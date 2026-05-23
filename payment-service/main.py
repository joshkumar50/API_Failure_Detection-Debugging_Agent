"""
Payment Service — Stellar AI Observability Platform
Handles payments with real DB transactions, inter-service auth validation,
and a chaos endpoint for organic failure injection.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import httpx
import jwt
from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Numeric, String, Text, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://stellar:stellar_secret@postgres-db:5432/stellar_db",
)
AUTH_SERVICE_URL: str = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8001")
JWT_SECRET: str = os.getenv("JWT_SECRET", "stellar-jwt-secret-key-2026")
JWT_ALGORITHM: str = "HS256"
SERVICE_NAME: str = os.getenv("SERVICE_NAME", "payment-service")
MONITORING_URL: str = os.getenv("MONITORING_URL", "")  # Sprint 3

# ---------------------------------------------------------------------------
# Logging — structured JSON to stdout
# ---------------------------------------------------------------------------
logger = logging.getLogger("payment-service")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(message)s"))
logger.handlers = [handler]

# ---------------------------------------------------------------------------
# SQLAlchemy async engine & models
# ---------------------------------------------------------------------------
engine = create_async_engine(DATABASE_URL, echo=False, pool_size=20, max_overflow=10)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(128), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="USD")
    status = Column(String(20), nullable=False, default="completed")
    trace_id = Column(String(36), nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="Payment Service", version="1.0.0")


# ---------------------------------------------------------------------------
# Startup — create tables
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def on_startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": SERVICE_NAME,
        "level": "INFO",
        "message": "Database tables created / verified",
    }))


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class PayRequest(BaseModel):
    amount: float = Field(gt=0, description="Payment amount")
    currency: str = Field(default="USD", max_length=3)
    description: str | None = None


class PayResponse(BaseModel):
    transaction_id: str
    status: str
    amount: float
    currency: str
    username: str


class ChaosRequest(BaseModel):
    mode: str = Field(
        default="lock",
        description="Chaos mode: 'lock' to lock the transactions table, 'sleep' for 5s delay",
    )


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
# Logging middleware — identical contract to auth-service
# ---------------------------------------------------------------------------
@app.middleware("http")
async def logging_middleware(request: Request, call_next) -> Response:
    trace_id = request.headers.get("x-trace-id", str(uuid.uuid4()))
    start = time.perf_counter()
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

    # Async forward to monitoring-engine (fire-and-forget)
    asyncio.ensure_future(_forward_log(log_entry))

    response.headers["x-trace-id"] = trace_id
    return response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _validate_token(token: str, trace_id: str) -> str:
    """Call auth-service /validate and return the username."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.post(
            f"{AUTH_SERVICE_URL}/validate",
            json={"token": token},
            headers={"x-trace-id": trace_id},
        )
    if resp.status_code != 200:
        detail = resp.json().get("detail", "Authentication failed")
        raise HTTPException(status_code=401, detail=detail)
    data = resp.json()
    if not data.get("valid"):
        raise HTTPException(status_code=401, detail=data.get("error", "Invalid token"))
    return data["username"]


def _extract_bearer(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    return auth[7:]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.post("/pay", response_model=PayResponse)
async def pay(body: PayRequest, request: Request):
    """Process a payment: validate token via auth-service, then INSERT into DB."""
    trace_id: str = getattr(request.state, "trace_id", str(uuid.uuid4()))
    token = _extract_bearer(request)

    # 1) Validate with auth-service over HTTP
    username = await _validate_token(token, trace_id)

    # 2) Insert transaction into postgres
    txn = Transaction(
        username=username,
        amount=body.amount,
        currency=body.currency,
        status="completed",
        trace_id=trace_id,
        description=body.description,
    )

    async with async_session() as session:
        async with session.begin():
            session.add(txn)

    return PayResponse(
        transaction_id=txn.id,
        status=txn.status,
        amount=float(txn.amount),
        currency=txn.currency,
        username=username,
    )


@app.post("/inject-chaos")
async def inject_chaos(body: ChaosRequest, request: Request):
    """
    Protected chaos endpoint for demo purposes.
    - 'lock': Acquires an exclusive table lock for 5 seconds, blocking all other writes.
    - 'sleep': Simulates severe network degradation via a 5-second sleep.
    """
    trace_id: str = getattr(request.state, "trace_id", str(uuid.uuid4()))
    token = _extract_bearer(request)

    # Must be authenticated
    await _validate_token(token, trace_id)

    if body.mode == "lock":
        # Acquire an exclusive lock on the transactions table for 5 seconds.
        # This organically degrades all concurrent /pay requests.
        async with async_session() as session:
            async with session.begin():
                await session.execute(text("LOCK TABLE transactions IN ACCESS EXCLUSIVE MODE"))
                logger.info(json.dumps({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "service": SERVICE_NAME,
                    "level": "WARN",
                    "message": "CHAOS: Exclusive table lock acquired for 5 seconds",
                    "trace_id": trace_id,
                }))
                await asyncio.sleep(5)

        return {"chaos": "lock", "duration_seconds": 5, "status": "completed"}

    elif body.mode == "sleep":
        logger.info(json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": SERVICE_NAME,
            "level": "WARN",
            "message": "CHAOS: Sleeping 5 seconds to simulate network degradation",
            "trace_id": trace_id,
        }))
        await asyncio.sleep(5)
        return {"chaos": "sleep", "duration_seconds": 5, "status": "completed"}

    else:
        raise HTTPException(status_code=400, detail=f"Unknown chaos mode: {body.mode}")


@app.get("/health")
async def health():
    """Health check — also verifies DB connectivity."""
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "healthy", "service": SERVICE_NAME, "database": "connected"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database unreachable: {exc}")
