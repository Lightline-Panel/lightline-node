"""Lightline Node — Shadowsocks configuration manager.

Multi-user mode using AEAD-2022 cipher (2022-blake3-aes-128-gcm).
Each user gets their own unique key. The server has a master key.
shadowsocks-rust config format:
{
  "server": "0.0.0.0",
  "server_port": 8388,
  "method": "2022-blake3-aes-128-gcm",
  "password": "<server-key-base64>",
  "users": [
    {"name": "user1", "password": "<user-key-base64>"},
    ...
  ]
}

ss:// URL format for multi-user AEAD-2022:
  ss://BASE64(method:server-key:user-key)@host:port#tag
"""

import json
import os
import base64
import secrets
import logging
from pathlib import Path

logger = logging.getLogger('lightline-node')

SS_CONFIG_PATH = os.environ.get('SS_CONFIG_PATH', '/etc/shadowsocks/config.json')
SS_METHOD = "2022-blake3-aes-128-gcm"
SS_KEY_BYTES = 16  # aes-128-gcm requires 16-byte keys


def generate_ss_key() -> str:
    """Generate a base64-encoded random key for AEAD-2022."""
    return base64.b64encode(secrets.token_bytes(SS_KEY_BYTES)).decode()


def get_config_path() -> str:
    return SS_CONFIG_PATH


def load_config() -> dict:
    """Load the current SS config from disk."""
    path = Path(SS_CONFIG_PATH)
    if path.exists():
        try:
            with open(path) as f:
                config = json.load(f)
            # Migration: if old chacha20 config detected, regenerate with new cipher
            if config.get("method") != SS_METHOD:
                logger.info(f"Migrating config from {config.get('method')} to {SS_METHOD}")
                old_port = config.get("server_port", 8388)
                config = _default_config()
                config["server_port"] = old_port
                save_config(config)
            return config
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
    """Default multi-user shadowsocks-rust config with AEAD-2022."""
    return {
        "server": "0.0.0.0",
        "server_port": 8388,
        "method": SS_METHOD,
        "password": generate_ss_key(),
        "users": [],
        "mode": "tcp_and_udp",
        "no_delay": True
    }


def add_user(username: str, password: str) -> dict:
    """Add a user to the SS config users array.
    
    The password must be a valid base64-encoded 16-byte key.
    After calling this, restart ss-server to apply.
    """
    config = load_config()
    users = config.get("users", [])
    for u in users:
        if u.get("name") == username:
            u["password"] = password
            save_config(config)
            return {"action": "updated", "username": username}
    users.append({"name": username, "password": password})
    config["users"] = users
    save_config(config)
    return {"action": "added", "username": username}


def remove_user(username: str) -> dict:
    """Remove a user from the SS config users array.
    
    After calling this, restart ss-server to apply.
    """
    config = load_config()
    users = config.get("users", [])
    new_users = [u for u in users if u.get("name") != username]
    if len(new_users) == len(users):
        return {"action": "not_found", "username": username}
    config["users"] = new_users
    save_config(config)
    return {"action": "removed", "username": username}


def list_users() -> list:
    """List all users in the SS config."""
    config = load_config()
    return config.get("users", [])


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
    """Get the server's master key (used in ss:// URL as server-key part)."""
    config = load_config()
    return config.get("password", "")
