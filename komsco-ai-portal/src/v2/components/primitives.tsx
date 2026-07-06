import React from 'react';
import { Check, ChevronLeft, ChevronRight, Copy, Inbox, X } from 'lucide-react';
import type { Severity } from '../../types';
import { severityLabel } from '../../portalBadges';

/* ---------- Card ---------- */

export const Card: React.FC<{
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  flush?: boolean;
  sub?: string;
  title?: React.ReactNode;
}> = ({ actions, children, className, flush, sub, title }) => (
  <section className={`v2-card${className ? ` ${className}` : ''}`}>
    {(title || actions) && (
      <header className="v2-card__head">
        <div className="v2-card__heading">
          {title && <h2 className="v2-card__title">{title}</h2>}
          {sub && <p className="v2-card__sub">{sub}</p>}
        </div>
        {actions && <div className="v2-card__actions">{actions}</div>}
      </header>
    )}
    <div className={`v2-card__body${flush ? ' is-flush' : ''}`}>{children}</div>
  </section>
);

/* ---------- Severity badge ---------- */

export const SevBadge: React.FC<{ label?: string; severity: Severity }> = ({ label, severity }) => (
  <span className={`v2-badge is-${severity}`}>
    <span className="v2-badge__dot" aria-hidden="true" />
    {label ?? severityLabel[severity]}
  </span>
);

export const ToneDot: React.FC<{ tone: string }> = ({ tone }) => (
  <span className={`v2-tone-dot is-${tone}`} aria-hidden="true" />
);

/* ---------- KPI ---------- */

export const KpiStat: React.FC<{
  icon?: React.ReactNode;
  label: string;
  severity?: Severity;
  sub: string;
  value: React.ReactNode;
}> = ({ icon, label, severity = 'ok', sub, value }) => (
  <div className={`v2-kpi is-${severity}`}>
    <div className="v2-kpi__top">
      <span className="v2-kpi__label">{label}</span>
      {icon && <span className="v2-kpi__icon">{icon}</span>}
    </div>
    <strong className="v2-kpi__value">{value}</strong>
    <span className="v2-kpi__sub">{sub}</span>
  </div>
);

export const HealthRing: React.FC<{ score: number; size?: number }> = ({ score, size = 148 }) => {
  const clamped = Math.max(0, Math.min(100, score));
  const radius = (size - 14) / 2;
  const circumference = 2 * Math.PI * radius;
  const severity: Severity = clamped >= 90 ? 'ok' : clamped >= 70 ? 'warn' : 'risk';
  return (
    <div className={`v2-health-ring is-${severity}`} style={{ width: size, height: size }}>
      <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size} aria-hidden="true">
        <circle className="v2-health-ring__track" cx={size / 2} cy={size / 2} r={radius} />
        <circle
          className="v2-health-ring__meter"
          cx={size / 2}
          cy={size / 2}
          r={radius}
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - clamped / 100)}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <div className="v2-health-ring__value">
        <strong>{clamped}</strong>
        <span>건강도</span>
      </div>
    </div>
  );
};

export const Sparkline: React.FC<{ className?: string; points?: number[] }> = ({
  className,
  points = [42, 45, 41, 48, 52, 49, 56, 61, 58, 66, 63, 72],
}) => {
  const width = 120;
  const height = 36;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const step = width / (points.length - 1);
  const coords = points.map((p, i) => [i * step, height - 4 - ((p - min) / span) * (height - 8)]);
  const path = coords.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const area = `${path} L${width},${height} L0,${height} Z`;
  return (
    <svg
      className={`v2-sparkline${className ? ` ${className}` : ''}`}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <path className="v2-sparkline__area" d={area} />
      <path className="v2-sparkline__line" d={path} />
    </svg>
  );
};

/* ---------- CountUp / Delta / AreaChart ---------- */

export const CountUp: React.FC<{ duration?: number; value: number }> = ({ duration = 900, value }) => {
  const [display, setDisplay] = React.useState(0);
  React.useEffect(() => {
    let frame = 0;
    const start = performance.now();
    const from = 0;
    const tick = (now: number) => {
      const progress = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(Math.round(from + (value - from) * eased));
      if (progress < 1) {
        frame = requestAnimationFrame(tick);
      }
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [duration, value]);
  return <>{display}</>;
};

export const DeltaChip: React.FC<{ label?: string; value: number }> = ({ label, value }) => {
  const direction = value > 0 ? 'up' : value < 0 ? 'down' : 'flat';
  return (
    <span className={`v2-delta is-${direction}`}>
      <svg viewBox="0 0 8 8" aria-hidden="true">
        {direction === 'flat' ? (
          <path d="M1 4h6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        ) : (
          <path
            d={direction === 'up' ? 'M4 1.2 7 6H1z' : 'M4 6.8 1 2h6z'}
            fill="currentColor"
          />
        )}
      </svg>
      {Math.abs(value).toFixed(1)}%{label ? ` ${label}` : ''}
    </span>
  );
};

export const AreaChart: React.FC<{
  height?: number;
  id: string;
  labels?: { end: string; start: string };
  points: number[];
  tone?: 'accent' | 'ok' | 'warn' | 'risk';
}> = ({ height = 120, id, labels, points, tone = 'accent' }) => {
  const width = 460;
  const pad = 6;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const step = (width - pad * 2) / (points.length - 1);
  const coords = points.map((p, i) => [
    pad + i * step,
    height - 18 - ((p - min) / span) * (height - 34),
  ]);
  // 부드러운 곡선 (Catmull-Rom 유사 보간)
  let path = `M${coords[0][0].toFixed(1)},${coords[0][1].toFixed(1)}`;
  for (let i = 1; i < coords.length; i += 1) {
    const [x0, y0] = coords[i - 1];
    const [x1, y1] = coords[i];
    const cx = (x0 + x1) / 2;
    path += ` C${cx.toFixed(1)},${y0.toFixed(1)} ${cx.toFixed(1)},${y1.toFixed(1)} ${x1.toFixed(1)},${y1.toFixed(1)}`;
  }
  const area = `${path} L${(width - pad).toFixed(1)},${height - 12} L${pad},${height - 12} Z`;
  const [lastX, lastY] = coords[coords.length - 1];
  return (
    <div className={`v2-areachart is-${tone}`}>
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
        <defs>
          <linearGradient id={`v2-area-${id}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="currentColor" stopOpacity="0.32" />
            <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0.25, 0.5, 0.75].map((fraction) => (
          <line
            className="v2-areachart__grid"
            key={fraction}
            x1={pad}
            x2={width - pad}
            y1={(height - 30) * fraction + 6}
            y2={(height - 30) * fraction + 6}
          />
        ))}
        <path d={area} fill={`url(#v2-area-${id})`} stroke="none" />
        <path className="v2-areachart__line" d={path} />
        <circle className="v2-areachart__dot" cx={lastX} cy={lastY} r="3.4" />
        <circle className="v2-areachart__dot-halo" cx={lastX} cy={lastY} r="8" />
      </svg>
      {labels && (
        <div className="v2-areachart__labels">
          <span>{labels.start}</span>
          <span>{labels.end}</span>
        </div>
      )}
    </div>
  );
};

/* ---------- Progress / Donut ---------- */

export const ProgressBar: React.FC<{ severity?: Severity; value: number }> = ({ severity = 'ok', value }) => (
  <span className={`v2-progress is-${severity}`}>
    <span className="v2-progress__fill" style={{ width: `${Math.max(0, Math.min(100, value * 100))}%` }} />
  </span>
);

export const Donut: React.FC<{
  center?: React.ReactNode;
  segments: Array<{ severity: Severity; value: number }>;
  size?: number;
}> = ({ center, segments, size = 120 }) => {
  const total = segments.reduce((sum, s) => sum + s.value, 0) || 1;
  const radius = (size - 16) / 2;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;
  return (
    <div className="v2-donut" style={{ width: size, height: size }}>
      <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size} aria-hidden="true">
        <circle className="v2-donut__track" cx={size / 2} cy={size / 2} r={radius} />
        {segments.map((segment, index) => {
          const fraction = segment.value / total;
          const dash = fraction * circumference;
          const element = (
            <circle
              key={index}
              className={`v2-donut__seg is-${segment.severity}`}
              cx={size / 2}
              cy={size / 2}
              r={radius}
              strokeDasharray={`${dash} ${circumference - dash}`}
              strokeDashoffset={-offset}
              transform={`rotate(-90 ${size / 2} ${size / 2})`}
            />
          );
          offset += dash;
          return element;
        })}
      </svg>
      {center && <div className="v2-donut__center">{center}</div>}
    </div>
  );
};

/* ---------- Tabs / Segmented ---------- */

export type TabItem = { count?: number; id: string; label: string };

export const Tabs: React.FC<{
  active: string;
  items: TabItem[];
  onChange: (id: string) => void;
}> = ({ active, items, onChange }) => (
  <div className="v2-tabs" role="tablist">
    {items.map((item) => (
      <button
        key={item.id}
        className={`v2-tabs__item${active === item.id ? ' is-active' : ''}`}
        onClick={() => onChange(item.id)}
        role="tab"
        aria-selected={active === item.id}
        type="button"
      >
        {item.label}
        {item.count !== undefined && <span className="v2-tabs__count">{item.count}</span>}
      </button>
    ))}
  </div>
);

export const Segmented: React.FC<{
  active: string;
  items: TabItem[];
  onChange: (id: string) => void;
}> = ({ active, items, onChange }) => (
  <div className="v2-segmented">
    {items.map((item) => (
      <button
        key={item.id}
        className={`v2-segmented__item${active === item.id ? ' is-active' : ''}`}
        onClick={() => onChange(item.id)}
        type="button"
      >
        {item.label}
      </button>
    ))}
  </div>
);

/* ---------- Toggle ---------- */

export const Toggle: React.FC<{
  checked: boolean;
  disabled?: boolean;
  label: string;
  onChange?: (checked: boolean) => void;
}> = ({ checked, disabled, label, onChange }) => (
  <button
    className={`v2-toggle${checked ? ' is-on' : ''}${disabled ? ' is-disabled' : ''}`}
    onClick={() => !disabled && onChange?.(!checked)}
    type="button"
    aria-pressed={checked}
  >
    <span className="v2-toggle__track" aria-hidden="true">
      <span className="v2-toggle__thumb" />
    </span>
    <span className="v2-toggle__label">{label}</span>
  </button>
);

/* ---------- Inputs ---------- */

export const SearchInput: React.FC<{
  onChange: (value: string) => void;
  placeholder?: string;
  value: string;
}> = ({ onChange, placeholder, value }) => (
  <label className="v2-search">
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" strokeWidth="2" />
      <line x1="16.5" y1="16.5" x2="21" y2="21" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
    <input
      onChange={(event) => onChange(event.target.value)}
      placeholder={placeholder}
      type="search"
      value={value}
    />
    {value && (
      <button className="v2-search__clear" onClick={() => onChange('')} type="button" aria-label="지우기">
        <X size={13} />
      </button>
    )}
  </label>
);

export const Select: React.FC<{
  onChange: (value: string) => void;
  options: Array<{ label: string; value: string }>;
  value: string;
}> = ({ onChange, options, value }) => (
  <select className="v2-select" onChange={(event) => onChange(event.target.value)} value={value}>
    {options.map((option) => (
      <option key={option.value} value={option.value}>
        {option.label}
      </option>
    ))}
  </select>
);

/* ---------- Buttons ---------- */

export const Button: React.FC<{
  children: React.ReactNode;
  disabled?: boolean;
  icon?: React.ReactNode;
  onClick?: () => void;
  size?: 'sm' | 'md';
  variant?: 'primary' | 'ghost' | 'outline';
}> = ({ children, disabled, icon, onClick, size = 'md', variant = 'outline' }) => (
  <button
    className={`v2-button is-${variant} is-${size}`}
    disabled={disabled}
    onClick={onClick}
    type="button"
  >
    {icon}
    {children}
  </button>
);

export const CopyButton: React.FC<{ label?: string; text: string }> = ({ label, text }) => {
  const [copied, setCopied] = React.useState(false);
  const copy = React.useCallback(() => {
    void navigator.clipboard?.writeText(text).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    });
  }, [text]);
  return (
    <button className={`v2-copy${copied ? ' is-copied' : ''}`} onClick={copy} type="button">
      {copied ? <Check size={13} /> : <Copy size={13} />}
      {copied ? '복사됨' : label ?? '복사'}
    </button>
  );
};

export const CommandBlock: React.FC<{ command: string; title?: string }> = ({ command, title }) => (
  <div className="v2-cmd">
    <div className="v2-cmd__head">
      {title && <span className="v2-cmd__title">{title}</span>}
      <CopyButton text={command} />
    </div>
    <code className="v2-cmd__code">{command}</code>
  </div>
);

/* ---------- Empty / Skeleton ---------- */

export const Empty: React.FC<{ label: string }> = ({ label }) => (
  <div className="v2-empty">
    <Inbox size={22} aria-hidden="true" />
    <p>{label}</p>
  </div>
);

export const Skeleton: React.FC<{ height?: number | string; width?: number | string }> = ({
  height = 14,
  width = '100%',
}) => <span className="v2-skeleton" style={{ height, width }} aria-hidden="true" />;

/* ---------- Drawer ---------- */

export const Drawer: React.FC<{
  children: React.ReactNode;
  onClose: () => void;
  open: boolean;
  sub?: React.ReactNode;
  title: React.ReactNode;
  wide?: boolean;
}> = ({ children, onClose, open, sub, title, wide }) => {
  React.useEffect(() => {
    if (!open) {
      return;
    }
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [open, onClose]);

  if (!open) {
    return null;
  }
  return (
    <div className="v2-drawer" role="dialog" aria-modal="true">
      <div className="v2-drawer__scrim" onClick={onClose} />
      <aside className={`v2-drawer__panel${wide ? ' is-wide' : ''}`}>
        <header className="v2-drawer__head">
          <div>
            <h2 className="v2-drawer__title">{title}</h2>
            {sub && <div className="v2-drawer__sub">{sub}</div>}
          </div>
          <button className="v2-icon-btn" onClick={onClose} type="button" aria-label="닫기">
            <X size={16} />
          </button>
        </header>
        <div className="v2-drawer__body">{children}</div>
      </aside>
    </div>
  );
};

/* ---------- Pagination ---------- */

export const Pagination: React.FC<{
  onPage: (page: number) => void;
  onPageSize: (size: number) => void;
  page: number;
  pageSize: number;
  pageSizeOptions?: number[];
  total: number;
  unit?: string;
}> = ({ onPage, onPageSize, page, pageSize, pageSizeOptions = [10, 25, 50], total, unit = '행' }) => {
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const clamped = Math.min(page, pageCount);
  const start = total === 0 ? 0 : (clamped - 1) * pageSize + 1;
  const end = Math.min(total, clamped * pageSize);
  return (
    <div className="v2-pagination">
      <span className="v2-pagination__summary">
        {start}-{end} / {total} {unit}
      </span>
      <div className="v2-pagination__controls">
        <Select
          onChange={(value) => onPageSize(Number(value))}
          options={pageSizeOptions.map((option) => ({ label: `${option}개씩`, value: String(option) }))}
          value={String(pageSize)}
        />
        <button
          className="v2-icon-btn"
          disabled={clamped <= 1}
          onClick={() => onPage(clamped - 1)}
          type="button"
          aria-label="이전 페이지"
        >
          <ChevronLeft size={15} />
        </button>
        <span className="v2-pagination__page">
          {clamped} / {pageCount}
        </span>
        <button
          className="v2-icon-btn"
          disabled={clamped >= pageCount}
          onClick={() => onPage(clamped + 1)}
          type="button"
          aria-label="다음 페이지"
        >
          <ChevronRight size={15} />
        </button>
      </div>
    </div>
  );
};

/* ---------- DataTable ---------- */

export type ColumnDef<T> = {
  align?: 'left' | 'right' | 'center';
  key: string;
  label: string;
  render?: (row: T) => React.ReactNode;
  width?: string;
};

export function DataTable<T extends { id: string }>({
  columns,
  emptyLabel = '표시할 항목이 없습니다',
  onRowClick,
  rows,
  selectedId,
}: {
  columns: Array<ColumnDef<T>>;
  emptyLabel?: string;
  onRowClick?: (row: T) => void;
  rows: T[];
  selectedId?: string;
}): React.ReactElement {
  return (
    <div className="v2-table-wrap">
      <table className="v2-table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key} style={{ width: column.width, textAlign: column.align }}>
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td className="v2-table__empty" colSpan={columns.length}>
                {emptyLabel}
              </td>
            </tr>
          )}
          {rows.map((row) => (
            <tr
              key={row.id}
              className={`${onRowClick ? 'is-clickable' : ''}${selectedId === row.id ? ' is-selected' : ''}`}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
            >
              {columns.map((column) => (
                <td key={column.key} style={{ textAlign: column.align }}>
                  {column.render
                    ? column.render(row)
                    : String((row as Record<string, unknown>)[column.key] ?? '-')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ---------- Definition rows ---------- */

export const DefList: React.FC<{ rows: Array<{ label: string; value: React.ReactNode }> }> = ({ rows }) => (
  <dl className="v2-deflist">
    {rows.map((row) => (
      <div className="v2-deflist__row" key={row.label}>
        <dt>{row.label}</dt>
        <dd>{row.value}</dd>
      </div>
    ))}
  </dl>
);
