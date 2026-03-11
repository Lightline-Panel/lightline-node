"""Lightline Node — Shadowsocks configuration manager.

Manages ss-server config file and process. Each user gets their own
password on a shared port using the multi-user feature of ss-rust,
or individual ports with ss-libev.

We use shadowsocks-rust with the `--manager-address` approach or
a simple JSON config file that gets reloaded on changes.
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
    """Default multi-user shadowsocks-rust config."""
    return {
        "server": "0.0.0.0",
        "server_port": 8388,
        "method": SS_METHOD,
        "password": "",
        "users": []
    }


def add_user(username: str, password: str) -> dict:
    """Add a user to the SS config."""
    config = load_config()

    # Check if user already exists
    users = config.get("users", [])
    for u in users:
        if u.get("name") == username:
            u["password"] = password
            save_config(config)
            return {"action": "updated", "username": username}

    users.append({"name": username, "password": password})
    config["users"] = users

    # For single-user mode (ss-libev), set the main password to first user
    if not config.get("password") and users:
        config["password"] = users[0]["password"]

    save_config(config)
    return {"action": "added", "username": username}


def remove_user(username: str) -> dict:
    """Remove a user from the SS config."""
    config = load_config()
    users = config.get("users", [])
    new_users = [u for u in users if u.get("name") != username]
    if len(new_users) == len(users):
        return {"action": "not_found", "username": username}
    config["users"] = new_users
    save_config(config)
    return {"action": "removed", "username": username}


def list_users() -> list:
    """List all configured users."""
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
