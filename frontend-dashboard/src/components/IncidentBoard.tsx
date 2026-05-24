import { useState, useEffect } from 'react';
import { API, type Incident, type RCAResponse } from '../api';
import { IncidentTimeline } from './IncidentTimeline';
import './IncidentBoard.css';

// ── RCA Cache ──────────────────────────────────────────────────
const rcaCache = new Map<string, RCAResponse>();

// ── Sub-components ─────────────────────────────────────────────

function SeverityBadge({ severity }: { severity: string }) {
  const cls = severity === 'CRITICAL' ? 'badge-critical' : 'badge-high';
  return <span className={`badge ${cls}`}>{severity}</span>;
}

function FixStep({ step, index }: { step: string; index: number }) {
  return (
    <div className="fix-step" style={{ animationDelay: `${index * 100}ms` }}>
      <div className="fix-step__number">{index + 1}</div>
      <div className="fix-step__text">{step}</div>
    </div>
  );
}

function Expander({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="expander">
      <button className="expander-trigger" onClick={() => setOpen(!open)}>
        <span className={`expander-arrow ${open ? 'open' : ''}`}>▶</span>
        {label}
      </button>
      <div className={`expander-content ${open ? 'open' : ''}`}>{children}</div>
    </div>
  );
}

// ── Single Incident Card ───────────────────────────────────────

function IncidentCard({ incident }: { incident: Incident }) {
  const [rca, setRca] = useState<RCAResponse | null>(rcaCache.get(incident.id) ?? null);
  const [loadingRca, setLoadingRca] = useState(false);
  const [isResolved, setIsResolved] = useState(incident.resolved);

  // Sync resolution state when parent poll updates the incident
  useEffect(() => {
    setIsResolved(incident.resolved);
  }, [incident.resolved]);

  const triggerAnalysis = () => {
    if (rca || loadingRca) return;
    setLoadingRca(true);

    API.analyzeIncident(incident).then((result) => {
      if (result) {
        rcaCache.set(incident.id, result);
        setRca(result);
      } else {
        setLoadingRca(false);
      }
    });
  };

  const handleResolve = () => {
    API.resolveIncident(incident.id).then((res) => {
      if (res) {
        setIsResolved(true);
      }
    });
  };

  // Keep loading false if result resolves or fails, but we manage it cleanly
  useEffect(() => {
    if (rca) {
      setLoadingRca(false);
    }
  }, [rca]);

  return (
    <div className="incident-card glass-panel">
      {/* Header */}
      <div className="incident-card__header">
        <div className="incident-card__title-row">
          <SeverityBadge severity={incident.severity} />
          <h3 className="incident-card__title">
            Incident #{incident.id.slice(0, 8)}
          </h3>
          {isResolved ? (
            <span className="badge badge-healthy">Resolved</span>
          ) : (
            <button className="resolve-btn" onClick={handleResolve}>
              ✓ Resolve
            </button>
          )}
        </div>
        <span className="incident-card__time">
          {new Date(incident.created_at).toLocaleTimeString()}
        </span>
      </div>

      {/* Meta */}
      <p className="incident-card__subtitle">{incident.title}</p>

      <div className="incident-card__meta">
        <span className="incident-card__meta-item">
          <strong>Services:</strong> {incident.services_affected.join(', ')}
        </span>
        <span className="incident-card__meta-item">
          <strong>Anomalies:</strong> {incident.anomalies.length}
        </span>
        <span className="incident-card__meta-item">
          <strong>Errors:</strong> {incident.correlated_errors.length}
        </span>
      </div>

      <p className="incident-card__description">{incident.description}</p>

      {/* AI RCA Section */}
      <div className="incident-card__rca">
        {!rca && !loadingRca ? (
          <div className="rca-trigger-placeholder">
            <button className="rca-trigger-btn" onClick={triggerAnalysis}>
              🤖 Run AI Root Cause Analysis
            </button>
          </div>
        ) : loadingRca ? (
          <div className="rca-loading">
            <span className="spinner" />
            <span>Consulting SRE Copilot…</span>
          </div>
        ) : rca ? (
          <div className="rca-result">
            <div
              className={`rca-header ${incident.severity === 'CRITICAL' ? 'rca-header--critical' : 'rca-header--high'}`}
            >
              <span className="rca-icon">🤖</span>
              <div>
                <div className="rca-label">Root Cause</div>
                <div className="rca-cause">{rca.root_cause}</div>
              </div>
            </div>

            <p className="rca-analysis">{rca.analysis}</p>

            <div className="rca-fix-steps">
              <h4 className="rca-fix-title">🛡️ Remediation Plan</h4>
              {rca.fix_steps.map((step, i) => (
                <FixStep key={i} step={step} index={i} />
              ))}
            </div>

            <div className="rca-footer">
              <span className="mono">
                Engine: {rca.model_used}
              </span>
              <span className="mono">
                {rca.generated_at
                  ? new Date(rca.generated_at).toLocaleString()
                  : ''}
              </span>
            </div>
          </div>
        ) : (
          <div className="rca-unavailable">AI Diagnostics unavailable</div>
        )}
      </div>

      {/* Incident Timeline */}
      <IncidentTimeline incident={incident} rca={rca} />

      {/* Expandable Details */}
      <Expander label="🔍 Inspect Traces & Anomalies">
        <div className="incident-card__details">
          <div>
            <h5>Trace IDs</h5>
            <div className="json-viewer">
              {incident.trace_ids.length > 0
                ? incident.trace_ids.join('\n')
                : 'No trace IDs'}
            </div>
          </div>

          <div>
            <h5>Anomalies</h5>
            <div className="json-viewer">
              {JSON.stringify(incident.anomalies, null, 2)}
            </div>
          </div>

          {incident.correlated_errors.length > 0 && (
            <div>
              <h5>Correlated Errors</h5>
              <div className="json-viewer">
                {JSON.stringify(incident.correlated_errors, null, 2)}
              </div>
            </div>
          )}
        </div>
      </Expander>
    </div>
  );
}

// ── Main IncidentBoard ─────────────────────────────────────────

interface IncidentBoardProps {
  incidents: Incident[];
}

export function IncidentBoard({ incidents }: IncidentBoardProps) {
  return (
    <div className="incident-board">
      <div className="section-header">
        <span className="icon">🚨</span>
        <h2 className="gradient-text">Incident Board & AI Root Cause Analysis</h2>
      </div>

      {incidents.length === 0 ? (
        <div className="empty-state glass-panel">
          <div className="empty-state-icon">✅</div>
          <div className="empty-state-title">System Status Nominal</div>
          <div className="empty-state-subtitle">
            No anomalies or correlated incidents detected.
          </div>
        </div>
      ) : (
        <div className="incident-board__list stagger-children">
          {incidents.map((incident) => (
            <IncidentCard key={incident.id} incident={incident} />
          ))}
        </div>
      )}
    </div>
  );
}
