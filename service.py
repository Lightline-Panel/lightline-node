"""Lightline Node — REST API service.

Manages shadowsocks-rust (ssserver) internally. No external Outline Server needed.
The panel communicates with this agent to add/remove users and check health.
"""

import platform
import time
import subprocess
import signal
import os
import logging
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from config import NODE_TOKEN, SS_PORT
from ss_config import (
    add_user, remove_user, list_users, load_config,
    save_config, get_server_port, set_server_port, get_config_path,
    get_server_password, SS_METHOD
)

logger = logging.getLogger('lightline-node')

app = FastAPI(title="Lightline Node", docs_url=None, redoc_url=None)

# Track uptime and ss-server process
_start_time = time.time()
_ss_process: subprocess.Popen = None


def start_ss_server():
    """Start the shadowsocks server process."""
    global _ss_process
    if _ss_process and _ss_process.poll() is None:
        logger.info("ss-server already running")
        return

    config_path = get_config_path()
    # Try shadowsocks-rust first, fall back to shadowsocks-libev
    for binary in ['ssserver', 'ss-server']:
        try:
            _ss_process = subprocess.Popen(
                [binary, '-c', config_path],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            logger.info(f"Started {binary} (PID {_ss_process.pid}) with config {config_path}")
            return
        except FileNotFoundError:
            continue
    logger.error("No shadowsocks binary found! Install shadowsocks-rust or shadowsocks-libev.")


def stop_ss_server():
    """Stop the shadowsocks server process."""
    global _ss_process
    if _ss_process and _ss_process.poll() is None:
        _ss_process.send_signal(signal.SIGTERM)
        _ss_process.wait(timeout=5)
        logger.info("ss-server stopped")
    _ss_process = None


def restart_ss_server():
    """Restart ss-server to pick up config changes."""
    stop_ss_server()
    start_ss_server()


def is_ss_running() -> bool:
    """Check if ss-server process is alive."""
    return _ss_process is not None and _ss_process.poll() is None


# ===== Auth =====

async def verify_token(request: Request):
    """Verify the Bearer token matches NODE_TOKEN."""
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        raise HTTPException(401, "Missing authorization header")
    token = auth[7:]
    if token != NODE_TOKEN:
        raise HTTPException(403, "Invalid token")
    return token


# ===== Pydantic models =====

class AddUserRequest(BaseModel):
    username: str
    password: str

class RemoveUserRequest(BaseModel):
    username: str


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

@app.get("/")
async def node_status(token: str = Depends(verify_token)):
    """Node status and info."""
    return {
        "service": "lightline-node",
        "version": "2.0.0",
        "hostname": platform.node(),
        "uptime_seconds": int(time.time() - _start_time),
        "ss_running": is_ss_running(),
        "ss_port": get_server_port(),
        "users": len(list_users()),
    }


@app.get("/health")
async def health_check(token: str = Depends(verify_token)):
    """Health check — is ss-server running?"""
    if not is_ss_running():
        return JSONResponse(status_code=503, content={"healthy": False, "error": "ss-server not running"})
    return {"healthy": True}


@app.get("/users")
async def get_users(token: str = Depends(verify_token)):
    """List all configured SS users."""
    return {"users": list_users()}


@app.post("/users")
async def create_user(req: AddUserRequest, token: str = Depends(verify_token)):
    """Register a user in metadata (no SS restart needed in single-password mode)."""
    result = add_user(req.username, req.password)
    return result


@app.delete("/users/{username}")
async def delete_user(username: str, token: str = Depends(verify_token)):
    """Remove a user from metadata."""
    result = remove_user(username)
    if result["action"] == "not_found":
        raise HTTPException(404, f"User '{username}' not found")
    return result


@app.get("/server-info")
async def server_info(token: str = Depends(verify_token)):
    """Return the server's shared SS password, port, and method.
    
    In single-password mode (Outline model), all users connect with
    the same server password. The panel uses this to build ss:// URLs.
    """
    return {
        "password": get_server_password(),
        "port": get_server_port(),
        "method": SS_METHOD,
    }


@app.post("/restart")
async def restart(token: str = Depends(verify_token)):
    """Restart ss-server."""
    restart_ss_server()
    return {"restarted": True, "running": is_ss_running()}
