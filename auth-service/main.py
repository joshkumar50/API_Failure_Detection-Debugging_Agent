"""
Auth Service — Stellar AI Observability Platform
Handles JWT token generation and validation with structured JSON logging.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import jwt
from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
JWT_SECRET: str = os.getenv("JWT_SECRET", "stellar-jwt-secret-key-2026")
JWT_ALGORITHM: str = "HS256"
JWT_EXPIRY_MINUTES: int = 30
SERVICE_NAME: str = os.getenv("SERVICE_NAME", "auth-service")
MONITORING_URL: str = os.getenv("MONITORING_URL", "")  # Sprint 3 will set this

# ---------------------------------------------------------------------------
# Logging setup — structured JSON to stdout
# ---------------------------------------------------------------------------
logger = logging.getLogger("auth-service")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(message)s"))
logger.handlers = [handler]

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="Auth Service", version="1.0.0")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ValidateRequest(BaseModel):
    token: str


class ValidateResponse(BaseModel):
    valid: bool
    username: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Persistent HTTP client for log forwarding (Sprint 3)
# ---------------------------------------------------------------------------
_monitoring_client: httpx.AsyncClient | None = None


@app.on_event("startup")
async def _start_monitoring_client():
    global _monitoring_client
    if MONITORING_URL:
        _monitoring_client = httpx.AsyncClient(timeout=2.0)


@app.on_event("shutdown")
async def _stop_monitoring_client():
    global _monitoring_client
    if _monitoring_client:
        await _monitoring_client.aclose()


async def _forward_log(log_entry: dict) -> None:
    """Best-effort async forward to monitoring-engine."""
    if _monitoring_client and MONITORING_URL:
        try:
            await _monitoring_client.post(f"{MONITORING_URL}/ingest", json=log_entry)
        except Exception:
            pass  # Never block the response path


# ---------------------------------------------------------------------------
# Logging middleware — emits structured JSON for every request
# ---------------------------------------------------------------------------
@app.middleware("http")
async def logging_middleware(request: Request, call_next) -> Response:
    trace_id = request.headers.get("x-trace-id", str(uuid.uuid4()))
    start = time.perf_counter()

    # Attach trace_id so route handlers can read it
    request.state.trace_id = trace_id

    response: Response = await call_next(request)

    latency_ms = round((time.perf_counter() - start) * 1000, 2)

    status_code = response.status_code
    level = "ERROR" if status_code >= 500 else ("WARN" if status_code >= 400 else "INFO")

    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": SERVICE_NAME,
        "endpoint": request.url.path,
        "method": request.method,
        "status_code": status_code,
        "latency_ms": latency_ms,
        "level": level,
        "message": f"{request.method} {request.url.path} -> {status_code}",
        "trace_id": trace_id,
    }

    logger.info(json.dumps(log_entry))

    # Async forward to monitoring-engine (fire-and-forget via background task)
    asyncio.ensure_future(_forward_log(log_entry))

    # Propagate trace_id downstream
    response.headers["x-trace-id"] = trace_id
    return response


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, request: Request):
    """Generate a real JWT token. Any username/password is accepted for demo."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": body.username,
        "iat": now,
        "exp": now + timedelta(minutes=JWT_EXPIRY_MINUTES),
        "jti": str(uuid.uuid4()),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return LoginResponse(access_token=token)


@app.post("/validate", response_model=ValidateResponse)
async def validate(body: ValidateRequest, request: Request):
    """Decode and validate a JWT token."""
    try:
        decoded = jwt.decode(body.token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return ValidateResponse(valid=True, username=decoded.get("sub"))
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")


@app.get("/health")
async def health():
    return {"status": "healthy", "service": SERVICE_NAME}
