"""FastAPI routes for CINEMY TV Pairing & Device Management."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.auth.config import SESSION_COOKIE_NAME
from app.auth.service import validate_session
from . import service, store
from .ws_hub import hub

tv_router = APIRouter(prefix="/api/tv", tags=["tv-remote"])


def _require_authenticated_username(request: Request) -> str:
    session = getattr(request.state, "session", None)
    if isinstance(session, dict):
        username = str(session.get("username") or "").strip()
        if username:
            return username
    user_obj = getattr(request.state, "user", None)
    if isinstance(user_obj, dict):
        username = str(user_obj.get("username") or "").strip()
        if username:
            return username
    raise HTTPException(status_code=401, detail="Authentication required")


def _extract_client_ip(request: Request) -> Optional[str]:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else None


class RegisterTvRequest(BaseModel):
    tv_id: Optional[str] = Field(default=None, max_length=64)
    name: Optional[str] = Field(default="Living Room TV", max_length=60)
    device_secret: Optional[str] = Field(default=None, max_length=128)


class StartPairingRequest(BaseModel):
    tv_id: str = Field(..., min_length=5, max_length=64)


class CompletePairingRequest(BaseModel):
    pairing_id: Optional[str] = Field(default=None, max_length=64)
    pairing_token: Optional[str] = Field(default=None, max_length=128)
    code: Optional[str] = Field(default=None, max_length=16)
    phone_name: Optional[str] = Field(default="Mobile Remote", max_length=60)


class RevokeControllerRequest(BaseModel):
    controller_id: Optional[str] = Field(default=None, max_length=64)


@tv_router.post("/register")
def register_tv_endpoint(payload: RegisterTvRequest, request: Request):
    username = _require_authenticated_username(request)
    try:
        return service.register_tv(
            owner_username=username,
            name=payload.name,
            tv_id=payload.tv_id,
            device_secret=payload.device_secret,
            client_ip=_extract_client_ip(request),
        )
    except service.TvPairingError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


@tv_router.post("/pairing/start")
def start_pairing_endpoint(payload: StartPairingRequest, request: Request):
    username = _require_authenticated_username(request)
    try:
        return service.start_pairing(
            owner_username=username,
            tv_id=payload.tv_id,
            client_ip=_extract_client_ip(request),
        )
    except service.TvPairingError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


@tv_router.post("/pairing/complete")
def complete_pairing_endpoint(payload: CompletePairingRequest, request: Request):
    username = _require_authenticated_username(request)
    try:
        return service.complete_pairing(
            owner_username=username,
            pairing_id=payload.pairing_id,
            pairing_token=payload.pairing_token,
            code=payload.code,
            phone_name=payload.phone_name,
        )
    except service.TvPairingError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


@tv_router.get("/devices")
def list_tv_devices_endpoint(request: Request):
    username = _require_authenticated_username(request)
    devices = service.list_devices(
        owner_username=username,
        client_ip=_extract_client_ip(request),
        online_tv_ids=hub.online_tv_ids(),
    )
    return {"devices": devices}


@tv_router.post("/devices/{tv_id}/heartbeat")
def heartbeat_tv_endpoint(tv_id: str, request: Request):
    username = _require_authenticated_username(request)
    tv = store.get_tv_device(tv_id)
    if not tv or tv.get("revoked_at") is not None or tv["owner_username"] != username:
        raise HTTPException(status_code=404, detail="TV device not found")
    store.update_tv_presence(tv_id, service.hash_client_ip(_extract_client_ip(request)))
    controllers = store.list_active_controllers_for_tv(tv_id)
    return {
        "ok": True,
        "tv_id": tv_id,
        "controllers": [
            {
                "controller_id": c["controller_id"],
                "phone_name": c["phone_name"],
                "role": c["role"],
                "created_at": c["created_at"],
                "last_seen_at": c["last_seen_at"],
            }
            for c in controllers
        ],
    }


@tv_router.post("/devices/{tv_id}/revoke")
async def revoke_tv_controllers_endpoint(tv_id: str, payload: RevokeControllerRequest, request: Request):
    username = _require_authenticated_username(request)
    try:
        ok, count = service.revoke_controllers(
            owner_username=username,
            tv_id=tv_id,
            controller_id=payload.controller_id,
        )
        await hub.disconnect_revoked(tv_id, payload.controller_id)
        return {"ok": ok, "revoked_count": count, "tv_id": tv_id}
    except service.TvPairingError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


@tv_router.delete("/devices/{tv_id}")
async def delete_tv_device_endpoint(tv_id: str, request: Request):
    username = _require_authenticated_username(request)
    try:
        service.delete_tv(owner_username=username, tv_id=tv_id)
        await hub.disconnect_tv(tv_id)
        return {"ok": True, "tv_id": tv_id}
    except service.TvPairingError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


def _extract_ws_ip(websocket: WebSocket) -> Optional[str]:
    forwarded = websocket.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = websocket.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return websocket.client.host if websocket.client else None


def _resolve_ws_session_username(websocket: WebSocket) -> Optional[str]:
    token = websocket.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    try:
        sess = validate_session(token)
        if isinstance(sess, dict) and sess.get("username"):
            return str(sess["username"]).strip()
    except Exception:
        return None
    return None


@tv_router.websocket("/ws")
async def tv_realtime_ws(websocket: WebSocket):
    """
    Authenticated bidirectional WebSocket channel for Phone <-> TV Remote Control.
    Query params:
      - role=tv&tv_id=...&device_secret=...
      - role=phone&tv_id=...&controller_id=...&control_token=...
    Explicitly verifies scoped device/controller credentials (and optional session cookie owner)
    before accepting the connection.
    """
    role = (websocket.query_params.get("role") or "").strip().lower()
    tv_id = (websocket.query_params.get("tv_id") or "").strip()
    session_user = _resolve_ws_session_username(websocket)
    client_ip_hash = service.hash_client_ip(_extract_ws_ip(websocket))

    if role == "tv":
        device_secret = (websocket.query_params.get("device_secret") or "").strip()
        tv = service.verify_tv_credentials(tv_id, device_secret, owner_username=session_user)
        if not tv:
            await websocket.close(code=4401, reason="unauthorized_tv")
            return

        await websocket.accept()
        store.update_tv_presence(tv_id, client_ip_hash)
        await hub.register_tv_socket(tv_id, websocket)
        await websocket.send_json({
            "type": "connected",
            "role": "tv",
            "tv_id": tv_id,
            "connected_controllers": list(hub.connected_controller_ids(tv_id)),
        })
        try:
            while True:
                msg = await websocket.receive_json()
                if not isinstance(msg, dict):
                    continue
                msg_type = str(msg.get("type") or "").lower()
                if msg_type == "ping":
                    store.update_tv_presence(tv_id, client_ip_hash)
                    await websocket.send_json({"type": "pong"})
                elif msg_type == "state" and isinstance(msg.get("state"), dict):
                    store.update_tv_presence(tv_id, client_ip_hash)
                    await hub.handle_tv_state(tv_id, msg["state"])
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            await hub.unregister_tv_socket(tv_id, websocket)
        return

    if role == "phone":
        controller_id = (websocket.query_params.get("controller_id") or "").strip()
        control_token = (websocket.query_params.get("control_token") or "").strip()
        ctrl = service.verify_controller_credentials(
            controller_id, control_token, tv_id=tv_id, owner_username=session_user
        )
        if not ctrl:
            await websocket.close(code=4403, reason="unauthorized_controller")
            return

        await websocket.accept()
        store.touch_controller(controller_id)
        await hub.register_phone_socket(tv_id, controller_id, ctrl["phone_name"], websocket)
        try:
            while True:
                msg = await websocket.receive_json()
                if not isinstance(msg, dict):
                    continue
                msg_type = str(msg.get("type") or "").lower()
                if msg_type == "ping":
                    store.touch_controller(controller_id)
                    await websocket.send_json({"type": "pong"})
                elif msg_type == "command":
                    # Re-verify controller has not been revoked mid-session
                    still_valid = service.verify_controller_credentials(
                        controller_id, control_token, tv_id=tv_id
                    )
                    if not still_valid:
                        await websocket.send_json({"type": "revoked", "tv_id": tv_id, "controller_id": controller_id})
                        await websocket.close(code=4403, reason="controller_revoked")
                        break
                    store.touch_controller(controller_id)
                    delivered = await hub.forward_command_to_tv(
                        tv_id=tv_id,
                        controller_id=controller_id,
                        phone_name=ctrl["phone_name"],
                        payload=msg,
                    )
                    await websocket.send_json({
                        "type": "ack",
                        "command": str(msg.get("command") or "").upper(),
                        "delivered": delivered,
                    })
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            await hub.unregister_phone_socket(tv_id, controller_id, websocket)
        return

    await websocket.close(code=4400, reason="invalid_role")
