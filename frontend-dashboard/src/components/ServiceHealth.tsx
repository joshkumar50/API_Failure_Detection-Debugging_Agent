import { useCallback } from 'react';
import { API, type HealthResponse, type Incident } from '../api';
import { usePolling } from '../hooks/usePolling';
import './ServiceHealth.css';

interface ServiceDef {
  name: string;
  proxyPrefix: string;
  serviceKey: string;
}

const SERVICES: ServiceDef[] = [
  { name: 'Auth Service', proxyPrefix: 'auth', serviceKey: 'auth-service' },
  { name: 'Payment Service', proxyPrefix: 'payment', serviceKey: 'payment-service' },
  { name: 'Monitoring Engine', proxyPrefix: 'monitoring', serviceKey: 'monitoring-engine' },
  { name: 'AI Engine', proxyPrefix: 'ai', serviceKey: 'ai-engine' },
];

interface ServiceRowProps {
  service: ServiceDef;
  isAffected: boolean;
  severity?: string;
}

function ServiceRow({ service, isAffected, severity }: ServiceRowProps) {
  const fetcher = useCallback(() => API.getHealth(service.proxyPrefix), [service.proxyPrefix]);
  const { data, loading } = usePolling<HealthResponse>(fetcher, 3000);

  const isHealthy = data?.status === 'healthy';

  // Determine final status class and label
  let statusText = 'Offline';
  let statusClass = 'offline';

  if (loading) {
    statusText = '…';
    statusClass = 'loading';
  } else if (isHealthy) {
    if (isAffected) {
      if (severity === 'CRITICAL') {
        statusText = 'Critical';
        statusClass = 'critical';
      } else {
        statusText = 'Degraded';
        statusClass = 'degraded';
      }
    } else {
      statusText = 'Healthy';
      statusClass = 'healthy';
    }
  }

  return (
    <div className="service-row">
      <div className={`service-dot ${statusClass}`} />
      <span className="service-name">{service.name}</span>
      <span className={`service-status ${statusClass}`}>{statusText}</span>
    </div>
  );
}

interface ServiceHealthProps {
  activeIncidents?: Incident[];
}

export function ServiceHealth({ activeIncidents = [] }: ServiceHealthProps) {
  // Find open (unresolved) incidents
  const openIncidents = activeIncidents.filter((inc) => !inc.resolved);

  return (
    <div className="service-health">
      <h3 className="service-health__title">Service Health</h3>
      <div className="service-health__list">
        {SERVICES.map((svc) => {
          // Find if this service is affected by any active open incident
          const correlatedIncident = openIncidents.find((inc) =>
            inc.services_affected.includes(svc.serviceKey)
          );
          const isAffected = !!correlatedIncident;
          const severity = correlatedIncident?.severity;

          return (
            <ServiceRow
              key={svc.proxyPrefix}
              service={svc}
              isAffected={isAffected}
              severity={severity}
            />
          );
        })}
      </div>
    </div>
  );
}
