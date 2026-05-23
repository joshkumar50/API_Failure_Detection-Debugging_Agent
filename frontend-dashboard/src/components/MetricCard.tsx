import './MetricCard.css';

interface MetricCardProps {
  icon: string;
  label: string;
  value: string;
  delta?: string;
  deltaType?: 'positive' | 'negative' | 'neutral';
  accentColor?: string;
  index?: number;
}

export function MetricCard({
  icon,
  label,
  value,
  delta,
  deltaType = 'neutral',
  accentColor = 'var(--accent-blue)',
  index = 0,
}: MetricCardProps) {
  return (
    <div
      className="metric-card glass-panel glass-panel-interactive"
      style={{ '--accent': accentColor, animationDelay: `${index * 80}ms` } as React.CSSProperties}
    >
      <div className="metric-card__header">
        <span className="metric-card__icon">{icon}</span>
        <span className="metric-card__label">{label}</span>
      </div>

      <div className="metric-card__value" key={value}>
        {value}
      </div>

      {delta && (
        <div className={`metric-card__delta metric-card__delta--${deltaType}`}>
          {deltaType === 'positive' && '▲ '}
          {deltaType === 'negative' && '▼ '}
          {delta}
        </div>
      )}

      <div className="metric-card__glow" />
    </div>
  );
}
