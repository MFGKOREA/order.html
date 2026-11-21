"""Keys come from the environment or the OS keychain. Nothing here prints a secret."""
import os
import re
import subprocess
import sys

NAMES = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "HR_BOARD_PASSWORD", "ORDER_APP_API",
         "HUB_SYNC_SECRET", "HUB_SCREEN_PASSWORD")
_KEY = re.compile(r"sk-(?:ant|proj)-[A-Za-z0-9_\-]{8,}|sk-[A-Za-z0-9]{12,}")
_ASSIGNED = re.compile(r"(?i)(api[_-]?key|password|secret|token)\s*[=:]\s*\S+")


def read_secret(name, env=None):
    """The value for `name`, from `env` when given, otherwise the process environment, then the keychain.

    A passed-in mapping is not the process environment: tests and callers stay in control, and the
    keychain is not consulted for them.
    """
    if env is not None and env is not os.environ:
        return env.get(name) or None
    if os.environ.get(name):
        return os.environ[name]
    return _keychain(name)


def secret_values(env=None):
    """Values currently available, so a log line can be scrubbed of the real secret. Never logged."""
    env = os.environ if env is None else env
    return [env[name] for name in NAMES if env.get(name)]


def redact(text, secrets=()):
    """Replace key material with [비밀]. `secrets` is the live values (any length that is worth hiding)."""
    if not text:
        return text
    for secret in secrets:
        if secret and len(secret) >= 6:
            text = text.replace(secret, "[비밀]")
    text = _KEY.sub("[비밀]", text)
    return _ASSIGNED.sub(r"\1=[비밀]", text)


def _keychain(name):
    if sys.platform != "darwin":
        return None  # Windows Credential Manager is not read without another package
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-s", "pickle-hub", "-a", name, "-w"],
            check=False, capture_output=True, text=True, timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None
