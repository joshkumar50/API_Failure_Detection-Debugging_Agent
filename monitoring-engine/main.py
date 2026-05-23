"""
Monitoring Engine — Stellar AI Observability Platform
Real-time log ingestion, Z-Score anomaly detection, and incident correlation.
"""

from __future__ import annotations

import json
import logging
import math
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Request
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger("monitoring-engine")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(asctime)s [monitoring-engine] %(levelname)s %(message)s"))
logger.handlers = [handler]

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="Monitoring Engine", version="1.0.0")

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class LogEntry(BaseModel):
    timestamp: str
    service: str
    endpoint: str = ""
    method: str = ""
    status_code: int = 200
    latency_ms: float = 0.0
    level: str = "INFO"
    message: str = ""
    trace_id: str = ""


class AnomalyRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str
    service: str
    endpoint: str
    latency_ms: float
    z_score: float
    mean_ms: float
    std_ms: float
    log_entry: dict


class Incident(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    severity: str = "HIGH"
    title: str = ""
    description: str = ""
    anomalies: list[dict] = Field(default_factory=list)
    correlated_errors: list[dict] = Field(default_factory=list)
    trace_ids: list[str] = Field(default_factory=list)
    services_affected: list[str] = Field(default_factory=list)
    resolved: bool = False


# ---------------------------------------------------------------------------
# In-memory stores (thread-safe via GIL for single-process uvicorn)
# ---------------------------------------------------------------------------

# Rolling latency windows per service (last 100)
_latency_windows: dict[str, deque[float]] = {}
_WINDOW_SIZE = 100

# Recent log buffer for correlation (last 500 entries)
_log_buffer: deque[dict] = deque(maxlen=2000)

# Anomaly records
_anomalies: list[AnomalyRecord] = []

# Incidents
_incidents: list[Incident] = []

# Metrics counters
_metrics: dict[str, Any] = {
    "total_logs_ingested": 0,
    "total_anomalies": 0,
    "total_incidents": 0,
    "logs_per_second": 0.0,
    "per_service": {},
}
_log_timestamps: deque[float] = deque(maxlen=1000)

# Lock for incident creation to prevent duplicates
_incident_lock = threading.Lock()

# Global chaos switch
_chaos_enabled = True


# ---------------------------------------------------------------------------
# Z-Score Engine
# ---------------------------------------------------------------------------

def _compute_z_score(service: str, latency_ms: float) -> float | None:
    """
    Compute Z-score for a latency value against the rolling window for a service.
    Returns None if insufficient data (< 10 samples).
    """
    if service not in _latency_windows:
        _latency_windows[service] = deque(maxlen=_WINDOW_SIZE)

    window = _latency_windows[service]

    # Need at least 10 data points for meaningful statistics
    if len(window) < 10:
        window.append(latency_ms)
        return None

    # Compute mean and std
    n = len(window)
    mean = sum(window) / n
    variance = sum((x - mean) ** 2 for x in window) / n
    std = math.sqrt(variance) if variance > 0 else 0.0

    # Append AFTER computing (so current value doesn't pollute its own score)
    window.append(latency_ms)

    if std < 0.001:
        # All values are effectively identical — no meaningful deviation
        return 0.0

    z_score = (latency_ms - mean) / std
    return round(z_score, 3)


# ---------------------------------------------------------------------------
# Incident Correlation Engine
# ---------------------------------------------------------------------------

def _try_correlate(anomaly: AnomalyRecord, log_entry: dict) -> None:
    """
    Check if this anomaly correlates with recent errors (same trace_id or
    errors within 2 seconds). If so, create or update an Incident.
    """
    anomaly_time = time.time()
    trace_id = log_entry.get("trace_id", "")

    # Find correlated errors in recent log buffer
    correlated_errors: list[dict] = []
    correlated_trace_ids: set[str] = set()
    if trace_id:
        correlated_trace_ids.add(trace_id)

    for buffered in _log_buffer:
        # Correlate by trace_id
        if trace_id and buffered.get("trace_id") == trace_id and buffered.get("status_code", 200) >= 400:
            correlated_errors.append(buffered)
            continue

        # Correlate by time proximity (within 2 seconds) for errors
        if buffered.get("status_code", 200) >= 400:
            try:
                buf_time = datetime.fromisoformat(buffered.get("timestamp", ""))
                anomaly_dt = datetime.fromisoformat(anomaly.timestamp)
                delta = abs((anomaly_dt - buf_time).total_seconds())
                if delta <= 2.0:
                    correlated_errors.append(buffered)
                    if buffered.get("trace_id"):
                        correlated_trace_ids.add(buffered["trace_id"])
            except (ValueError, TypeError):
                pass

    # Determine affected services
    services_affected = {anomaly.service}
    for err in correlated_errors:
        if err.get("service"):
            services_affected.add(err["service"])

    # Check if this should be merged into an existing recent incident
    with _incident_lock:
        # Look for an open incident within the last 5 seconds with overlapping trace_ids
        for existing in reversed(_incidents[-20:]):
            if existing.resolved:
                continue
            try:
                existing_time = datetime.fromisoformat(existing.created_at)
                delta = abs((datetime.now(timezone.utc) - existing_time).total_seconds())
                if delta <= 5.0:
                    # Merge if there's trace overlap
                    if correlated_trace_ids & set(existing.trace_ids):
                        existing.anomalies.append(anomaly.model_dump())
                        existing.correlated_errors.extend(correlated_errors)
                        existing.trace_ids = list(set(existing.trace_ids) | correlated_trace_ids)
                        existing.services_affected = list(
                            set(existing.services_affected) | services_affected
                        )
                        logger.info(f"🔗 Merged anomaly into existing incident {existing.id[:8]}")
                        return
            except (ValueError, TypeError):
                pass

        # Create new incident if we have correlated errors or high z-score
        if correlated_errors or anomaly.z_score > 4.0:
            incident = Incident(
                title=f"Latency anomaly on {anomaly.service}{anomaly.endpoint} "
                      f"(Z={anomaly.z_score:.1f}, {anomaly.latency_ms:.0f}ms)",
                description=(
                    f"Detected anomalous latency of {anomaly.latency_ms:.1f}ms "
                    f"(Z-score: {anomaly.z_score:.2f}, mean: {anomaly.mean_ms:.1f}ms, "
                    f"std: {anomaly.std_ms:.1f}ms) on {anomaly.service}. "
                    f"{len(correlated_errors)} correlated error(s) found."
                ),
                severity="CRITICAL" if anomaly.z_score > 5.0 else "HIGH",
                anomalies=[anomaly.model_dump()],
                correlated_errors=correlated_errors[:20],  # Cap at 20
                trace_ids=list(correlated_trace_ids),
                services_affected=list(services_affected),
            )
            _incidents.append(incident)
            _metrics["total_incidents"] += 1
            logger.warning(
                f"🚨 NEW INCIDENT {incident.id[:8]}: {incident.title} "
                f"| {len(correlated_errors)} errors correlated"
            )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.post("/ingest")
async def ingest(entry: LogEntry):
    """Ingest a structured log entry, run Z-score detection, attempt correlation."""
    _metrics["total_logs_ingested"] += 1
    _log_timestamps.append(time.time())

    entry_dict = entry.model_dump()
    _log_buffer.append(entry_dict)

    # Track per-service metrics
    svc = entry.service
    if svc not in _metrics["per_service"]:
        _metrics["per_service"][svc] = {
            "total_requests": 0,
            "total_errors": 0,
            "avg_latency_ms": 0.0,
            "latest_latencies": [],
        }
    svc_metrics = _metrics["per_service"][svc]
    svc_metrics["total_requests"] += 1
    if entry.status_code >= 400:
        svc_metrics["total_errors"] += 1

    # Track latest latencies for charting (last 60 data points)
    svc_metrics["latest_latencies"].append({
        "timestamp": entry.timestamp,
        "latency_ms": entry.latency_ms,
        "status_code": entry.status_code,
    })
    if len(svc_metrics["latest_latencies"]) > 200:
        svc_metrics["latest_latencies"] = svc_metrics["latest_latencies"][-200:]

    # Running average
    total = svc_metrics["total_requests"]
    svc_metrics["avg_latency_ms"] = round(
        svc_metrics["avg_latency_ms"] * (total - 1) / total + entry.latency_ms / total, 2
    )

    # Z-Score anomaly detection
    z_score = _compute_z_score(svc, entry.latency_ms)
    if z_score is not None and z_score > 3.0:
        window = _latency_windows.get(svc, deque())
        n = len(window)
        mean = sum(window) / n if n > 0 else 0
        variance = sum((x - mean) ** 2 for x in window) / n if n > 0 else 0
        std = math.sqrt(variance)

        anomaly = AnomalyRecord(
            timestamp=entry.timestamp,
            service=svc,
            endpoint=entry.endpoint,
            latency_ms=entry.latency_ms,
            z_score=z_score,
            mean_ms=round(mean, 2),
            std_ms=round(std, 2),
            log_entry=entry_dict,
        )
        _anomalies.append(anomaly)
        _metrics["total_anomalies"] += 1

        logger.warning(
            f"⚡ ANOMALY: {svc}{entry.endpoint} latency={entry.latency_ms:.1f}ms "
            f"Z={z_score:.2f} (mean={mean:.1f}, std={std:.1f})"
        )

        # Try to correlate into an incident
        _try_correlate(anomaly, entry_dict)

    return {"status": "ingested"}


@app.get("/metrics")
async def get_metrics():
    """Return current system metrics."""
    # Compute logs/sec over last 10 seconds
    now = time.time()
    recent = sum(1 for t in _log_timestamps if now - t <= 10)
    _metrics["logs_per_second"] = round(recent / 10, 1)

    return _metrics


@app.get("/incidents")
async def get_incidents(limit: int = 50, unresolved_only: bool = False):
    """Return recent incidents, newest first, with auto-resolution check."""
    now_dt = datetime.now(timezone.utc)
    
    # Auto-resolve incidents that have seen no anomalies/updates for 15 seconds (Nominal auto-healing)
    with _incident_lock:
        for incident in _incidents:
            if not incident.resolved:
                try:
                    time_str = incident.anomalies[-1].get("timestamp") if incident.anomalies else incident.created_at
                    dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                    if (now_dt - dt).total_seconds() > 15.0:
                        incident.resolved = True
                        logger.info(f"🍃 Incident {incident.id[:8]} automatically resolved after 15s of nominal state")
                except Exception as exc:
                    logger.warning(f"Error parsing date for auto-resolve: {exc}")

    results = _incidents
    if unresolved_only:
        results = [i for i in results if not i.resolved]
    # Return newest first, limited
    return [i.model_dump() for i in reversed(results[-limit:])]


@app.post("/incidents/{incident_id}/resolve")
async def resolve_incident(incident_id: str):
    """Manually resolve an active incident."""
    with _incident_lock:
        for incident in _incidents:
            if incident.id == incident_id:
                incident.resolved = True
                logger.info(f"✅ Incident {incident_id[:8]} marked as RESOLVED manually")
                return {"status": "resolved", "incident_id": incident_id}
    raise HTTPException(status_code=404, detail="Incident not found")


@app.get("/anomalies")
async def get_anomalies(limit: int = 100):
    """Return recent anomaly records."""
    return [a.model_dump() for a in reversed(_anomalies[-limit:])]


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "monitoring-engine",
        "total_ingested": _metrics["total_logs_ingested"],
        "total_anomalies": _metrics["total_anomalies"],
        "total_incidents": _metrics["total_incidents"],
    }


@app.get("/chaos/status")
async def get_chaos_status():
    return {"enabled": _chaos_enabled}


@app.post("/chaos/toggle")
async def toggle_chaos():
    global _chaos_enabled
    _chaos_enabled = not _chaos_enabled
    logger.info(f"🛑 Chaos switch toggled. New state: enabled={_chaos_enabled}")
    return {"enabled": _chaos_enabled}


@app.post("/reset")
async def reset_monitoring_state():
    """Clear all in-memory incidents, anomalies, buffers, and metrics counters."""
    global _anomalies, _incidents, _latency_windows, _log_buffer
    with _incident_lock:
        _anomalies = []
        _incidents = []
        _latency_windows = {}
        _log_buffer.clear()
        
        # Reset counters
        _metrics["total_logs_ingested"] = 0
        _metrics["total_anomalies"] = 0
        _metrics["total_incidents"] = 0
        _metrics["logs_per_second"] = 0.0
        _metrics["per_service"] = {}
        
        logger.info("🗑️ Monitoring engine state cleared successfully")
    return {"status": "cleared"}

