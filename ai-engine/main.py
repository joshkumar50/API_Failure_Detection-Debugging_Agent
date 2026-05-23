"""
AI Engine — Stellar AI Observability Platform
Accepts Incident objects and uses Google Gemini to generate Root Cause Analysis.
Falls back to a structured heuristic analysis if no API key is configured.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3")
SERVICE_NAME: str = "ai-engine"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger(SERVICE_NAME)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(asctime)s [ai-engine] %(levelname)s %(message)s"))
logger.handlers = [handler]

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="AI Engine", version="1.0.0")

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class IncidentPayload(BaseModel):
    id: str = ""
    created_at: str = ""
    severity: str = "HIGH"
    title: str = ""
    description: str = ""
    anomalies: list[dict] = Field(default_factory=list)
    correlated_errors: list[dict] = Field(default_factory=list)
    trace_ids: list[str] = Field(default_factory=list)
    services_affected: list[str] = Field(default_factory=list)
    resolved: bool = False


class RCAResponse(BaseModel):
    incident_id: str
    root_cause: str
    analysis: str
    fix_steps: list[str]
    severity_assessment: str
    generated_at: str
    model_used: str


# ---------------------------------------------------------------------------
# Gemini LLM integration
# ---------------------------------------------------------------------------

def _build_prompt(incident: IncidentPayload) -> str:
    """Build a detailed SRE analysis prompt from incident data."""
    anomaly_details = ""
    for i, a in enumerate(incident.anomalies[:5], 1):
        anomaly_details += (
            f"  Anomaly {i}: service={a.get('service','?')}, "
            f"endpoint={a.get('endpoint','?')}, "
            f"latency={a.get('latency_ms','?')}ms, "
            f"z_score={a.get('z_score','?')}, "
            f"mean={a.get('mean_ms','?')}ms, "
            f"std={a.get('std_ms','?')}ms\n"
        )

    error_details = ""
    for i, e in enumerate(incident.correlated_errors[:10], 1):
        error_details += (
            f"  Error {i}: service={e.get('service','?')}, "
            f"endpoint={e.get('endpoint','?')}, "
            f"status={e.get('status_code','?')}, "
            f"latency={e.get('latency_ms','?')}ms, "
            f"message={e.get('message','?')}\n"
        )

    return f"""You are a Senior Site Reliability Engineer (SRE) analyzing a production incident
in a distributed microservices platform. The platform consists of: auth-service (JWT authentication),
payment-service (payment processing with PostgreSQL), and supporting infrastructure.

INCIDENT REPORT:
  ID: {incident.id}
  Severity: {incident.severity}
  Title: {incident.title}
  Description: {incident.description}
  Services Affected: {', '.join(incident.services_affected)}
  Trace IDs: {', '.join(incident.trace_ids[:5])}

ANOMALIES DETECTED:
{anomaly_details if anomaly_details else '  None recorded'}

CORRELATED ERRORS:
{error_details if error_details else '  None recorded'}

Analyze this incident and respond with EXACTLY this JSON structure (no markdown, no code fences):
{{
  "root_cause": "A single sentence identifying the root cause",
  "analysis": "A detailed 2-3 paragraph technical analysis of what happened, why, and the blast radius",
  "fix_steps": ["Step 1: ...", "Step 2: ...", "Step 3: ..."],
  "severity_assessment": "CRITICAL/HIGH/MEDIUM/LOW with justification"
}}"""


async def _analyze_with_gemini(incident: IncidentPayload) -> dict:
    """Call Google Gemini API for root cause analysis."""
    import google.generativeai as genai

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.0-flash")

    prompt = _build_prompt(incident)

    response = model.generate_content(prompt)
    text = response.text.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # If Gemini returns non-JSON, wrap it
        return {
            "root_cause": "See analysis",
            "analysis": text,
            "fix_steps": [
                "Step 1: Review the detailed analysis above",
                "Step 2: Check service health and database connections",
                "Step 3: Scale impacted services and implement circuit breakers",
            ],
            "severity_assessment": incident.severity,
        }


def _analyze_with_ollama(incident: IncidentPayload) -> dict:
    """Call local Ollama instance for root cause analysis."""
    import requests

    prompt = _build_prompt(incident)
    
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json"
    }

    response = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json=payload,
        timeout=(3.0, 30.0)  # 3s connect timeout, 30s read timeout
    )
    response.raise_for_status()
    
    data = response.json()
    text = data.get("response", "").strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {
            "root_cause": "See analysis",
            "analysis": text,
            "fix_steps": [
                "Step 1: Review the detailed analysis above",
                "Step 2: Check service health and database connections",
                "Step 3: Scale impacted services and implement circuit breakers",
            ],
            "severity_assessment": incident.severity,
        }

def _analyze_with_groq(incident: IncidentPayload) -> dict:
    """Call Groq API (OpenAI compatible) for root cause analysis."""
    import requests

    prompt = _build_prompt(incident)
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2
    }

    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        json=payload,
        headers=headers,
        timeout=10.0
    )
    response.raise_for_status()
    data = response.json()
    text = data["choices"][0]["message"]["content"].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {
            "root_cause": "See analysis",
            "analysis": text,
            "fix_steps": [
                "Step 1: Review the detailed analysis above",
                "Step 2: Check service health and database connections",
                "Step 3: Scale impacted services and implement circuit breakers",
            ],
            "severity_assessment": incident.severity,
        }


def _analyze_heuristic(incident: IncidentPayload) -> dict:
    """Fallback heuristic analysis when no LLM API key is configured."""
    # Analyze patterns from the incident data
    services = incident.services_affected
    anomalies = incident.anomalies
    errors = incident.correlated_errors

    # Detect common patterns
    has_db_latency = any(
        a.get("latency_ms", 0) > 1000 and a.get("service") == "payment-service"
        for a in anomalies
    )
    has_auth_errors = any(
        e.get("status_code") == 401 for e in errors
    )
    has_cascade = len(services) > 1
    max_latency = max((a.get("latency_ms", 0) for a in anomalies), default=0)
    max_z = max((a.get("z_score", 0) for a in anomalies), default=0)
    error_count = len(errors)

    if has_db_latency:
        root_cause = "Database contention or table lock causing cascading latency in payment-service"
        analysis = (
            f"Detected {len(anomalies)} latency anomalies with max latency of {max_latency:.0f}ms "
            f"(Z-score: {max_z:.1f}) on payment-service. This pattern is consistent with a database "
            f"table lock (ACCESS EXCLUSIVE MODE) blocking concurrent transaction INSERTs. "
            f"{error_count} correlated errors were observed across {len(services)} service(s). "
            f"The lock caused request queuing, connection pool exhaustion, and eventual timeouts "
            f"propagating to upstream callers."
        )
        fix_steps = [
            "Step 1: Release the database lock — check pg_locks and terminate the blocking session with pg_terminate_backend()",
            "Step 2: Implement connection pool monitoring and circuit breakers on payment-service to shed load during contention",
            "Step 3: Add database lock timeout (SET lock_timeout = '3s') to prevent indefinite waits",
        ]
    elif has_auth_errors:
        root_cause = "Authentication failures causing cascading 401 errors across the request chain"
        analysis = (
            f"Detected {error_count} authentication errors (HTTP 401) correlated with "
            f"{len(anomalies)} latency anomalies. Invalid or expired JWT tokens are being "
            f"rejected by auth-service, causing payment-service requests to fail. "
            f"This may indicate a token refresh issue, clock skew, or an intentional invalid "
            f"token injection."
        )
        fix_steps = [
            "Step 1: Verify JWT token expiry settings and ensure client-side token refresh is functioning",
            "Step 2: Check for clock synchronization issues between services (NTP drift)",
            "Step 3: Implement token caching with graceful refresh to prevent thundering herd on auth-service",
        ]
    else:
        root_cause = f"Latency spike detected across {', '.join(services)} with Z-score {max_z:.1f}"
        analysis = (
            f"Observed {len(anomalies)} anomalous requests with latencies up to {max_latency:.0f}ms "
            f"(Z-score: {max_z:.1f}). {error_count} correlated errors found. "
            f"The spike pattern suggests either a resource exhaustion event (CPU, memory, connections) "
            f"or a burst of concurrent traffic overwhelming the service capacity."
        )
        fix_steps = [
            "Step 1: Check resource utilization (CPU, memory, connection pools) on affected services",
            "Step 2: Review recent deployments or configuration changes that may have introduced the regression",
            "Step 3: Implement rate limiting and auto-scaling policies to handle traffic bursts",
        ]

    severity = "CRITICAL" if max_z > 5 or has_cascade else "HIGH"

    return {
        "root_cause": root_cause,
        "analysis": analysis,
        "fix_steps": fix_steps,
        "severity_assessment": f"{severity} — Max Z-score: {max_z:.1f}, Errors: {error_count}, Services: {len(services)}",
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.post("/analyze", response_model=RCAResponse)
async def analyze(incident: IncidentPayload):
    """Analyze an incident and return root cause analysis."""
    logger.info(f"🔍 Analyzing incident {incident.id[:8] if incident.id else 'unknown'}...")

    model_used = "heuristic-fallback"

    try:
        if GEMINI_API_KEY:
            result = await _analyze_with_gemini(incident)
            model_used = "gemini-2.0-flash"
            logger.info(f"✅ Gemini analysis complete for incident {incident.id[:8]}")
        else:
            raise Exception("No GEMINI_API_KEY set")
    except Exception as gemini_exc:
        logger.warning(f"⚠️ Gemini analysis failed or unavailable: {gemini_exc}. Attempting Groq fallback...")
        try:
            if GROQ_API_KEY:
                result = _analyze_with_groq(incident)
                model_used = "groq/llama-3.1-8b-instant"
                logger.info(f"✅ Groq analysis complete for incident {incident.id[:8]}")
            else:
                raise Exception("No GROQ_API_KEY set")
        except Exception as groq_exc:
            logger.warning(f"⚠️ Groq analysis failed or unavailable: {groq_exc}. Attempting Ollama fallback...")
            try:
                result = _analyze_with_ollama(incident)
                model_used = OLLAMA_MODEL
                logger.info(f"✅ Ollama analysis complete for incident {incident.id[:8]}")
            except Exception as ollama_exc:
                logger.error(f"❌ Ollama analysis failed: {ollama_exc}. Falling back to heuristics")
                result = _analyze_heuristic(incident)

    return RCAResponse(
        incident_id=incident.id,
        root_cause=result.get("root_cause", "Unknown"),
        analysis=result.get("analysis", "Analysis unavailable"),
        fix_steps=result.get("fix_steps", []),
        severity_assessment=result.get("severity_assessment", incident.severity),
        generated_at=datetime.now(timezone.utc).isoformat(),
        model_used=model_used,
    )


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": SERVICE_NAME,
        "llm_configured": bool(GEMINI_API_KEY),
    }
