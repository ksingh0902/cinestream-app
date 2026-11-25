"""Backend unit & integration tests for CINEMY TV Remote Phase 1 — Pairing Foundation."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.auth import config as auth_config
from app.auth.store import init_auth_db
from app.tv import init_tv_db, tv_router
from app.tv import service as tv_service
from app.tv import store as tv_store


class TestTvPairingFoundation(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="cinemy_tv_phase1_")
        self.db_path = os.path.join(self.temp_dir, "test_tv.sqlite3")
        self._prev_auth_db = auth_config.AUTH_DB_PATH
        self._prev_auth_url = auth_config.AUTH_DATABASE_URL
        auth_config.AUTH_DB_PATH = self.db_path
        auth_config.AUTH_DATABASE_URL = ""

        init_auth_db()
        init_tv_db()

        self.active_user = "alice"
        self.app = FastAPI()

        @self.app.middleware("http")
        async def inject_test_session(request: Request, call_next):
            user_hdr = request.headers.get("x-test-user")
            if user_hdr != "ANON":
                request.state.session = {
                    "username": user_hdr or self.active_user,
                    "role": "viewer",
                }
            return await call_next(request)

        self.app.include_router(tv_router)
        self.client = TestClient(self.app)

    def tearDown(self):
        auth_config.AUTH_DB_PATH = self._prev_auth_db
        auth_config.AUTH_DATABASE_URL = self._prev_auth_url
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_unauthenticated_requests_rejected(self):
        r = self.client.post("/api/tv/register", json={"name": "Living Room TV"}, headers={"x-test-user": "ANON"})
        self.assertEqual(r.status_code, 401)
        r2 = self.client.get("/api/tv/devices", headers={"x-test-user": "ANON"})
        self.assertEqual(r2.status_code, 401)

    def test_02_register_multiple_tvs_and_persistent_identity(self):
        r1 = self.client.post("/api/tv/register", json={"name": "Living Room TV"})
        self.assertEqual(r1.status_code, 200)
        tv1 = r1.json()
        self.assertTrue(tv1["tv_id"].startswith("tv_"))
        self.assertIn("device_secret", tv1)

        r2 = self.client.post("/api/tv/register", json={"name": "Bedroom TV"})
        self.assertEqual(r2.status_code, 200)
        tv2 = r2.json()
        self.assertNotEqual(tv1["tv_id"], tv2["tv_id"])

        # Re-registering existing tv_id with valid secret preserves identity and updates name
        r1_upd = self.client.post(
            "/api/tv/register",
            json={"tv_id": tv1["tv_id"], "device_secret": tv1["device_secret"], "name": "Main Lounge TV"},
        )
        self.assertEqual(r1_upd.status_code, 200)
        self.assertEqual(r1_upd.json()["name"], "Main Lounge TV")
        self.assertNotIn("device_secret", r1_upd.json())

        listed = self.client.get("/api/tv/devices").json()["devices"]
        self.assertEqual(len(listed), 2)
        names = {d["name"] for d in listed}
        self.assertEqual(names, {"Main Lounge TV", "Bedroom TV"})

    def test_03_qr_pairing_creation_completion_and_single_use(self):
        tv = self.client.post("/api/tv/register", json={"name": "Living Room TV"}).json()
        pair = self.client.post("/api/tv/pairing/start", json={"tv_id": tv["tv_id"]}).json()

        self.assertTrue(pair["pairing_id"].startswith("pair_"))
        self.assertEqual(len(pair["code"]), 6)
        self.assertTrue(pair["code"].isdigit())
        self.assertIn("pid=", pair["qr_path"])
        self.assertIn("t=", pair["qr_path"])
        # QR payload must never contain permanent secrets or session cookies
        self.assertNotIn("cms_session", pair["qr_path"])
        self.assertNotIn(tv["device_secret"], pair["qr_path"])

        # Complete via QR credentials
        comp = self.client.post(
            "/api/tv/pairing/complete",
            json={
                "pairing_id": pair["pairing_id"],
                "pairing_token": pair["pairing_token"],
                "phone_name": "Alice iPhone",
            },
        )
        self.assertEqual(comp.status_code, 200)
        data = comp.json()
        self.assertTrue(data["paired"])
        self.assertEqual(data["tv_id"], tv["tv_id"])
        self.assertEqual(data["role"], "primary")
        self.assertTrue(data["controller_id"].startswith("ctrl_"))
        self.assertTrue(len(data["control_token"]) >= 24)

        # Duplicate / replay of same QR pairing MUST fail
        replay = self.client.post(
            "/api/tv/pairing/complete",
            json={
                "pairing_id": pair["pairing_id"],
                "pairing_token": pair["pairing_token"],
                "phone_name": "Attacker Phone",
            },
        )
        self.assertEqual(replay.status_code, 410)

        # Verify controller credentials validate cleanly
        verified = tv_service.verify_controller_credentials(
            data["controller_id"], data["control_token"], tv_id=tv["tv_id"], owner_username="alice"
        )
        self.assertIsNotNone(verified)

    def test_04_six_digit_code_fallback_and_secondary_controller(self):
        tv = self.client.post("/api/tv/register", json={"name": "Bedroom TV"}).json()
        p1 = self.client.post("/api/tv/pairing/start", json={"tv_id": tv["tv_id"]}).json()
        c1 = self.client.post(
            "/api/tv/pairing/complete",
            json={"code": p1["display_code"], "phone_name": "Phone One"},
        )
        self.assertEqual(c1.status_code, 200)
        self.assertEqual(c1.json()["role"], "primary")

        # Second pairing produces secondary controller
        p2 = self.client.post("/api/tv/pairing/start", json={"tv_id": tv["tv_id"]}).json()
        c2 = self.client.post(
            "/api/tv/pairing/complete",
            json={"code": p2["code"], "phone_name": "Phone Two"},
        )
        self.assertEqual(c2.status_code, 200)
        self.assertEqual(c2.json()["role"], "secondary")

    def test_05_expired_pairing_rejected(self):
        tv = self.client.post("/api/tv/register", json={"name": "Living Room TV"}).json()
        pair = self.client.post("/api/tv/pairing/start", json={"tv_id": tv["tv_id"]}).json()

        # Force expiration in DB
        from app.auth.database import connect
        with connect() as conn:
            conn.execute(
                "UPDATE tv_pairing_sessions SET expires_at = ? WHERE pairing_id = ?",
                (int(time.time()) - 10, pair["pairing_id"]),
            )

        r_qr = self.client.post(
            "/api/tv/pairing/complete",
            json={"pairing_id": pair["pairing_id"], "pairing_token": pair["pairing_token"]},
        )
        self.assertEqual(r_qr.status_code, 410)

        r_code = self.client.post("/api/tv/pairing/complete", json={"code": pair["code"]})
        self.assertEqual(r_code.status_code, 400)

    def test_06_invalid_code_rate_limit_lockout(self):
        tv = self.client.post("/api/tv/register", json={"name": "Living Room TV"}).json()
        pair = self.client.post("/api/tv/pairing/start", json={"tv_id": tv["tv_id"]}).json()

        for _ in range(tv_service.PAIRING_MAX_FAILED_ATTEMPTS):
            bad = self.client.post(
                "/api/tv/pairing/complete",
                json={"pairing_id": pair["pairing_id"], "pairing_token": "wrong-token"},
            )
            self.assertEqual(bad.status_code, 400)

        # Next attempt even with valid token must be locked (429)
        locked = self.client.post(
            "/api/tv/pairing/complete",
            json={"pairing_id": pair["pairing_id"], "pairing_token": pair["pairing_token"]},
        )
        self.assertEqual(locked.status_code, 429)

    def test_07_cross_account_isolation(self):
        tv = self.client.post("/api/tv/register", json={"name": "Alice TV"}, headers={"x-test-user": "alice"}).json()
        pair = self.client.post(
            "/api/tv/pairing/start", json={"tv_id": tv["tv_id"]}, headers={"x-test-user": "alice"}
        ).json()

        # Bob cannot pair with Alice's TV
        r_bob = self.client.post(
            "/api/tv/pairing/complete",
            json={"pairing_id": pair["pairing_id"], "pairing_token": pair["pairing_token"]},
            headers={"x-test-user": "bob"},
        )
        self.assertEqual(r_bob.status_code, 403)

        # Bob cannot see Alice's TVs
        bob_devices = self.client.get("/api/tv/devices", headers={"x-test-user": "bob"}).json()["devices"]
        self.assertEqual(bob_devices, [])

    def test_08_revocation_invalidates_controller_and_tv_deletion_revokes_all(self):
        tv = self.client.post("/api/tv/register", json={"name": "Living Room TV"}).json()
        pair = self.client.post("/api/tv/pairing/start", json={"tv_id": tv["tv_id"]}).json()
        ctrl = self.client.post(
            "/api/tv/pairing/complete",
            json={"pairing_id": pair["pairing_id"], "pairing_token": pair["pairing_token"], "phone_name": "Phone A"},
        ).json()

        # Revoke single controller
        rev = self.client.post(
            f"/api/tv/devices/{tv['tv_id']}/revoke",
            json={"controller_id": ctrl["controller_id"]},
        )
        self.assertEqual(rev.status_code, 200)
        self.assertEqual(rev.json()["revoked_count"], 1)
        self.assertIsNone(
            tv_service.verify_controller_credentials(ctrl["controller_id"], ctrl["control_token"])
        )

        # Pair again then delete TV -> revokes TV and controller
        pair2 = self.client.post("/api/tv/pairing/start", json={"tv_id": tv["tv_id"]}).json()
        ctrl2 = self.client.post(
            "/api/tv/pairing/complete",
            json={"code": pair2["code"], "phone_name": "Phone B"},
        ).json()
        del_r = self.client.delete(f"/api/tv/devices/{tv['tv_id']}")
        self.assertEqual(del_r.status_code, 200)
        self.assertIsNone(
            tv_service.verify_controller_credentials(ctrl2["controller_id"], ctrl2["control_token"])
        )
        self.assertEqual(self.client.get("/api/tv/devices").json()["devices"], [])

    def test_09_websocket_two_way_commands_state_sync_disconnect_and_reconnect(self):
        tv = self.client.post("/api/tv/register", json={"name": "Living Room TV"}).json()
        pair = self.client.post("/api/tv/pairing/start", json={"tv_id": tv["tv_id"]}).json()
        ctrl = self.client.post(
            "/api/tv/pairing/complete",
            json={"pairing_id": pair["pairing_id"], "pairing_token": pair["pairing_token"], "phone_name": "Test Phone"},
        ).json()

        tv_ws_url = f"/api/tv/ws?role=tv&tv_id={tv['tv_id']}&device_secret={tv['device_secret']}"
        phone_ws_url = (
            f"/api/tv/ws?role=phone&tv_id={tv['tv_id']}"
            f"&controller_id={ctrl['controller_id']}&control_token={ctrl['control_token']}"
        )

        # Unauthorized phone token must be rejected
        bad_phone_url = (
            f"/api/tv/ws?role=phone&tv_id={tv['tv_id']}"
            f"&controller_id={ctrl['controller_id']}&control_token=forged_token"
        )
        with self.assertRaises(Exception):
            with self.client.websocket_connect(bad_phone_url):
                pass

        with self.client.websocket_connect(tv_ws_url) as tv_ws:
            tv_hello = tv_ws.receive_json()
            self.assertEqual(tv_hello["type"], "connected")
            self.assertEqual(tv_hello["role"], "tv")

            with self.client.websocket_connect(phone_ws_url) as phone_ws:
                p_hello = phone_ws.receive_json()
                self.assertEqual(p_hello["type"], "connected")
                self.assertTrue(p_hello["tv_online"])

                tv_conn_notice = tv_ws.receive_json()
                self.assertEqual(tv_conn_notice["type"], "controller_connected")

                # Phone sends PLAY -> TV receives PLAY
                phone_ws.send_json({"type": "command", "command": "PLAY"})
                tv_cmd = tv_ws.receive_json()
                self.assertEqual(tv_cmd["type"], "command")
                self.assertEqual(tv_cmd["command"], "PLAY")
                ack = phone_ws.receive_json()
                self.assertEqual(ack["type"], "ack")
                self.assertTrue(ack["delivered"])

                # TV reports authoritative state -> Phone receives it
                tv_ws.send_json({
                    "type": "state",
                    "state": {
                        "status": "PLAYING",
                        "currentTitle": "Friends",
                        "currentEpisode": "S01E01",
                        "currentPosition": 1934,
                        "duration": 2535,
                        "isPlaying": True,
                        "volume": 0.8,
                    },
                })
                st = phone_ws.receive_json()
                self.assertEqual(st["type"], "state")
                self.assertEqual(st["state"]["currentTitle"], "Friends")
                self.assertEqual(st["state"]["currentPosition"], 1934.0)

                # Phone sends PAUSE and SEEK_FORWARD
                phone_ws.send_json({"type": "command", "command": "PAUSE"})
                self.assertEqual(tv_ws.receive_json()["command"], "PAUSE")
                self.assertTrue(phone_ws.receive_json()["delivered"])

                phone_ws.send_json({"type": "command", "command": "SEEK_FORWARD", "seconds": 30})
                seek_cmd = tv_ws.receive_json()
                self.assertEqual(seek_cmd["command"], "SEEK_FORWARD")
                self.assertEqual(seek_cmd["seconds"], 30)
                self.assertTrue(phone_ws.receive_json()["delivered"])

            # Phone disconnected (e.g. phone call / lock / background):
            # TV must ONLY receive controller_disconnected, NEVER PAUSE or STOP!
            disc_notice = tv_ws.receive_json()
            self.assertEqual(disc_notice["type"], "controller_disconnected")
            self.assertNotEqual(disc_notice.get("command"), "PAUSE")

            # TV continues playing and advances position to 2100s
            tv_ws.send_json({
                "type": "state",
                "state": {
                    "status": "PLAYING",
                    "currentTitle": "Friends",
                    "currentEpisode": "S01E01",
                    "currentPosition": 2100,
                    "duration": 2535,
                    "isPlaying": True,
                    "volume": 0.8,
                },
            })

            # Phone reconnects and immediately receives authoritative TV state (2100s, PLAYING)
            with self.client.websocket_connect(phone_ws_url) as phone_ws2:
                re_hello = phone_ws2.receive_json()
                self.assertEqual(re_hello["type"], "connected")
                self.assertTrue(re_hello["tv_online"])
                self.assertEqual(re_hello["state"]["currentPosition"], 2100.0)
                self.assertEqual(re_hello["state"]["status"], "PLAYING")

        # Revoke controller -> future WS connection must be rejected
        self.client.post(
            f"/api/tv/devices/{tv['tv_id']}/revoke",
            json={"controller_id": ctrl["controller_id"]},
        )
        with self.assertRaises(Exception):
            with self.client.websocket_connect(phone_ws_url):
                pass

    def test_10_same_network_automatic_discovery_and_load_media_command(self):
        # Register TV from home Wi-Fi IP
        tv = self.client.post(
            "/api/tv/register",
            json={"name": "Living Room TV"},
            headers={"x-forwarded-for": "203.0.113.5"},
        ).json()

        # Phone on SAME Wi-Fi IP sees nearby=True, same_network=True
        same_net = self.client.get(
            "/api/tv/devices", headers={"x-forwarded-for": "203.0.113.5"}
        ).json()["devices"]
        self.assertEqual(len(same_net), 1)
        self.assertTrue(same_net[0]["nearby"])
        self.assertTrue(same_net[0]["same_network"])

        # Phone on cellular IP sees same_network=False, nearby=False (still pairable via QR/code!)
        diff_net = self.client.get(
            "/api/tv/devices", headers={"x-forwarded-for": "198.51.100.9"}
        ).json()["devices"]
        self.assertEqual(len(diff_net), 1)
        self.assertFalse(diff_net[0]["same_network"])
        self.assertFalse(diff_net[0]["nearby"])

        # Pair and verify LOAD_MEDIA + disallowed command rejection
        pair = self.client.post("/api/tv/pairing/start", json={"tv_id": tv["tv_id"]}).json()
        ctrl = self.client.post(
            "/api/tv/pairing/complete",
            json={"code": pair["code"], "phone_name": "Cellular Phone"},
        ).json()

        tv_ws_url = f"/api/tv/ws?role=tv&tv_id={tv['tv_id']}&device_secret={tv['device_secret']}"
        phone_ws_url = (
            f"/api/tv/ws?role=phone&tv_id={tv['tv_id']}"
            f"&controller_id={ctrl['controller_id']}&control_token={ctrl['control_token']}"
        )
        with self.client.websocket_connect(tv_ws_url) as tv_ws:
            tv_ws.receive_json()
            with self.client.websocket_connect(phone_ws_url) as phone_ws:
                phone_ws.receive_json()
                tv_ws.receive_json()  # controller_connected

                # Send LOAD_MEDIA
                phone_ws.send_json({
                    "type": "command",
                    "command": "LOAD_MEDIA",
                    "media": {"id": 42, "title": "Inception", "isSeries": False},
                })
                loaded = tv_ws.receive_json()
                self.assertEqual(loaded["command"], "LOAD_MEDIA")
                self.assertEqual(loaded["media"]["id"], 42)
                self.assertTrue(phone_ws.receive_json()["delivered"])

                # Unknown/disallowed command must NOT be delivered
                phone_ws.send_json({"type": "command", "command": "DROP_DATABASE"})
                ack_bad = phone_ws.receive_json()
                self.assertFalse(ack_bad["delivered"])


if __name__ == "__main__":
    unittest.main()
