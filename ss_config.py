"""Lightline Node — Shadowsocks configuration manager.

Uses outline-ss-server for multi-user support on the same port.
Each user gets a unique password with chacha20-ietf-poly1305.
The server differentiates users by trying each key during handshake.

outline-ss-server config format (YAML):
  keys:
    - id: user1
      port: 8388
      cipher: chacha20-ietf-poly1305
      secret: <password>
    - id: user2
      port: 8388
      cipher: chacha20-ietf-poly1305
      secret: <password>

ss:// URL format (standard SIP002):
  ss://BASE64(method:password)@host:port#tag
"""

import os
import secrets
import string
import logging
from pathlib import Path

try:
    import yaml
except ImportError:
    import json as yaml
    yaml.safe_load = lambda s: __import__('json').loads(s)
    yaml.dump = lambda d, f, **kw: f.write(__import__('json').dumps(d, indent=2))

logger = logging.getLogger('lightline-node')

SS_CONFIG_PATH = os.environ.get('SS_CONFIG_PATH', '/etc/shadowsocks/config.yml')
SS_METHOD = "chacha20-ietf-poly1305"


def generate_password(length: int = 24) -> str:
    """Generate a random password for a Shadowsocks user."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def get_config_path() -> str:
    return SS_CONFIG_PATH


def _load_raw() -> dict:
    """Load the raw YAML config from disk."""
    path = Path(SS_CONFIG_PATH)
    if path.exists():
        try:
            with open(path) as f:
                data = yaml.safe_load(f.read())
            if isinstance(data, dict):
                return data
        except Exception as e:
            logger.error(f"Failed to load SS config: {e}")
    return {"keys": []}


def _save_raw(data: dict):
    """Write YAML config to disk."""
    path = Path(SS_CONFIG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as f:
        yaml.dump(data, f, default_flow_style=False)
    logger.info(f"SS config saved to {path}")


def load_config() -> dict:
    """Load config. Handles migration from old JSON format."""
    # Check if old JSON config exists and migrate
    old_json = Path('/etc/shadowsocks/config.json')
    yml_path = Path(SS_CONFIG_PATH)
    if old_json.exists() and not yml_path.exists():
        try:
            import json
            with open(old_json) as f:
                old = json.load(f)
            port = old.get('server_port', 8388)
            logger.info(f"Migrating from old JSON config (port={port})")
            data = {"keys": []}
            _save_raw(data)
            # Store port in a sidecar file
            _save_port(port)
        except Exception as e:
            logger.error(f"Migration failed: {e}")
    return _load_raw()


def save_config(data: dict):
    """Write config to disk."""
    _save_raw(data)


def _port_file() -> Path:
    return Path(SS_CONFIG_PATH).parent / 'port'


def _save_port(port: int):
    p = _port_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(port))


def get_server_port() -> int:
    """Get the configured server port."""
    p = _port_file()
    if p.exists():
        try:
            return int(p.read_text().strip())
        except Exception:
            pass
    return int(os.environ.get('SS_PORT', '8388'))


def set_server_port(port: int):
    """Set the server port. Updates all keys in config to use new port."""
    _save_port(port)
    data = _load_raw()
    for key in data.get("keys", []):
        key["port"] = port
    _save_raw(data)


def add_user(username: str, password: str) -> dict:
    """Add a user to the outline-ss-server config.
    
    Each user gets their own key entry with a unique password,
    all sharing the same port and cipher.
    After calling this, restart outline-ss-server to apply.
    """
    port = get_server_port()
    data = _load_raw()
    keys = data.get("keys", [])
    for k in keys:
        if k.get("id") == username:
            k["secret"] = password
            k["port"] = port
            k["cipher"] = SS_METHOD
            _save_raw(data)
            return {"action": "updated", "username": username}
    keys.append({
        "id": username,
        "port": port,
        "cipher": SS_METHOD,
        "secret": password,
    })
    data["keys"] = keys
    _save_raw(data)
    return {"action": "added", "username": username}


def remove_user(username: str) -> dict:
    """Remove a user from the outline-ss-server config.
    
    After calling this, restart outline-ss-server to apply.
    """
    data = _load_raw()
    keys = data.get("keys", [])
    new_keys = [k for k in keys if k.get("id") != username]
    if len(new_keys) == len(keys):
        return {"action": "not_found", "username": username}
    data["keys"] = new_keys
    _save_raw(data)
    return {"action": "removed", "username": username}


def list_users() -> list:
    """List all users in the config."""
    data = _load_raw()
    return data.get("keys", [])


def get_server_password() -> str:
    """Not used in multi-user mode. Returns empty string."""
    return ""
