import { useState, useCallback, useRef, useEffect } from 'react';
import { API, type MetricsResponse, type Incident } from './api';
import { usePolling } from './hooks/usePolling';
import { MetricCard } from './components/MetricCard';
import { ServiceHealth } from './components/ServiceHealth';
import { ChaosControl } from './components/ChaosControl';
import { LiveCharts } from './components/LiveCharts';
import { IncidentBoard } from './components/IncidentBoard';
import { TerminalModal } from './components/TerminalModal';
import './App.css';

// ── Toast System ───────────────────────────────────────────────

interface Toast {
  id: number;
  type: 'success' | 'error';
  message: string;
}

let toastId = 0;

function App() {
  // ── State ────────────────────────────────────────────────────
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [metricsHistory, setMetricsHistory] = useState<MetricsResponse[]>([]);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [isTerminalOpen, setIsTerminalOpen] = useState(false);
  const [terminalTab, setTerminalTab] = useState<'logs' | 'containers'>('logs');

  // ── Polling ──────────────────────────────────────────────────
  const getMetrics = useCallback(() => API.getMetrics(), []);
  const getIncidents = useCallback(() => API.getIncidents(), []);

  const { data: metrics } = usePolling<MetricsResponse>(getMetrics, 3000, autoRefresh);
  const { data: incidents } = usePolling<Incident[]>(getIncidents, 3000, autoRefresh);

  // ── Metrics History (rolling 40 points) ──────────────────────
  const prevMetricsRef = useRef<MetricsResponse | null>(null);

  useEffect(() => {
    if (metrics && metrics !== prevMetricsRef.current) {
      prevMetricsRef.current = metrics;
      setMetricsHistory((prev) => [...prev, metrics].slice(-40));
    }
  }, [metrics]);

  // ── Toast Handler ────────────────────────────────────────────
  const handleToast = useCallback((type: 'success' | 'error', message: string) => {
    const id = ++toastId;
    setToasts((prev) => [...prev, { id, type, message }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  }, []);

  // ── Derived Values ───────────────────────────────────────────
  const authLatency = metrics?.per_service?.['auth-service']?.avg_latency_ms ?? 0;
  const payLatency = metrics?.per_service?.['payment-service']?.avg_latency_ms ?? 0;
  const throughput = metrics?.logs_per_second ?? 0;
  const totalIncidents = metrics?.total_incidents ?? 0;
  const totalAnomalies = metrics?.total_anomalies ?? 0;

  return (
    <div className="app">
      {/* ── Sidebar ──────────────────────────────────────────── */}
      <aside className="sidebar">
        <div className="sidebar__inner">
          {/* Logo / Title */}
          <div className="sidebar__brand">
            <span className="sidebar__logo">
              <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="url(#logo-grad)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ display: 'block' }}>
                <defs>
                  <linearGradient id="logo-grad" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stopColor="var(--accent-blue)" />
                    <stop offset="100%" stopColor="var(--accent-purple)" />
                  </linearGradient>
                </defs>
                <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
              </svg>
            </span>
            <div>
              <h1 className="sidebar__title gradient-text">Stellar</h1>
              <p className="sidebar__subtitle">AI Observability Platform</p>
            </div>
          </div>

          <hr className="divider" />

          {/* Service Health */}
          <ServiceHealth activeIncidents={incidents ?? []} />

          <hr className="divider" />

          {/* Chaos Controls */}
          <ChaosControl onToast={handleToast} />

          <hr className="divider" />

          {/* Terminal View */}
          <div style={{ padding: '0 var(--space-xs)', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <button 
              className="btn" 
              style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', background: 'var(--bg-primary)', color: 'var(--text-primary)', border: '1px solid var(--glass-border)' }}
              onClick={() => { setTerminalTab('logs'); setIsTerminalOpen(true); }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="4 17 10 11 4 5"></polyline>
                <line x1="12" y1="19" x2="20" y2="19"></line>
              </svg>
              View Container Logs
            </button>
            <button 
              className="btn" 
              style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', background: 'var(--bg-primary)', color: 'var(--text-primary)', border: '1px solid var(--glass-border)' }}
              onClick={() => { setTerminalTab('containers'); setIsTerminalOpen(true); }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect>
                <line x1="8" y1="21" x2="16" y2="21"></line>
                <line x1="12" y1="17" x2="12" y2="21"></line>
              </svg>
              Active Containers
            </button>
          </div>

          <hr className="divider" />

          {/* Auto Refresh Toggle */}
          <div
            className="toggle-wrapper"
            onClick={() => setAutoRefresh((prev) => !prev)}
          >
            <div className={`toggle-track ${autoRefresh ? 'active' : ''}`}>
              <div className="toggle-thumb" />
            </div>
            <span className="toggle-label">
              Live Refresh {autoRefresh ? '(3s)' : '(Paused)'}
            </span>
          </div>
        </div>
      </aside>

      {/* ── Main Content ─────────────────────────────────────── */}
      <main className="main-content">
        {/* Page Header */}
        <div className="page-header">
          <div>
            <h1 className="page-title gradient-text">
              Stellar AI Observability Platform
            </h1>
            <p className="page-subtitle">
              Site Reliability Engineering Console — Real-Time Mathematical & LLM-Powered Distributed Observability
            </p>
          </div>
          <div className="page-header__status">
            <span className={`status-indicator ${autoRefresh ? 'live' : 'paused'}`} />
            <span className="status-text">{autoRefresh ? 'LIVE' : 'PAUSED'}</span>
          </div>
        </div>

        {/* Metric Cards */}
        <div className="metrics-grid stagger-children">
          <MetricCard
            icon="📡"
            label="System Throughput"
            value={`${throughput} RPS`}
            delta={throughput > 0 ? 'Active Traffic' : 'No Load'}
            deltaType={throughput > 0 ? 'positive' : 'neutral'}
            accentColor="var(--accent-purple)"
            index={0}
          />
          <MetricCard
            icon="🔐"
            label="Auth Latency"
            value={`${authLatency.toFixed(1)} ms`}
            delta={authLatency > 100 ? 'Elevated' : 'Normal'}
            deltaType={authLatency > 100 ? 'negative' : 'positive'}
            accentColor="var(--accent-blue)"
            index={1}
          />
          <MetricCard
            icon="💳"
            label="Payment Latency"
            value={`${payLatency.toFixed(1)} ms`}
            delta={payLatency > 100 ? 'Elevated' : 'Normal'}
            deltaType={payLatency > 100 ? 'negative' : 'positive'}
            accentColor="var(--accent-cyan)"
            index={2}
          />
          <MetricCard
            icon="🚨"
            label="Total Incidents"
            value={`${totalIncidents}`}
            delta={`${totalAnomalies} anomalies`}
            deltaType={totalIncidents > 0 ? 'negative' : 'neutral'}
            accentColor="var(--accent-red)"
            index={3}
          />
        </div>

        {/* Live Charts */}
        <LiveCharts metricsHistory={metricsHistory} />

        {/* Divider */}
        <hr className="divider" />

        {/* Incident Board */}
        <IncidentBoard incidents={incidents ?? []} />
      </main>

      {/* ── Toast Container ──────────────────────────────────── */}
      <div className="toast-container">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.type}`}>
            {t.type === 'success' ? '✅ ' : '❌ '}
            {t.message}
          </div>
        ))}
      </div>

      <TerminalModal isOpen={isTerminalOpen} onClose={() => setIsTerminalOpen(false)} initialTab={terminalTab} />
    </div>
  );
}

export default App;
