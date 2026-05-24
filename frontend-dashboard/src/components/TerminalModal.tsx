import { useState, useEffect, useRef } from 'react';
import { API, type LogEntry } from '../api';
import './TerminalModal.css';

interface TerminalModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialTab?: 'logs' | 'containers';
}

export function TerminalModal({ isOpen, onClose, initialTab = 'logs' }: TerminalModalProps) {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [activeTab, setActiveTab] = useState<'logs' | 'containers'>(initialTab);
  const terminalRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isOpen) {
      setActiveTab(initialTab);
    }
  }, [isOpen, initialTab]);

  // Poll for logs when modal is open
  useEffect(() => {
    if (!isOpen) return;

    let intervalId: number;

    const fetchLogs = async () => {
      const data = await API.getLogs(150);
      if (data) {
        setLogs(data);
      }
    };

    fetchLogs();
    intervalId = window.setInterval(fetchLogs, 1000);

    return () => {
      clearInterval(intervalId);
    };
  }, [isOpen]);

  const isScrolledUpRef = useRef(false);

  const handleScroll = () => {
    if (terminalRef.current) {
      const { scrollTop, scrollHeight, clientHeight } = terminalRef.current;
      // If user scrolls up more than 20px from bottom, pause auto-scroll
      isScrolledUpRef.current = scrollHeight - scrollTop - clientHeight > 20;
    }
  };

  // Auto-scroll to bottom when new logs arrive, ONLY if we haven't manually scrolled up
  useEffect(() => {
    if (terminalRef.current && !isScrolledUpRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [logs]);

  if (!isOpen) return null;

  return (
    <div className="terminal-overlay" onClick={onClose}>
      <div className="terminal-container" onClick={(e) => e.stopPropagation()}>
        <div className="terminal-header">
          <div className="terminal-controls">
            <span className="terminal-dot red" onClick={onClose} title="Close"></span>
            <span className="terminal-dot yellow"></span>
            <span className="terminal-dot green"></span>
          </div>
          <div className="terminal-tabs">
            <button className={`term-tab ${activeTab === 'logs' ? 'active' : ''}`} onClick={() => setActiveTab('logs')}>Live Telemetry</button>
            <button className={`term-tab ${activeTab === 'containers' ? 'active' : ''}`} onClick={() => setActiveTab('containers')}>Active Containers</button>
          </div>
        </div>
        
        <div className="terminal-body" ref={terminalRef} onScroll={handleScroll}>
          {activeTab === 'containers' ? (
            <div className="terminal-welcome">
              <span className="term-info">$ docker container ps</span><br/>
              <pre style={{ margin: '8px 0', color: '#ccc', fontSize: '11px', fontFamily: 'inherit', lineHeight: '1.2' }}>
{`CONTAINER ID   IMAGE                            COMMAND                  STATUS                    PORTS                                       NAMES
2f3020b30e32   stellar-frontend-dashboard       "/docker-entrypoint.…"   Up About a minute         0.0.0.0:3000->3000/tcp                      frontend-dashboard
dd5bc7dfcacc   stellar-traffic-generator        "python -u main.py"      Up About a minute                                                     traffic-generator
e4ec8dcf9887   stellar-payment-service          "uvicorn main:app --…"   Up About a minute         0.0.0.0:8002->8002/tcp                      payment-service
a33d89f2cdfd   stellar-auth-service             "uvicorn main:app --…"   Up About a minute         0.0.0.0:8001->8001/tcp                      auth-service
a80a1a8606f1   postgres:16-alpine               "docker-entrypoint.s…"   Up 2 minutes (healthy)    0.0.0.0:5432->5432/tcp                      postgres-db
2b662920df1a   stellar-monitoring-engine        "uvicorn main:app --…"   Up 2 minutes              0.0.0.0:8005->8005/tcp                      monitoring-engine
3d9d46496d43   stellar-ai-engine                "uvicorn main:app --…"   Up 2 minutes              0.0.0.0:8006->8006/tcp                      ai-engine`}
              </pre>
            </div>
          ) : (
            <>
              <div className="terminal-welcome">
                <span className="term-info">$ docker logs -f stellar-cluster</span><br/>
                <span style={{ color: '#888' }}>Attaching to container network... streaming live telemetry.</span><br/>
                <br/>
              </div>
              
              {logs.map((log, index) => {
            // Determine colors
            const isError = log.status_code >= 400 || log.level === 'ERROR' || log.level === 'WARNING';
            const methodColor = log.method === 'GET' ? 'term-blue' : (log.method === 'POST' ? 'term-green' : 'term-magenta');
            
            return (
              <div key={index} className={`term-line ${isError ? 'term-line-error' : ''}`}>
                <span className="term-time">[{new Date(log.timestamp).toISOString()}]</span>
                <span className="term-service">[{log.service}]</span>
                {' '}
                {log.level && <span className={`term-level ${log.level.toLowerCase()}`}>{log.level}</span>}
                {' '}
                {log.method && <span className={methodColor}>{log.method}</span>}
                {' '}
                <span className="term-endpoint">{log.endpoint}</span>
                {' '}
                {log.status_code > 0 && (
                  <span className={`term-status ${isError ? 'term-red' : 'term-cyan'}`}>
                    {log.status_code}
                  </span>
                )}
                {' '}
                <span className="term-latency">{log.latency_ms.toFixed(1)}ms</span>
                {' '}
                {log.message && <span className="term-msg">| {log.message}</span>}
              </div>
            );
          })}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
