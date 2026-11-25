"""In-process WebSocket realtime hub for CINEMY Phone <-> TV Remote Control.

Architectural invariants:
  - TV is the authoritative playback owner.
  - Phone disconnect NEVER pauses or stops TV playback.
  - Every WebSocket connection is explicitly authenticated & authorized before accept().
  - Revoking a controller or TV immediately disconnects active sockets and blocks future commands.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional, Set

from fastapi import WebSocket

logger = logging.getLogger("cinemymovies.tv.ws")

ALLOWED_COMMANDS = frozenset({
    "PLAY",
    "PAUSE",
    "SEEK_FORWARD",
    "SEEK_BACKWARD",
    "SEEK_TO",
    "LOAD_MEDIA",
    "NEXT_EPISODE",
    "PREVIOUS_EPISODE",
    "VOLUME_SET",
    "MUTE_TOGGLE",
    "NAVIGATE_UP",
    "NAVIGATE_DOWN",
    "NAVIGATE_LEFT",
    "NAVIGATE_RIGHT",
    "SELECT",
    "BACK",
    "HOME",
})


class TvRealtimeHub:
    def __init__(self) -> None:
        self._tv_sockets: Dict[str, Set[WebSocket]] = {}
        self._phone_sockets: Dict[str, Dict[str, WebSocket]] = {}
        self._tv_states: Dict[str, Dict[str, Any]] = {}
        self._socket_loops: Dict[int, asyncio.AbstractEventLoop] = {}

    def online_tv_ids(self) -> Set[str]:
        return {tv_id for tv_id, socks in self._tv_sockets.items() if socks}

    def is_tv_online(self, tv_id: str) -> bool:
        return bool(self._tv_sockets.get(tv_id))

    def get_tv_state(self, tv_id: str) -> Optional[Dict[str, Any]]:
        return self._tv_states.get(tv_id)

    def connected_controller_ids(self, tv_id: str) -> Set[str]:
        return set(self._phone_sockets.get(tv_id, {}).keys())

    async def register_tv_socket(self, tv_id: str, ws: WebSocket) -> None:
        self._socket_loops[id(ws)] = asyncio.get_running_loop()
        self._tv_sockets.setdefault(tv_id, set()).add(ws)
        asyncio.create_task(self._broadcast_to_phones(tv_id, {
            "type": "tv_status",
            "tv_id": tv_id,
            "online": True,
            "state": self._tv_states.get(tv_id),
            "ts": int(time.time()),
        }))

    async def unregister_tv_socket(self, tv_id: str, ws: WebSocket) -> None:
        self._socket_loops.pop(id(ws), None)
        socks = self._tv_sockets.get(tv_id)
        if socks:
            socks.discard(ws)
            if not socks:
                self._tv_sockets.pop(tv_id, None)
                asyncio.create_task(self._broadcast_to_phones(tv_id, {
                    "type": "tv_status",
                    "tv_id": tv_id,
                    "online": False,
                    "ts": int(time.time()),
                }))

    async def register_phone_socket(self, tv_id: str, controller_id: str, phone_name: str, ws: WebSocket) -> None:
        self._socket_loops[id(ws)] = asyncio.get_running_loop()
        phones = self._phone_sockets.setdefault(tv_id, {})
        prev = phones.get(controller_id)
        if prev is not None and prev is not ws:
            try:
                await prev.close(code=4000, reason="replaced_by_reconnect")
            except Exception:
                pass
        phones[controller_id] = ws

        # Immediately sync authoritative TV state to the (re)connected phone
        await self._safe_send(ws, {
            "type": "connected",
            "role": "phone",
            "tv_id": tv_id,
            "controller_id": controller_id,
            "tv_online": self.is_tv_online(tv_id),
            "state": self._tv_states.get(tv_id),
            "ts": int(time.time()),
        })

        asyncio.create_task(self._broadcast_to_tvs(tv_id, {
            "type": "controller_connected",
            "tv_id": tv_id,
            "controller_id": controller_id,
            "phone_name": phone_name,
            "ts": int(time.time()),
        }))

    async def unregister_phone_socket(self, tv_id: str, controller_id: str, ws: WebSocket) -> None:
        """
        Phone disconnected. CRITICAL: NEVER send PAUSE or STOP to TV!
        Only notify TV of controller presence change so playback continues uninterrupted.
        """
        self._socket_loops.pop(id(ws), None)
        phones = self._phone_sockets.get(tv_id)
        if phones and phones.get(controller_id) is ws:
            phones.pop(controller_id, None)
            if not phones:
                self._phone_sockets.pop(tv_id, None)
            asyncio.create_task(self._broadcast_to_tvs(tv_id, {
                "type": "controller_disconnected",
                "tv_id": tv_id,
                "controller_id": controller_id,
                "ts": int(time.time()),
            }))

    async def handle_tv_state(self, tv_id: str, state: Dict[str, Any]) -> None:
        sanitized = {
            "status": str(state.get("status") or "IDLE"),
            "mediaId": state.get("mediaId"),
            "currentTitle": state.get("currentTitle"),
            "currentEpisode": state.get("currentEpisode"),
            "season": state.get("season"),
            "episode": state.get("episode"),
            "isSeries": bool(state.get("isSeries")),
            "currentPosition": float(state.get("currentPosition") or 0),
            "duration": float(state.get("duration") or 0),
            "isPlaying": bool(state.get("isPlaying")),
            "volume": float(state.get("volume") if state.get("volume") is not None else 1.0),
            "muted": bool(state.get("muted")),
            "playerKind": state.get("playerKind"),
            "updatedAt": int(time.time()),
        }
        self._tv_states[tv_id] = sanitized
        await self._broadcast_to_phones(tv_id, {
            "type": "state",
            "tv_id": tv_id,
            "state": sanitized,
        })

    async def forward_command_to_tv(
        self,
        *,
        tv_id: str,
        controller_id: str,
        phone_name: str,
        payload: Dict[str, Any],
    ) -> bool:
        cmd = str(payload.get("command") or "").upper().strip()
        if cmd not in ALLOWED_COMMANDS:
            return False

        msg: Dict[str, Any] = {
            "type": "command",
            "command": cmd,
            "tv_id": tv_id,
            "controller_id": controller_id,
            "phone_name": phone_name,
            "ts": int(time.time()),
        }
        for key in ("seconds", "position", "volume", "media"):
            if key in payload and payload[key] is not None:
                msg[key] = payload[key]

        delivered = await self._broadcast_to_tvs(tv_id, msg)
        return delivered > 0

    async def disconnect_revoked(self, tv_id: str, controller_id: Optional[str] = None) -> None:
        phones = self._phone_sockets.get(tv_id, {})
        targets = (
            [(controller_id, phones.get(controller_id))]
            if controller_id
            else list(phones.items())
        )
        for cid, sock in targets:
            if sock is None:
                continue
            try:
                await self._safe_send(sock, {"type": "revoked", "tv_id": tv_id, "controller_id": cid})
                await sock.close(code=4403, reason="controller_revoked")
            except Exception:
                pass
            if cid:
                phones.pop(cid, None)
        if not phones:
            self._phone_sockets.pop(tv_id, None)

    async def disconnect_tv(self, tv_id: str) -> None:
        await self.disconnect_revoked(tv_id)
        for sock in list(self._tv_sockets.get(tv_id, set())):
            try:
                await sock.close(code=4403, reason="tv_revoked")
            except Exception:
                pass
        self._tv_sockets.pop(tv_id, None)
        self._tv_states.pop(tv_id, None)

    async def _broadcast_to_tvs(self, tv_id: str, message: Dict[str, Any]) -> int:
        socks = list(self._tv_sockets.get(tv_id, set()))
        sent = 0
        for sock in socks:
            if await self._safe_send(sock, message):
                sent += 1
        return sent

    async def _broadcast_to_phones(self, tv_id: str, message: Dict[str, Any]) -> int:
        socks = list(self._phone_sockets.get(tv_id, {}).values())
        sent = 0
        for sock in socks:
            if await self._safe_send(sock, message):
                sent += 1
        return sent

    async def _safe_send(self, ws: WebSocket, message: Dict[str, Any]) -> bool:
        try:
            current_loop = asyncio.get_running_loop()
            target_loop = self._socket_loops.get(id(ws))
            if target_loop is not None and target_loop is not current_loop and target_loop.is_running():
                fut = asyncio.run_coroutine_threadsafe(ws.send_json(message), target_loop)
                await asyncio.wait_for(asyncio.wrap_future(fut), timeout=3.0)
            else:
                await asyncio.wait_for(ws.send_json(message), timeout=3.0)
            return True
        except Exception:
            return False


hub = TvRealtimeHub()
