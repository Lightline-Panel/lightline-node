"""Lightline Node — REST API service.

Follows Marzban-node pattern:
  - Session-based connection (panel calls /connect first)
  - mTLS authentication (no bearer tokens)
  - Panel controls ssserver lifecycle via /start, /stop, /restart
  - /server-info returns shared SS password, port, method for URL building
"""

import platform
import time
import subprocess
import signal
import os
import json
import logging
import struct
import socket
from pathlib import Path
from uuid import UUID, uuid4
from fastapi import FastAPI, HTTPException, Body, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from config import SS_PORT
from ss_config import (
    load_config, save_config, get_server_port, set_server_port,
    get_config_path, get_server_password, SS_METHOD
)

logger = logging.getLogger('lightline-node')

app = FastAPI(title="Lightline Node", docs_url=None, redoc_url=None)

# ===== SS Server Process Management =====

_start_time = time.time()
_ss_process: subprocess.Popen = None
_traffic_offset = {"upload": 0, "download": 0}  # cumulative from previous ssserver runs
TRAFFIC_STATE_FILE = os.environ.get('TRAFFIC_STATE_FILE', '/var/lib/lightline-node/traffic.json')


def _load_traffic_state():
    """Load cumulative traffic from previous ssserver runs."""
    global _traffic_offset
    try:
        p = Path(TRAFFIC_STATE_FILE)
        if p.exists():
            data = json.loads(p.read_text())
            _traffic_offset = {"upload": data.get("upload", 0), "download": data.get("download", 0)}
            logger.info(f"Loaded traffic state: up={_traffic_offset['upload']}, down={_traffic_offset['download']}")
    except Exception as e:
        logger.warning(f"Failed to load traffic state: {e}")


def _save_traffic_state():
    """Save cumulative traffic before ssserver stops."""
    try:
        current = _get_process_io()
        total_up = _traffic_offset["upload"] + current["upload"]
        total_down = _traffic_offset["download"] + current["download"]
        p = Path(TRAFFIC_STATE_FILE)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"upload": total_up, "download": total_down}))
        logger.info(f"Saved traffic state: up={total_up}, down={total_down}")
    except Exception as e:
        logger.warning(f"Failed to save traffic state: {e}")


def _get_process_io() -> dict:
    """Read ssserver process I/O from /proc/{pid}/io.
    
    Returns upload (write_bytes) and download (read_bytes) for current process.
    """
    if not _ss_process or _ss_process.poll() is not None:
        return {"upload": 0, "download": 0}
    try:
        io_path = f"/proc/{_ss_process.pid}/io"
        with open(io_path, 'r') as f:
            data = {}
            for line in f:
                parts = line.strip().split(': ')
                if len(parts) == 2:
                    data[parts[0]] = int(parts[1])
        return {
            "upload": data.get("write_bytes", 0),
            "download": data.get("read_bytes", 0),
        }
    except (FileNotFoundError, PermissionError, ValueError) as e:
        logger.debug(f"Cannot read process IO: {e}")
        return {"upload": 0, "download": 0}


def _get_active_connections() -> dict:
    """Count active TCP connections to the SS port and list unique client IPs.
    
    Reads /proc/net/tcp (and /proc/net/tcp6) for ESTABLISHED connections.
    """
    ss_port = get_server_port()
    connections = []
    unique_ips = set()
    
    for tcp_file in ['/proc/net/tcp', '/proc/net/tcp6']:
        try:
            with open(tcp_file, 'r') as f:
                for line in f.readlines()[1:]:  # skip header
                    parts = line.strip().split()
                    if len(parts) < 4:
                        continue
                    # State 01 = ESTABLISHED
                    state = parts[3]
                    if state != '01':
                        continue
                    # local_address is hex ip:port
                    local = parts[1]
                    local_port = int(local.split(':')[1], 16)
                    if local_port != ss_port:
                        continue
                    # remote address
                    remote = parts[2]
                    remote_hex_ip = remote.split(':')[0]
                    try:
                        if tcp_file.endswith('tcp6') and len(remote_hex_ip) == 32:
                            # IPv6 or IPv4-mapped-IPv6
                            ip_bytes = bytes.fromhex(remote_hex_ip)
                            # Check if it's IPv4-mapped (::ffff:x.x.x.x)
                            if ip_bytes[:12] == b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xff':
                                ip_str = socket.inet_ntoa(ip_bytes[12:16][::-1] if len(remote_hex_ip) == 8 else ip_bytes[12:16])
                            else:
                                # Reverse each 4-byte group for /proc/net/tcp6 little-endian format
                                groups = [ip_bytes[i:i+4][::-1] for i in range(0, 16, 4)]
                                ip_str = socket.inet_ntop(socket.AF_INET6, b''.join(groups))
                        else:
                            # IPv4: stored as little-endian hex
                            ip_int = int(remote_hex_ip, 16)
                            ip_str = socket.inet_ntoa(struct.pack('<I', ip_int))
                    except Exception:
                        ip_str = remote_hex_ip
                    unique_ips.add(ip_str)
                    connections.append(ip_str)
        except FileNotFoundError:
            continue
        except Exception as e:
            logger.debug(f"Cannot read {tcp_file}: {e}")
    
    return {
        "count": len(connections),
        "unique_ips": list(unique_ips),
        "devices": len(unique_ips),
    }


def start_ss_server():
    """Start the shadowsocks server process."""
    global _ss_process
    if _ss_process and _ss_process.poll() is None:
        logger.info("ss-server already running")
        return True

    # Ensure config exists before starting
    config_path = get_config_path()
    config = load_config()
    save_config(config)  # write default config if missing
    logger.info(f"SS config: port={config.get('server_port')}, method={config.get('method')}, password={'***' if config.get('password') else 'EMPTY'}")

    ss_port = config.get('server_port', 8388)
    ss_method = config.get('method', 'chacha20-ietf-poly1305')
    ss_password = config.get('password', '')

    for binary in ['ssserver', 'ss-server']:
        try:
            # ssserver v1.20+ requires --encrypt-method and --server-addr even with -c
            cmd = [
                binary,
                '-s', f'0.0.0.0:{ss_port}',
                '-m', ss_method,
                '-k', ss_password,
                '-U',  # UDP relay
                '--no-delay',
            ]
            logger.info(f"Starting: {binary} -s 0.0.0.0:{ss_port} -m {ss_method} -k *** -U --no-delay")
            _ss_process = subprocess.Popen(
                cmd,
                stdout=None, stderr=None
            )
            # Wait briefly to check if it crashed immediately
            import time as _t
            _t.sleep(0.5)
            if _ss_process.poll() is not None:
                rc = _ss_process.returncode
                logger.error(f"{binary} exited immediately with code {rc}")
                _ss_process = None
                continue
            logger.info(f"Started {binary} (PID {_ss_process.pid}) with config {config_path}")
            return True
        except FileNotFoundError:
            logger.debug(f"{binary} not found, trying next...")
            continue
        except Exception as e:
            logger.error(f"Failed to start {binary}: {e}")
            continue
    logger.error("No shadowsocks binary found! Install shadowsocks-rust or shadowsocks-libev.")
    return False


def stop_ss_server():
    """Stop the shadowsocks server process."""
    global _ss_process
    _save_traffic_state()
    if _ss_process and _ss_process.poll() is None:
        _ss_process.send_signal(signal.SIGTERM)
        try:
            _ss_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _ss_process.kill()
        logger.info("ss-server stopped")
    _ss_process = None


def restart_ss_server():
    """Restart ss-server to pick up config changes."""
    stop_ss_server()
    return start_ss_server()


def is_ss_running() -> bool:
    """Check if ss-server process is alive."""
    return _ss_process is not None and _ss_process.poll() is None


# ===== Session Management (Marzban-node pattern) =====

_connected = False
_client_ip = None
_session_id = None


def _response(**kwargs):
    """Standard response with connection state."""
    return {
        "connected": _connected,
        "started": is_ss_running(),
        "version": "3.0.0",
        **kwargs
    }


def _check_session(session_id: UUID):
    """Verify session ID matches current session."""
    if session_id != _session_id:
        raise HTTPException(403, "Session ID mismatch")
    return True


# ===== Startup / Shutdown =====

@app.on_event("startup")
async def startup():
    """Initialize SS config and start the server."""
    _load_traffic_state()
    config = load_config()
    if SS_PORT and config.get("server_port") != SS_PORT:
        set_server_port(SS_PORT)
    start_ss_server()


@app.on_event("shutdown")
async def shutdown():
    stop_ss_server()


# ===== Routes =====

@app.post("/")
async def base():
    """Base status endpoint."""
    return _response()


@app.post("/connect")
async def connect(request: Request):
    """Panel connects to this node. Returns a session ID for subsequent calls.
    
    Like Marzban-node: first call from panel establishes the session.
    If another panel connects, it takes over control.
    """
    global _connected, _client_ip, _session_id

    new_ip = request.client.host if request.client else "unknown"
    _session_id = uuid4()

    if _connected:
        logger.warning(f"New connection from {new_ip}, taking control from {_client_ip}")
    
    _connected = True
    _client_ip = new_ip
    logger.info(f"{_client_ip} connected, Session ID = \"{_session_id}\"")

    return _response(session_id=str(_session_id))


@app.post("/disconnect")
async def disconnect():
    """Panel disconnects from this node."""
    global _connected, _client_ip, _session_id

    if _connected:
        logger.info(f"{_client_ip} disconnected, Session ID = \"{_session_id}\"")

    _session_id = None
    _client_ip = None
    _connected = False

    return _response()


@app.post("/ping")
async def ping(session_id: UUID = Body(embed=True)):
    """Heartbeat — panel pings to keep session alive."""
    _check_session(session_id)
    return {"ok": True}


@app.get("/health")
async def health_check():
    """Health check — no auth required, used by panel to check if node is reachable."""
    return {
        "healthy": is_ss_running(),
        "connected": _connected,
        "ss_running": is_ss_running(),
        "uptime": int(time.time() - _start_time),
    }


@app.get("/server-info")
async def server_info():
    """Return the server's shared SS password, port, and method.
    
    No session required — panel needs this to build ss:// URLs.
    In single-password mode, all users connect with the same password.
    """
    return {
        "password": get_server_password(),
        "port": get_server_port(),
        "method": SS_METHOD,
    }


@app.post("/start")
async def start(session_id: UUID = Body(embed=True)):
    """Start ss-server."""
    _check_session(session_id)
    ok = start_ss_server()
    if not ok:
        raise HTTPException(503, "Failed to start ss-server")
    return _response()


@app.post("/stop")
async def stop(session_id: UUID = Body(embed=True)):
    """Stop ss-server."""
    _check_session(session_id)
    stop_ss_server()
    return _response()


@app.post("/restart")
async def restart(session_id: UUID = Body(embed=True)):
    """Restart ss-server."""
    _check_session(session_id)
    ok = restart_ss_server()
    if not ok:
        raise HTTPException(503, "Failed to restart ss-server")
    return _response()


@app.get("/stats")
async def stats():
    """Traffic statistics and active connections — no auth required.
    
    Returns cumulative upload/download bytes and connected device info.
    Panel polls this endpoint periodically to update TrafficLog.
    """
    proc_io = _get_process_io()
    conns = _get_active_connections()
    return {
        "upload": _traffic_offset["upload"] + proc_io["upload"],
        "download": _traffic_offset["download"] + proc_io["download"],
        "active_connections": conns["count"],
        "connected_devices": conns["devices"],
        "connected_ips": conns["unique_ips"],
        "ss_running": is_ss_running(),
    }


@app.get("/status")
async def status():
    """Full node status — no session required."""
    proc_io = _get_process_io()
    conns = _get_active_connections()
    return {
        "service": "lightline-node",
        "version": "3.0.0",
        "hostname": platform.node(),
        "uptime_seconds": int(time.time() - _start_time),
        "ss_running": is_ss_running(),
        "ss_port": get_server_port(),
        "connected": _connected,
        "client_ip": _client_ip,
        "traffic_upload": _traffic_offset["upload"] + proc_io["upload"],
        "traffic_download": _traffic_offset["download"] + proc_io["download"],
        "active_connections": conns["count"],
        "connected_devices": conns["devices"],
    }
