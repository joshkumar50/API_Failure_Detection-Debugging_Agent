import { useMemo } from 'react';
import type { Incident, RCAResponse } from '../api';
import './IncidentTimeline.css';

interface TimelineEvent {
  id: string;
  type: 'anomaly' | 'error' | 'incident' | 'rca' | 'resolved';
  timestamp: Date;
  title: string;
  description: string;
}

interface IncidentTimelineProps {
  incident: Incident;
  rca: RCAResponse | null;
}

export function IncidentTimeline({ incident, rca }: IncidentTimelineProps) {
  const events = useMemo(() => {
    const items: TimelineEvent[] = [];

    // 1. Initial Anomaly
    if (incident.anomalies && incident.anomalies.length > 0) {
      // Sort to find the earliest anomaly
      const sortedAnomalies = [...incident.anomalies].sort((a, b) => 
        new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
      );
      items.push({
        id: 'evt-anomaly',
        type: 'anomaly',
        timestamp: new Date(sortedAnomalies[0].timestamp),
        title: 'Initial Statistical Anomaly',
        description: `Z-Score threshold exceeded for ${sortedAnomalies[0].service}`,
      });
    }

    // 2. Correlated Error
    if (incident.correlated_errors && incident.correlated_errors.length > 0) {
      const firstError = incident.correlated_errors[0] as any;
      if (firstError && firstError.timestamp) {
        items.push({
          id: 'evt-error',
          type: 'error',
          timestamp: new Date(firstError.timestamp),
          title: 'Service Error Logged',
          description: `Correlated application failure detected`,
        });
      }
    }

    // 3. Incident Generation
    if (incident.created_at) {
      items.push({
        id: 'evt-incident',
        type: 'incident',
        timestamp: new Date(incident.created_at),
        title: 'Incident Auto-Generated',
        description: `Observability engine triggered incident protocol`,
      });
    }

    // 4. AI Diagnostics
    if (rca && rca.generated_at) {
      items.push({
        id: 'evt-rca',
        type: 'rca',
        timestamp: new Date(rca.generated_at),
        title: 'SRE Copilot Diagnostics',
        description: `AI root cause analysis completed via ${rca.model_used}`,
      });
    }

    // 5. Resolution
    if (incident.resolved) {
      // Since we don't have a resolved_at timestamp, we place it slightly after the latest event
      const maxTime = items.reduce((max, evt) => Math.max(max, evt.timestamp.getTime()), 0);
      items.push({
        id: 'evt-resolved',
        type: 'resolved',
        timestamp: new Date(maxTime + 1000), // 1 second after last event
        title: 'Service Restored',
        description: 'Incident resolved and auto-healed',
      });
    }

    // Sort chronologically
    return items.sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime());
  }, [incident, rca]);

  if (events.length === 0) return null;

  return (
    <div className="incident-timeline">
      <h4 className="timeline-header">Timeline of Events</h4>
      <div className="timeline-container">
        {events.map((evt, index) => (
          <div key={evt.id} className={`timeline-item type-${evt.type}`} style={{ animationDelay: `${index * 150}ms` }}>
            <div className="timeline-marker">
              <div className="timeline-dot"></div>
              {index < events.length - 1 && <div className="timeline-line"></div>}
            </div>
            <div className="timeline-content">
              <div className="timeline-time">{evt.timestamp.toLocaleTimeString()}</div>
              <div className="timeline-title">{evt.title}</div>
              <div className="timeline-desc">{evt.description}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
