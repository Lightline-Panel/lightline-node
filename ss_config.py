"""Lightline Node — Shadowsocks configuration manager.

Manages ssserver config. Uses single-password mode (like Outline Server):
one server password shared by all users on a single port.
chacha20-ietf-poly1305 does NOT support multi-user 'users' array —
only AEAD-2022 ciphers do. So we use one password per server.

User differentiation (traffic, expiry) is handled at the panel level.
"""

import json
import os
import logging
from pathlib import Path

logger = logging.getLogger('lightline-node')

SS_CONFIG_PATH = os.environ.get('SS_CONFIG_PATH', '/etc/shadowsocks/config.json')
SS_METHOD = "chacha20-ietf-poly1305"


def get_config_path() -> str:
    return SS_CONFIG_PATH


def load_config() -> dict:
    """Load the current SS config from disk."""
    path = Path(SS_CONFIG_PATH)
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load SS config: {e}")
    return _default_config()


def save_config(config: dict):
    """Write config to disk."""
    path = Path(SS_CONFIG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as f:
        json.dump(config, f, indent=2)
    logger.info(f"SS config saved to {path}")


def _default_config() -> dict:
    """Default single-password shadowsocks-rust config."""
    import secrets as _secrets
    import base64 as _base64
    return {
        "server": "0.0.0.0",
        "server_port": 8388,
        "method": SS_METHOD,
        "password": _secrets.token_urlsafe(24),
        "mode": "tcp_and_udp",
        "no_delay": True
    }


def add_user(username: str, password: str) -> dict:
    """Register a user (tracked in metadata, not in SS config).
    
    In single-password mode, all users share the server password.
    We keep a metadata list for the panel to query.
    """
    meta = _load_user_meta()
    for u in meta:
        if u.get("name") == username:
            u["password"] = password
            _save_user_meta(meta)
            return {"action": "updated", "username": username}
    meta.append({"name": username, "password": password})
    _save_user_meta(meta)
    return {"action": "added", "username": username}


def remove_user(username: str) -> dict:
    """Remove a user from metadata."""
    meta = _load_user_meta()
    new_meta = [u for u in meta if u.get("name") != username]
    if len(new_meta) == len(meta):
        return {"action": "not_found", "username": username}
    _save_user_meta(new_meta)
    return {"action": "removed", "username": username}


def list_users() -> list:
    """List all registered users."""
    return _load_user_meta()


def get_server_port() -> int:
    """Get the configured server port."""
    config = load_config()
    return config.get("server_port", 8388)


def set_server_port(port: int):
    """Set the server port."""
    config = load_config()
    config["server_port"] = port
    save_config(config)


def get_server_password() -> str:
    """Get the server's single shared password."""
    config = load_config()
    return config.get("password", "")


# ===== User metadata (separate from SS config) =====

USER_META_PATH = os.environ.get('USER_META_PATH',
    str(Path(SS_CONFIG_PATH).parent / 'users.json'))


def _load_user_meta() -> list:
    path = Path(USER_META_PATH)
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _save_user_meta(meta: list):
    path = Path(USER_META_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as f:
        json.dump(meta, f, indent=2)
