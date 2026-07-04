import * as React from 'react';
import type { Severity } from './types';

export const severityLabel: Record<Severity, string> = {
  ok: '정상',
  warn: '주의',
  risk: '위험',
};

export const severityClass = (severity: Severity): string => `is-${severity}`;

export const StatusBadge: React.FC<{ severity: Severity; label?: string }> = ({
  label,
  severity,
}) => <span className={`status-badge ${severityClass(severity)}`}>{label ?? severityLabel[severity]}</span>;
