import { useMemo } from 'react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import type { MetricsResponse } from '../api';
import './LiveCharts.css';

// ── Custom Tooltip ─────────────────────────────────────────────

interface TooltipPayloadEntry {
  name: string;
  value: number;
  color: string;
}

function CustomTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: TooltipPayloadEntry[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tooltip glass-panel">
      <p className="chart-tooltip__time">{label}</p>
      {payload.map((entry) => (
        <p key={entry.name} className="chart-tooltip__row" style={{ color: entry.color }}>
          {entry.name}: <strong>{typeof entry.value === 'number' ? entry.value.toFixed(1) : entry.value}</strong>
        </p>
      ))}
    </div>
  );
}

// ── Chart Data Point ───────────────────────────────────────────

interface LatencyPoint {
  time: string;
  auth: number;
  payment: number;
}

interface ThroughputPoint {
  time: string;
  rps: number;
}

interface LiveChartsProps {
  metricsHistory: MetricsResponse[];
}

export function LiveCharts({ metricsHistory }: LiveChartsProps) {
  // Transform metrics history into chart data
  const { latencyData, throughputData } = useMemo(() => {
    const latency: LatencyPoint[] = [];
    const throughput: ThroughputPoint[] = [];

    metricsHistory.forEach((m, i) => {
      const timeLabel = new Date().toLocaleTimeString('en-US', {
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      });
      // Use index-based offset to create unique labels
      const label = i === metricsHistory.length - 1 ? timeLabel : `t-${metricsHistory.length - 1 - i}`;

      const authLat = m.per_service?.['auth-service']?.avg_latency_ms ?? 0;
      const payLat = m.per_service?.['payment-service']?.avg_latency_ms ?? 0;

      latency.push({ time: label, auth: authLat, payment: payLat });
      throughput.push({ time: label, rps: m.logs_per_second ?? 0 });
    });

    return { latencyData: latency, throughputData: throughput };
  }, [metricsHistory]);

  const commonGridProps = {
    strokeDasharray: '3 3',
    stroke: 'rgba(0, 0, 0, 0.06)',
  };

  const commonAxisProps = {
    tick: { fill: '#94a3b8', fontSize: 11 },
    axisLine: { stroke: 'rgba(0, 0, 0, 0.08)' },
    tickLine: false as const,
  };

  return (
    <div className="live-charts">
      {/* Latency Chart */}
      <div className="chart-container glass-panel">
        <div className="chart-header">
          <span className="chart-icon">⏱️</span>
          <h3 className="chart-title">Live Service Latency</h3>
          <span className="chart-unit">ms</span>
        </div>

        {latencyData.length === 0 ? (
          <div className="chart-empty">Awaiting traffic metrics…</div>
        ) : (
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={latencyData} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
              <defs>
                <linearGradient id="gradAuth" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#4361ee" stopOpacity={0.2} />
                  <stop offset="100%" stopColor="#4361ee" stopOpacity={0.02} />
                </linearGradient>
                <linearGradient id="gradPayment" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#7c3aed" stopOpacity={0.2} />
                  <stop offset="100%" stopColor="#7c3aed" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid {...commonGridProps} />
              <XAxis dataKey="time" {...commonAxisProps} />
              <YAxis {...commonAxisProps} />
              <Tooltip content={<CustomTooltip />} />
              <Area
                type="monotone"
                dataKey="auth"
                name="Auth Latency"
                stroke="#4361ee"
                strokeWidth={2}
                fill="url(#gradAuth)"
                dot={false}
                animationDuration={300}
              />
              <Area
                type="monotone"
                dataKey="payment"
                name="Payment Latency"
                stroke="#7c3aed"
                strokeWidth={2}
                fill="url(#gradPayment)"
                dot={false}
                animationDuration={300}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Throughput Chart */}
      <div className="chart-container glass-panel">
        <div className="chart-header">
          <span className="chart-icon">📈</span>
          <h3 className="chart-title">Live Throughput</h3>
          <span className="chart-unit">req/s</span>
        </div>

        {throughputData.length === 0 ? (
          <div className="chart-empty">Awaiting traffic metrics…</div>
        ) : (
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={throughputData} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
              <defs>
                <linearGradient id="gradRps" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#ef4444" stopOpacity={0.2} />
                  <stop offset="100%" stopColor="#f59e0b" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid {...commonGridProps} />
              <XAxis dataKey="time" {...commonAxisProps} />
              <YAxis {...commonAxisProps} />
              <Tooltip content={<CustomTooltip />} />
              <Area
                type="monotone"
                dataKey="rps"
                name="Throughput"
                stroke="#ef4444"
                strokeWidth={2}
                fill="url(#gradRps)"
                dot={false}
                animationDuration={300}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
