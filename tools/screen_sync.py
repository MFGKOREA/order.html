"""Push the kitchen snapshot and pull signed confirm taps.

The order-app sheet kv is read-only, so this talks to the kitchen web app.
The web app keeps the snapshot and the command queue. Bytes are signed with
HUB_SYNC_SECRET. The same canonical strings live in kitchen/lib/hmac.js.
"""
import hashlib
import hmac
import json
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import hubkeys

INTERVAL = 5
KEY_RE = re.compile(r"^[A-Za-z0-9:_-]{8,80}$")


def sign(secret, payload):
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def command_canonical(cmd):
    return f"confirm\n{int(cmd['task_id'])}\n{cmd['idempotency_key']}\n{cmd['at']}".encode("utf-8")


def verify_command(secret, cmd):
    if not isinstance(cmd, dict):
        return False
    try:
        expected = sign(secret, command_canonical(cmd))
    except (KeyError, TypeError, ValueError):
        return False
    got = str(cmd.get("sig") or "")
    return hmac.compare_digest(expected, got)


def _scrub(value, secrets):
    if isinstance(value, str):
        return hubkeys.redact(value, secrets)
    if isinstance(value, list):
        return [_scrub(item, secrets) for item in value]
    if isinstance(value, dict):
        return {key: _scrub(item, secrets) for key, item in value.items()}
    return value


def snapshot_bytes(snapshot, secrets=()):
    clean = _scrub(snapshot, secrets)
    return json.dumps(clean, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _open(opener, request):
    try:
        with opener(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8") or "{}")
    except HTTPError as exc:
        raise RuntimeError(f"http {exc.code}") from None
    except URLError as exc:
        raise RuntimeError(type(exc.reason).__name__ if getattr(exc, "reason", None) else "url") from None


def push_snapshot(base, secret, snapshot, opener=urlopen, secrets=()):
    body = snapshot_bytes(snapshot, secrets)
    request = Request(
        base.rstrip("/") + "/api/hub/snapshot",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "X-Hub-Signature": "sha256=" + sign(secret, body)},
    )
    return _open(opener, request)


def fetch_commands(base, secret, opener=urlopen, now=None):
    stamp = str(int(now if now is not None else time.time()))
    canon = f"GET\n/api/hub/commands\n{stamp}".encode("utf-8")
    request = Request(
        base.rstrip("/") + "/api/hub/commands",
        method="GET",
        headers={"Accept": "application/json", "X-Hub-Timestamp": stamp, "X-Hub-Signature": "sha256=" + sign(secret, canon)},
    )
    return _open(opener, request)


def ack(base, secret, keys, opener=urlopen):
    body = json.dumps({"keys": keys}, separators=(",", ":"), sort_keys=True).encode("utf-8")
    request = Request(
        base.rstrip("/") + "/api/hub/ack",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "X-Hub-Signature": "sha256=" + sign(secret, body)},
    )
    return _open(opener, request)


def apply_signed_commands(hub, secret, commands):
    """Record each new tap on the ledger, then run the same 확인 path. A repeated key does nothing."""
    applied = []
    for cmd in commands or []:
        if not verify_command(secret, cmd):
            continue
        key = str(cmd.get("idempotency_key") or "")
        if not KEY_RE.fullmatch(key):
            continue
        task_id = int(cmd["task_id"])
        if hub.ledger.add(key, "화면", "허브", "접수", f"확인 #{task_id}"):
            hub.request_confirm(task_id)
        applied.append(key)
    return applied


def round_trip(base, secret, snapshot, apply, opener=urlopen, now=None, secrets=()):
    push_snapshot(base, secret, snapshot, opener, secrets)
    payload = fetch_commands(base, secret, opener, now=now)
    keys = apply(payload.get("commands") or [])
    if keys:
        ack(base, secret, keys, opener)
    return keys
