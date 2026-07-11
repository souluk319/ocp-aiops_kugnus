import type { QueueItem } from './types';

export type RcaEvidenceStatus = 'attention' | 'collected' | 'excluded' | 'normal';

export type RcaEvidenceRow = {
  label: string;
  status: Exclude<RcaEvidenceStatus, 'excluded'>;
  value: string;
};

const evidencePrefixes = [
  'recommended updates',
  'conditional updates',
  'current',
  'reason',
  'available',
  'degraded',
  'progressing',
  'created',
  'target',
  'kubelet',
  'cpu',
  'memory',
  'kind',
  'total',
  'ready',
  'issues',
  'os',
];

export const evidenceLabel = (label: string): string => {
  const labels: Record<string, string> = {
    available: '정상 여부',
    conditional: '조건부 업데이트',
    'conditional updates': '조건부 업데이트',
    cpu: 'CPU',
    created: '생성 시각',
    current: '현재 버전',
    degraded: '저하',
    kind: '종류',
    kubelet: 'Kubelet',
    memory: '메모리',
    os: 'OS',
    progressing: '진행 중',
    ready: '정상',
    reason: '사유',
    'recommended updates': '추천 업데이트',
    target: '대상',
    total: '전체',
    issues: '이슈',
  };
  return labels[label] ?? label;
};

export const evidenceStatusLabel = (status: RcaEvidenceStatus): string => {
  const labels: Record<RcaEvidenceStatus, string> = {
    attention: '확인 필요',
    collected: '수집됨',
    excluded: '제외',
    normal: '정상',
  };
  return labels[status];
};

const splitEvidenceLine = (line: string): { label: string; value: string } => {
  const normalized = line.trim();
  const lower = normalized.toLowerCase();
  const prefix = evidencePrefixes.find((candidate) => lower.startsWith(`${candidate} `));

  if (prefix) {
    return {
      label: prefix,
      value: normalized.slice(prefix.length).trim(),
    };
  }

  const [label, ...value] = normalized.split(/\s+/);
  return {
    label: label || 'signal',
    value: value.join(' ') || '-',
  };
};

const evidenceStatus = (label: string, value: string): RcaEvidenceRow['status'] => {
  const combined = `${label} ${value}`.toLowerCase();
  if (/(issue|failed|pending|degraded|notready|unavailable|blocked|adminack|required|pressure)/.test(combined)) {
    return 'attention';
  }
  if (/(ready|available|current|collected|true|normal|succeeded)/.test(combined)) {
    return 'normal';
  }
  return 'collected';
};

export const evidenceRows = (item: QueueItem): RcaEvidenceRow[] =>
  item.evidence.map((line) => {
    const parsed = splitEvidenceLine(line);
    return {
      ...parsed,
      status: evidenceStatus(parsed.label, parsed.value),
    };
  });
