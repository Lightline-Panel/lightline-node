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
TRAFFIC_STATE_FILE = os.environ.get('TRAFFIC_STATE_FILE', '/var/lib/lightline-node/traffic.json')
_IPTABLES_CHAIN = 'LIGHTLINE_STATS'
_iptables_ready = False


def _run_cmd(cmd: list, timeout: int = 5) -> tuple:
    """Run a shell command and return (stdout, stderr, returncode)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout, r.stderr, r.returncode
    except Exception as e:
        return '', str(e), -1


def _setup_iptables():
    """Set up iptables accounting rules for the SS port.
    
    Creates a custom chain LIGHTLINE_STATS with rules to count
    all incoming and outgoing bytes on the SS port (both TCP and UDP).
    Counters persist across reads — we read them cumulatively.
    """
    global _iptables_ready
    ss_port = get_server_port()

    # Create chain (ignore error if exists)
    _run_cmd(['iptables', '-N', _IPTABLES_CHAIN])

    # Flush existing rules in our chain
    _run_cmd(['iptables', '-F', _IPTABLES_CHAIN])

    # Add counting rules inside our chain:
    # - Incoming traffic (download): destination port = ss_port
    # - Outgoing traffic (upload): source port = ss_port
    for proto in ['tcp', 'udp']:
        _run_cmd(['iptables', '-A', _IPTABLES_CHAIN, '-p', proto, '--dport', str(ss_port), '-j', 'RETURN'])
        _run_cmd(['iptables', '-A', _IPTABLES_CHAIN, '-p', proto, '--sport', str(ss_port), '-j', 'RETURN'])

    # Hook our chain into INPUT and OUTPUT (remove old refs first, ignore errors)
    for chain in ['INPUT', 'OUTPUT']:
        _run_cmd(['iptables', '-D', chain, '-j', _IPTABLES_CHAIN])
        out, err, rc = _run_cmd(['iptables', '-I', chain, '-j', _IPTABLES_CHAIN])
        if rc != 0:
            logger.warning(f"Failed to hook {_IPTABLES_CHAIN} into {chain}: {err}")

    _iptables_ready = True
    logger.info(f"iptables accounting rules set up for port {ss_port}")


def _read_iptables_bytes() -> dict:
    """Read cumulative byte counters from iptables LIGHTLINE_STATS chain.
    
    Returns download (dport rules) and upload (sport rules) bytes.
    iptables counters are cumulative since chain creation / last reset.
    """
    if not _iptables_ready:
        return {"upload": 0, "download": 0}

    out, err, rc = _run_cmd(['iptables', '-L', _IPTABLES_CHAIN, '-n', '-v', '-x'])
    if rc != 0:
        logger.debug(f"iptables read failed: {err}")
        return {"upload": 0, "download": 0}

    download = 0  # dport rules = incoming to SS = client download
    upload = 0    # sport rules = outgoing from SS = client upload

    ss_port = str(get_server_port())
    for line in out.strip().split('\n')[2:]:  # skip header lines
        parts = line.split()
        if len(parts) < 10:
            continue
        try:
            byte_count = int(parts[1])
            # Check if this is a dport or sport rule
            # Format: pkts bytes target prot opt in out source destination [extra...]
            rest = ' '.join(parts[8:])
            if f'dpt:{ss_port}' in rest:
                download += byte_count
            elif f'spt:{ss_port}' in rest:
                upload += byte_count
        except (ValueError, IndexError):
            continue

    return {"upload": upload, "download": download}


def _load_traffic_state():
    """Load saved traffic offset from previous container runs.
    
    When the container restarts, iptables counters reset to 0.
    We save the cumulative total before shutdown so we can add it back.
    """
    try:
        p = Path(TRAFFIC_STATE_FILE)
        if p.exists():
            data = json.loads(p.read_text())
            logger.info(f"Loaded traffic state: up={data.get('upload', 0)}, down={data.get('download', 0)}")
            return {"upload": data.get("upload", 0), "download": data.get("download", 0)}
    except Exception as e:
        logger.warning(f"Failed to load traffic state: {e}")
    return {"upload": 0, "download": 0}


def _save_traffic_state():
    """Save current cumulative traffic (iptables counters + offset) before shutdown."""
    try:
        offset = _load_traffic_state()
        current = _read_iptables_bytes()
        total = {
            "upload": offset["upload"] + current["upload"],
            "download": offset["download"] + current["download"],
        }
        p = Path(TRAFFIC_STATE_FILE)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(total))
        logger.info(f"Saved traffic state: up={total['upload']}, down={total['download']}")
    except Exception as e:
        logger.warning(f"Failed to save traffic state: {e}")


def _get_traffic() -> dict:
    """Get total cumulative traffic (iptables current + saved offset)."""
    offset = _load_traffic_state()
    current = _read_iptables_bytes()
    return {
        "upload": offset["upload"] + current["upload"],
        "download": offset["download"] + current["download"],
    }


def _parse_ip_from_addr(addr: str) -> str:
    """Extract IP from address string like '1.2.3.4:12345' or '[::1]:12345'."""
    if addr.startswith('['):
        return addr.split(']')[0][1:]
    elif addr.count(':') > 1:
        return ':'.join(addr.split(':')[:-1])
    else:
        return addr.rsplit(':', 1)[0]


def _get_active_connections() -> dict:
    """Count active connections to the SS port.
    
    Strategy:
    1. TCP connections via `ss -t` (established TCP sockets on SS port)
    2. UDP flows via `conntrack` (netfilter tracks UDP flows even though UDP is connectionless)
    3. Fallback: `ss -u` for any UDP sockets that show a peer
    
    Extracts unique client IPs across all methods.
    """
    ss_port = get_server_port()
    unique_ips = set()
    total_conns = 0

    # --- Method 1: TCP established connections via ss ---
    try:
        out, err, rc = _run_cmd([
            'ss', '-t', '-n', 'state', 'established',
            f'sport = :{ss_port}'
        ])
        if rc == 0 and out.strip():
            for line in out.strip().split('\n')[1:]:
                parts = line.split()
                if len(parts) >= 5:
                    ip = _parse_ip_from_addr(parts[4])
                    if ip and ip not in ('*', '0.0.0.0', '::'):
                        unique_ips.add(ip)
                        total_conns += 1
    except Exception as e:
        logger.debug(f"ss TCP failed: {e}")

    # --- Method 2: UDP flows via conntrack ---
    try:
        out, err, rc = _run_cmd([
            'conntrack', '-L', '-p', 'udp',
            '--dport', str(ss_port), '-o', 'extended'
        ], timeout=5)
        if rc == 0 and out.strip():
            for line in out.strip().split('\n'):
                # conntrack lines: udp ... src=1.2.3.4 dst=... sport=... dport=8388
                parts = line.split()
                for part in parts:
                    if part.startswith('src='):
                        ip = part[4:]
                        if ip and ip not in ('0.0.0.0', '127.0.0.1', '::'):
                            unique_ips.add(ip)
                            total_conns += 1
                        break
    except Exception as e:
        logger.debug(f"conntrack failed: {e}")

    # --- Method 3: Fallback — ss UDP sockets ---
    try:
        out, err, rc = _run_cmd([
            'ss', '-u', '-n', '-a',
            f'sport = :{ss_port}'
        ])
        if rc == 0 and out.strip():
            for line in out.strip().split('\n')[1:]:
                parts = line.split()
                if len(parts) >= 5:
                    ip = _parse_ip_from_addr(parts[4])
                    if ip and ip not in ('*', '0.0.0.0', '::', '0.0.0.0:*'):
                        unique_ips.add(ip)
                        total_conns += 1
    except Exception as e:
        logger.debug(f"ss UDP failed: {e}")

    return {
        "count": total_conns,
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
    config = load_config()
    if SS_PORT and config.get("server_port") != SS_PORT:
        set_server_port(SS_PORT)
    start_ss_server()
    _setup_iptables()


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
    Uses iptables byte counters (TCP+UDP) and `ss` command for connections.
    """
    traffic = _get_traffic()
    conns = _get_active_connections()
    return {
        "upload": traffic["upload"],
        "download": traffic["download"],
        "active_connections": conns["count"],
        "connected_devices": conns["devices"],
        "connected_ips": conns["unique_ips"],
        "ss_running": is_ss_running(),
    }


@app.post("/config/port")
async def set_port(session_id: UUID = Body(...), port: int = Body(...)):
    """Change the SS server port and restart ss-server.
    
    Called by panel when admin changes the global SS port in settings.
    Requires active session.
    """
    _check_session(session_id)
    if port < 1 or port > 65535:
        raise HTTPException(400, "Invalid port number")
    old_port = get_server_port()
    set_server_port(port)
    ok = restart_ss_server()
    if not ok:
        # Revert on failure
        set_server_port(old_port)
        restart_ss_server()
        raise HTTPException(503, f"Failed to restart ss-server on port {port}, reverted to {old_port}")
    logger.info(f"SS port changed from {old_port} to {port}, server restarted")
    return {"ok": True, "old_port": old_port, "new_port": port}


@app.get("/status")
async def status():
    """Full node status — no session required."""
    traffic = _get_traffic()
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
        "traffic_upload": traffic["upload"],
        "traffic_download": traffic["download"],
        "active_connections": conns["count"],
        "connected_devices": conns["devices"],
    }
