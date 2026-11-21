"""Kitchen sync: the signed snapshot, and a confirm tap applied once through the ledger."""
import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import hub  # noqa: E402
import screen_sync  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"
NOW = datetime(2026, 11, 13, 11, 0)
SECRET = "test-secret"


class Protocol(unittest.TestCase):
    def test_vectors_match_the_web_app(self):
        self.assertEqual(screen_sync.sign(SECRET, b'{"ok":true}'),
                         "97b4f11584439784b801821ece72af4e29c19573aacf94bcc0533c09086b3643")
        cmd = {"task_id": 3, "idempotency_key": "confirm-3-abc", "at": "2026-11-21T16:00:00Z"}
        self.assertEqual(screen_sync.sign(SECRET, screen_sync.command_canonical(cmd)),
                         "869c1b056ad0fe4a5d72e94fe4dc17c6ede4d1a8925cc3bd2c41ca9b4732cdd2")
        stamped = dict(cmd, sig=screen_sync.sign(SECRET, screen_sync.command_canonical(cmd)))
        self.assertTrue(screen_sync.verify_command(SECRET, stamped))
        stamped["task_id"] = 4
        self.assertFalse(screen_sync.verify_command(SECRET, stamped))

    def test_snapshot_bytes_drop_a_secret_before_signing(self):
        body = screen_sync.snapshot_bytes({"timeline": [{"body": "sk-ant-api03-abcdefghijklmnopqrstuvwxyz"}]},
                                           ["sk-ant-api03-abcdefghijklmnopqrstuvwxyz"])
        self.assertNotIn(b"sk-ant", body)
        self.assertIn("[비밀]".encode(), body)

    def test_a_tap_is_applied_once(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        cache, drive, state = root / "cache", root / "drive", root / "state"
        shutil.copytree(FIX, cache)
        box = hub.Hub(cache, drive, state, confirm=True, env={})
        box.tick(NOW)
        with (drive / hub.INBOX).open("a", encoding="utf-8") as handle:
            handle.write("브로콜리 2개 발주\n")
        box.tick(NOW)
        cmd = {"task_id": 1, "idempotency_key": "confirm-1-abc000", "at": "2026-11-21T16:00:00Z"}
        cmd["sig"] = screen_sync.sign(SECRET, screen_sync.command_canonical(cmd))
        self.assertEqual(screen_sync.apply_signed_commands(box, SECRET, [cmd, cmd]),
                         ["confirm-1-abc000", "confirm-1-abc000"])
        inbox = (drive / hub.INBOX).read_text(encoding="utf-8")
        self.assertEqual(inbox.count("확인 #1"), 1)
        self.assertFalse(screen_sync.apply_signed_commands(box, SECRET, [dict(cmd, sig="nope")]))

    def test_round_trip_signs_the_body_and_acks(self):
        seen = []

        class Response:
            def __init__(self, payload):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return json.dumps(self.payload).encode()

        def opener(request, timeout=10):
            body = request.data or b""
            seen.append((request.full_url, request.get_method(), request.headers.get("X-hub-signature"), body))
            if request.full_url.endswith("/commands"):
                return Response({"commands": []})
            return Response({"ok": True})

        keys = screen_sync.round_trip("https://hub.example", SECRET, {"badges": [], "confirms": [], "timeline": []},
                                       lambda commands: [], opener=opener, now=1700000000)
        self.assertEqual(keys, [])
        signature = seen[0][2]
        self.assertTrue(signature.startswith("sha256="))
        self.assertEqual(signature.split("=", 1)[1], screen_sync.sign(SECRET, seen[0][3]))
        self.assertNotIn(SECRET.encode(), seen[0][3])
