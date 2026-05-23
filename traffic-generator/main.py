"""
Traffic Generator — Stellar AI Observability Platform
Generates organic, high-concurrency traffic against auth-service and payment-service.
Periodically injects controlled anomalies (invalid tokens, burst floods).
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import sys
import time
import uuid

import httpx

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
AUTH_URL: str = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8001")
PAYMENT_URL: str = os.getenv("PAYMENT_SERVICE_URL", "http://payment-service:8002")

NORMAL_RPS: int = int(os.getenv("NORMAL_RPS", "15"))  # 10-20 range
CHAOS_INTERVAL_S: int = int(os.getenv("CHAOS_INTERVAL_S", "60"))
BURST_SIZE: int = int(os.getenv("BURST_SIZE", "500"))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [traffic-generator] %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("traffic-generator")

# ---------------------------------------------------------------------------
# Globals
# ---------------------------------------------------------------------------
_current_token: str | None = None
_request_count: int = 0
_error_count: int = 0


async def wait_for_services(client: httpx.AsyncClient) -> None:
    """Block until both auth-service and payment-service are healthy."""
    services = {
        "auth-service": f"{AUTH_URL}/health",
        "payment-service": f"{PAYMENT_URL}/health",
    }
    for name, url in services.items():
        while True:
            try:
                r = await client.get(url, timeout=3.0)
                if r.status_code == 200:
                    log.info(f"✓ {name} is healthy")
                    break
            except Exception:
                pass
            log.info(f"⏳ Waiting for {name}...")
            await asyncio.sleep(2)


async def obtain_token(client: httpx.AsyncClient) -> str:
    """Login to auth-service and return a valid bearer token."""
    trace_id = str(uuid.uuid4())
    resp = await client.post(
        f"{AUTH_URL}/login",
        json={"username": "load-tester", "password": "test-password"},
        headers={"x-trace-id": trace_id},
    )
    resp.raise_for_status()
    token = resp.json()["access_token"]
    log.info(f"🔑 Obtained fresh JWT token (trace={trace_id[:8]})")
    return token


async def fire_payment(
    client: httpx.AsyncClient,
    token: str,
    trace_id: str | None = None,
) -> int:
    """Send a single /pay request. Returns status code."""
    global _request_count, _error_count
    if trace_id is None:
        trace_id = str(uuid.uuid4())
    try:
        resp = await client.post(
            f"{PAYMENT_URL}/pay",
            json={
                "amount": round(random.uniform(1.0, 500.0), 2),
                "currency": random.choice(["USD", "EUR", "GBP"]),
                "description": f"load-test-txn-{uuid.uuid4().hex[:8]}",
            },
            headers={
                "Authorization": f"Bearer {token}",
                "x-trace-id": trace_id,
            },
            timeout=10.0,
        )
        _request_count += 1
        if resp.status_code >= 400:
            _error_count += 1
        return resp.status_code
    except Exception as exc:
        _request_count += 1
        _error_count += 1
        log.warning(f"Request failed: {exc}")
        return 0


async def normal_traffic_loop(client: httpx.AsyncClient) -> None:
    """Continuous loop: fire NORMAL_RPS payments per second with valid tokens."""
    global _current_token

    _current_token = await obtain_token(client)
    # Refresh token every 10 minutes
    token_refresh_interval = 600
    last_refresh = time.monotonic()

    while True:
        # Refresh token periodically
        if time.monotonic() - last_refresh > token_refresh_interval:
            try:
                _current_token = await obtain_token(client)
                last_refresh = time.monotonic()
            except Exception as exc:
                log.error(f"Token refresh failed: {exc}")

        # Check if chaos is enabled. If not, scale down RPS to 1 to prevent organic CPU/DB queuing anomalies.
        current_rps = NORMAL_RPS
        try:
            resp = await client.get("http://monitoring-engine:8005/chaos/status", timeout=2.0)
            if resp.status_code == 200:
                enabled = resp.json().get("enabled", True)
                if not enabled:
                    current_rps = 1
        except Exception:
            pass

        # Fire a batch of requests spread over 1 second
        tasks = []
        for _ in range(current_rps):
            tasks.append(fire_payment(client, _current_token))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        statuses = [r for r in results if isinstance(r, int)]

        ok = sum(1 for s in statuses if 200 <= s < 300)
        fail = sum(1 for s in statuses if s >= 400 or s == 0)
        log.info(
            f"📊 Batch: {len(statuses)} reqs | {ok} ok | {fail} fail | "
            f"Total: {_request_count} reqs, {_error_count} errors"
        )

        # Pace to ~1 second per batch
        await asyncio.sleep(1.0)


async def chaos_loop(client: httpx.AsyncClient) -> None:
    """Periodically inject anomalies to generate organic errors and latency spikes."""
    global _current_token

    # Wait a bit before starting chaos
    await asyncio.sleep(15)

    cycle = 0
    while True:
        await asyncio.sleep(CHAOS_INTERVAL_S)

        # Query monitoring engine to check if chaos is enabled
        try:
            resp = await client.get("http://monitoring-engine:8005/chaos/status", timeout=2.0)
            if resp.status_code == 200:
                enabled = resp.json().get("enabled", True)
                if not enabled:
                    log.info("💤 Background chaos is disabled. Skipping cycle.")
                    continue
        except Exception as exc:
            log.warning(f"Could not verify chaos status from monitoring-engine: {exc}. Proceeding by default.")

        cycle += 1

        if cycle % 2 == 1:
            # === Anomaly Type 1: Invalid token burst ===
            log.warning("💥 CHAOS: Sending burst of INVALID token requests")
            invalid_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.INVALID.PAYLOAD"
            tasks = []
            for _ in range(20):
                trace_id = str(uuid.uuid4())
                tasks.append(fire_payment(client, invalid_token, trace_id))
            await asyncio.gather(*tasks, return_exceptions=True)
            log.warning("💥 CHAOS: Invalid token burst complete — expect 401s in logs")

        else:
            # === Anomaly Type 2: Concurrent flood ===
            log.warning(f"🌊 CHAOS: Launching {BURST_SIZE} concurrent requests")
            if _current_token is None:
                _current_token = await obtain_token(client)

            tasks = []
            for _ in range(BURST_SIZE):
                trace_id = str(uuid.uuid4())
                tasks.append(fire_payment(client, _current_token, trace_id))

            start = time.monotonic()
            await asyncio.gather(*tasks, return_exceptions=True)
            elapsed = time.monotonic() - start
            log.warning(
                f"🌊 CHAOS: Flood complete — {BURST_SIZE} reqs in {elapsed:.2f}s "
                f"({BURST_SIZE / elapsed:.0f} rps)"
            )


async def main() -> None:
    log.info("🚀 Traffic Generator starting up...")

    async with httpx.AsyncClient() as client:
        await wait_for_services(client)

        log.info(
            f"✅ All services healthy. Starting traffic at ~{NORMAL_RPS} rps "
            f"with chaos every ~{CHAOS_INTERVAL_S}s"
        )

        # Run normal traffic and chaos injection concurrently
        await asyncio.gather(
            normal_traffic_loop(client),
            chaos_loop(client),
        )


if __name__ == "__main__":
    asyncio.run(main())
