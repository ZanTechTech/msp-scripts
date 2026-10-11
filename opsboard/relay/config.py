import os
import re
import secrets
import yaml

_ENV_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def subst_env(value):
    """Recursively substitute ${ENV_VAR} in strings/dicts/lists."""
    if isinstance(value, str):
        return _ENV_RE.sub(lambda m: os.environ.get(m.group(1), ""), value)
    if isinstance(value, dict):
        return {k: subst_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [subst_env(v) for v in value]
    return value


def load_config(path, demo=False):
    cfg = {}
    if path and os.path.exists(path):
        with open(path) as f:
            cfg = yaml.safe_load(f) or {}
    cfg.setdefault("board_name", "Ops Board")
    cfg.setdefault("host", "0.0.0.0")
    cfg.setdefault("port", 8080)
    cfg.setdefault("poll_interval", 30)
    cfg.setdefault("decks", [])
    cfg.setdefault("actions", {})
    token = os.environ.get("BOARD_TOKEN") or cfg.get("token")
    if not token:
        token = "demo" if demo else secrets.token_urlsafe(24)
        print(f"[relay] no BOARD_TOKEN set; using generated token: {token}")
    cfg["token"] = token
    cfg["demo"] = demo
    return cfg
