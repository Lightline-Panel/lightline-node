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
import logging
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

    for binary in ['ssserver', 'ss-server']:
        try:
            # Don't pipe stdout/stderr — let it write to container logs and avoids pipe buffer deadlock
            _ss_process = subprocess.Popen(
                [binary, '-c', config_path, '-U'],
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


@app.get("/status")
async def status():
    """Full node status — no session required."""
    return {
        "service": "lightline-node",
        "version": "3.0.0",
        "hostname": platform.node(),
        "uptime_seconds": int(time.time() - _start_time),
        "ss_running": is_ss_running(),
        "ss_port": get_server_port(),
        "connected": _connected,
        "client_ip": _client_ip,
    }
