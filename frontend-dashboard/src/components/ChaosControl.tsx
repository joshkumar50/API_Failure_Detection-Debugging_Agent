import { useState, useCallback, useEffect } from 'react';
import { API } from '../api';
import './ChaosControl.css';

interface ChaosControlProps {
  onToast: (type: 'success' | 'error', message: string) => void;
}

export function ChaosControl({ onToast }: ChaosControlProps) {
  const [loadingMode, setLoadingMode] = useState<string | null>(null);
  const [chaosEnabled, setChaosEnabled] = useState<boolean>(true);
  const [loadingToggle, setLoadingToggle] = useState<boolean>(false);

  // Fetch initial background chaos status
  useEffect(() => {
    API.getChaosStatus().then((res) => {
      if (res) {
        setChaosEnabled(res.enabled);
      }
    });
  }, []);

  const handleChaos = useCallback(async (mode: string) => {
    setLoadingMode(mode);
    try {
      // Step 1: Login to get a token
      const token = await API.login('chaos-agent', 'admin-chaos');
      if (!token) {
        onToast('error', 'Authentication failed during chaos injection');
        return;
      }

      // Step 2: Fire the chaos request
      const result = await API.triggerChaos(mode, token);
      onToast(result.success ? 'success' : 'error', result.message);
    } catch (err) {
      onToast('error', `Chaos injection failed: ${err}`);
    } finally {
      setLoadingMode(null);
    }
  }, [onToast]);

  const handleToggleChaos = useCallback(async () => {
    setLoadingToggle(true);
    try {
      const res = await API.toggleChaos();
      if (res) {
        setChaosEnabled(res.enabled);
        onToast(
          res.enabled ? 'success' : 'success',
          res.enabled
            ? 'Background chaos generation has been resumed! Anomalies will trigger shortly.'
            : 'Background chaos generation has been stopped successfully!'
        );
      } else {
        onToast('error', 'Failed to update background chaos state');
      }
    } catch (err) {
      onToast('error', `Error updating chaos state: ${err}`);
    } finally {
      setLoadingToggle(false);
    }
  }, [onToast]);

  return (
    <div className="chaos-control">
      <div className="chaos-control__header">
        <span className="chaos-control__warning">⚠️</span>
        <h3 className="chaos-control__title">Chaos Controls</h3>
      </div>
      <p className="chaos-control__description">
        Trigger organic runtime failures to test anomaly detection and AI root cause analysis.
      </p>

      <div className="chaos-control__buttons">
        <button
          className="btn btn-danger chaos-btn"
          onClick={() => handleChaos('lock')}
          disabled={loadingMode !== null}
        >
          {loadingMode === 'lock' ? (
            <>
              <span className="spinner" /> Locking…
            </>
          ) : (
            <>💥 DB Table Lock</>
          )}
        </button>

        <button
          className="btn btn-danger chaos-btn"
          onClick={() => handleChaos('sleep')}
          disabled={loadingMode !== null}
        >
          {loadingMode === 'sleep' ? (
            <>
              <span className="spinner" /> Injecting…
            </>
          ) : (
            <>⏳ 5s Network Sleep</>
          )}
        </button>
      </div>

      <div className="chaos-control__toggle-section" style={{ marginTop: 'var(--space-md)' }}>
        <button
          className={`btn chaos-btn ${chaosEnabled ? 'btn-stop-chaos' : 'btn-start-chaos'}`}
          onClick={handleToggleChaos}
          disabled={loadingToggle}
          style={{
            width: '100%',
            background: chaosEnabled 
              ? 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)' 
              : 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
            color: '#ffffff',
            border: 'none',
            boxShadow: chaosEnabled 
              ? '0 4px 12px rgba(239, 68, 68, 0.2)' 
              : '0 4px 12px rgba(16, 185, 129, 0.2)'
          }}
        >
          {loadingToggle ? (
            <>
              <span className="spinner" /> Loading…
            </>
          ) : chaosEnabled ? (
            <>🛑 Stop Background Chaos</>
          ) : (
            <>▶️ Resume Background Chaos</>
          )}
        </button>
      </div>

      <div className="chaos-control__reset-section" style={{ marginTop: 'var(--space-sm)' }}>
        <button
          className="btn chaos-btn"
          onClick={async () => {
            if (window.confirm("Are you sure you want to clear all incidents and metrics state?")) {
              const res = await API.clearAllState();
              if (res && res.status === "cleared") {
                onToast("success", "SRE state cleared successfully!");
                // Force a page refresh to update all hooks
                window.location.reload();
              } else {
                onToast("error", "Failed to clear state.");
              }
            }
          }}
          style={{
            width: '100%',
            background: 'rgba(255, 255, 255, 0.05)',
            color: '#a0aec0',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            boxShadow: 'none'
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLButtonElement).style.background = 'rgba(255, 255, 255, 0.1)';
            (e.currentTarget as HTMLButtonElement).style.color = '#ffffff';
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLButtonElement).style.background = 'rgba(255, 255, 255, 0.05)';
            (e.currentTarget as HTMLButtonElement).style.color = '#a0aec0';
          }}
        >
          🗑️ Clear SRE Console State
        </button>
      </div>
    </div>
  );
}
