"""Lightline Node — REST API service."""

import platform
import time
import logging
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from config import NODE_TOKEN, OUTLINE_API_URL, OUTLINE_API_KEY
from outline import OutlineClient

logger = logging.getLogger('lightline-node')

app = FastAPI(title="Lightline Node", docs_url=None, redoc_url=None)

# Outline client instance
outline = OutlineClient(OUTLINE_API_URL, OUTLINE_API_KEY)

# Track uptime
_start_time = time.time()


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

class CreateKeyRequest(BaseModel):
    name: Optional[str] = None

class RenameKeyRequest(BaseModel):
    name: str

class DataLimitRequest(BaseModel):
    limit_bytes: int


# ===== Routes =====

@app.get("/")
async def node_status(token: str = Depends(verify_token)):
    """Node status and info."""
    outline_healthy = await outline.check_health()
    return {
        "service": "lightline-node",
        "version": "1.0.0",
        "hostname": platform.node(),
        "uptime_seconds": int(time.time() - _start_time),
        "outline_connected": outline_healthy,
        "outline_api_url": OUTLINE_API_URL,
    }


@app.get("/health")
async def health_check(token: str = Depends(verify_token)):
    """Health check — returns Outline server connectivity."""
    healthy = await outline.check_health()
    if not healthy:
        return JSONResponse(
            status_code=503,
            content={"healthy": False, "error": "Cannot reach Outline server"}
        )
    return {"healthy": True}


@app.get("/server")
async def get_server_info(token: str = Depends(verify_token)):
    """Get Outline server info."""
    try:
        info = await outline.get_server_info()
        return info
    except Exception as e:
        raise HTTPException(502, f"Outline API error: {e}")


@app.get("/keys")
async def list_keys(token: str = Depends(verify_token)):
    """List all Outline access keys."""
    try:
        data = await outline.get_access_keys()
        return data
    except Exception as e:
        raise HTTPException(502, f"Outline API error: {e}")


@app.post("/keys")
async def create_key(req: CreateKeyRequest, token: str = Depends(verify_token)):
    """Create a new Outline access key."""
    try:
        key_data = await outline.create_access_key(name=req.name)
        return key_data
    except Exception as e:
        raise HTTPException(502, f"Outline API error: {e}")


@app.delete("/keys/{key_id}")
async def delete_key(key_id: str, token: str = Depends(verify_token)):
    """Delete an Outline access key."""
    try:
        result = await outline.delete_access_key(key_id)
        return {"deleted": True}
    except Exception as e:
        raise HTTPException(502, f"Outline API error: {e}")


@app.put("/keys/{key_id}/name")
async def rename_key(key_id: str, req: RenameKeyRequest, token: str = Depends(verify_token)):
    """Rename an Outline access key."""
    try:
        await outline.rename_access_key(key_id, req.name)
        return {"renamed": True, "name": req.name}
    except Exception as e:
        raise HTTPException(502, f"Outline API error: {e}")


@app.put("/keys/{key_id}/data-limit")
async def set_data_limit(key_id: str, req: DataLimitRequest, token: str = Depends(verify_token)):
    """Set data transfer limit on an access key."""
    try:
        await outline.set_data_limit(key_id, req.limit_bytes)
        return {"limit_set": True, "bytes": req.limit_bytes}
    except Exception as e:
        raise HTTPException(502, f"Outline API error: {e}")


@app.delete("/keys/{key_id}/data-limit")
async def remove_data_limit(key_id: str, token: str = Depends(verify_token)):
    """Remove data transfer limit from an access key."""
    try:
        await outline.remove_data_limit(key_id)
        return {"limit_removed": True}
    except Exception as e:
        raise HTTPException(502, f"Outline API error: {e}")


@app.get("/metrics")
async def get_metrics(token: str = Depends(verify_token)):
    """Get transfer metrics from Outline."""
    try:
        data = await outline.get_metrics()
        return data
    except Exception as e:
        raise HTTPException(502, f"Outline API error: {e}")
