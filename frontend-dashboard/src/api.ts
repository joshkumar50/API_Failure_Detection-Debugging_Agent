/**
 * Stellar AI Observability Platform — API Client
 *
 * All requests go through the Nginx reverse proxy at the same origin,
 * so no CORS configuration is needed.
 *
 * Route mapping (Nginx):
 *   /api/auth/*       → http://auth-service:8001/*
 *   /api/payment/*    → http://payment-service:8002/*
 *   /api/monitoring/* → http://monitoring-engine:8005/*
 *   /api/ai/*         → http://ai-engine:8006/*
 */

// ── Types ──────────────────────────────────────────────────────

export interface LogEntry {
  timestamp: string;
  service: string;
  endpoint: string;
  method: string;
  status_code: number;
  latency_ms: number;
  level: string;
  message: string;
  trace_id: string;
}

export interface ServiceMetrics {
  total_requests: number;
  total_errors: number;
  avg_latency_ms: number;
  latest_latencies: {
    timestamp: string;
    latency_ms: number;
    status_code: number;
  }[];
}

export interface MetricsResponse {
  total_logs_ingested: number;
  total_anomalies: number;
  total_incidents: number;
  logs_per_second: number;
  per_service: Record<string, ServiceMetrics>;
}

export interface Anomaly {
  id: string;
  timestamp: string;
  service: string;
  endpoint: string;
  latency_ms: number;
  z_score: number;
  mean_ms: number;
  std_ms: number;
  log_entry: Record<string, unknown>;
}

export interface Incident {
  id: string;
  created_at: string;
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  title: string;
  description: string;
  anomalies: Anomaly[];
  correlated_errors: Record<string, unknown>[];
  trace_ids: string[];
  services_affected: string[];
  resolved: boolean;
}

export interface RCAResponse {
  incident_id: string;
  root_cause: string;
  analysis: string;
  fix_steps: string[];
  severity_assessment: string;
  generated_at: string;
  model_used: string;
}

export interface HealthResponse {
  status: string;
  service: string;
  [key: string]: unknown;
}

// ── API Functions ──────────────────────────────────────────────

async function safeFetch<T>(url: string, options?: RequestInit): Promise<T | null> {
  try {
    const res = await fetch(url, options);
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export const API = {
  /** Fetch recent logs from the monitoring engine for the terminal view. */
  getLogs(limit = 200): Promise<LogEntry[] | null> {
    return safeFetch<LogEntry[]>(`/api/monitoring/logs?limit=${limit}`);
  },

  /** Fetch current system metrics from the monitoring engine. */
  getMetrics(): Promise<MetricsResponse | null> {
    return safeFetch<MetricsResponse>('/api/monitoring/metrics');
  },

  /** Fetch recent incidents from the monitoring engine. */
  getIncidents(limit = 50): Promise<Incident[] | null> {
    return safeFetch<Incident[]>(`/api/monitoring/incidents?limit=${limit}`);
  },

  /** Mark an active incident as manually resolved. */
  async resolveIncident(incidentId: string): Promise<{ status: string } | null> {
    try {
      const res = await fetch(`/api/monitoring/incidents/${incidentId}/resolve`, {
        method: 'POST',
      });
      if (!res.ok) return null;
      return await res.json();
    } catch {
      return null;
    }
  },

  /** Ping a service's health endpoint. */
  getHealth(proxyPrefix: string): Promise<HealthResponse | null> {
    return safeFetch<HealthResponse>(`/api/${proxyPrefix}/health`);
  },

  /** Login to get a JWT token (for chaos injection). */
  async login(username: string, password: string): Promise<string | null> {
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      if (!res.ok) return null;
      const data = await res.json();
      return data.access_token ?? null;
    } catch {
      return null;
    }
  },

  /** Fetch background chaos status from the monitoring engine. */
  getChaosStatus(): Promise<{ enabled: boolean } | null> {
    return safeFetch<{ enabled: boolean }>('/api/monitoring/chaos/status');
  },

  /** Toggle background chaos injection. */
  toggleChaos(): Promise<{ enabled: boolean } | null> {
    return safeFetch<{ enabled: boolean }>('/api/monitoring/chaos/toggle', {
      method: 'POST',
    });
  },

  /** Trigger chaos injection on the payment service. */
  async triggerChaos(mode: string, token: string): Promise<{ success: boolean; message: string }> {
    try {
      const res = await fetch('/api/payment/inject-chaos', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ mode }),
      });
      if (res.ok) {
        return { success: true, message: `Successfully injected '${mode}' chaos!` };
      }
      const text = await res.text();
      return { success: false, message: `Chaos endpoint returned ${res.status}: ${text}` };
    } catch (err) {
      return { success: false, message: `Error calling chaos endpoint: ${err}` };
    }
  },

  /** Request AI root cause analysis for an incident. */
  analyzeIncident(incident: Incident): Promise<RCAResponse | null> {
    return safeFetch<RCAResponse>('/api/ai/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(incident),
    });
  },

  /** Clear all incidents, anomalies, metrics, and logs in the monitoring engine. */
  clearAllState(): Promise<{ status: string } | null> {
    return safeFetch<{ status: string }>('/api/monitoring/reset', {
      method: 'POST',
    });
  },
};
