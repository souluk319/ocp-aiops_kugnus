import type { QueueItem, Severity } from './types';

export type AlertEventRow = {
  category: string;
  detail: string;
  id: string;
  namespace: string;
  sample: boolean;
  severity: Severity;
  source: string;
  target: string;
  time: string;
  title: string;
};

export type EventInboxGroup = {
  detail: string;
  id: string;
  kind: string;
  namespace: string;
  reason: string;
  relatedIssue?: QueueItem;
  rows: AlertEventRow[];
  severity: Severity;
  target: string;
  time: string;
  title: string;
};

export const sampleAlertEvents: AlertEventRow[] = [
  {
    category: '샘플',
    detail: '게이트웨이 이벤트 스트림이 비어 있을 때 보이는 예시 이벤트입니다.',
    id: 'sample-event-gateway-empty',
    namespace: 'komsco-ai-dev',
    sample: true,
    severity: 'warn',
    source: '샘플 데이터',
    target: 'aiops-gateway',
    time: '07. 03. 오전 09:35',
    title: '샘플: 이벤트 수집 지연',
  },
  {
    category: '샘플',
    detail: '파드 재시작 증가를 알림/이벤트 화면에서 확인하는 예시입니다.',
    id: 'sample-event-pod-restart',
    namespace: 'cyntra',
    sample: true,
    severity: 'risk',
    source: '샘플 데이터',
    target: 'cyntra-api',
    time: '07. 03. 오전 09:28',
    title: '샘플: 파드 재시작 급증',
  },
];

const eventSeverityRank: Record<Severity, number> = {
  ok: 0,
  warn: 1,
  risk: 2,
};

export const eventReason = (row: AlertEventRow): string => {
  const text = `${row.title} ${row.detail} ${row.category}`.toLowerCase();
  if (/backoff|crashloopbackoff|imagepullbackoff/.test(text)) {
    return 'BackOff';
  }
  if (/probeerror|probe error/.test(text)) {
    return 'ProbeError';
  }
  if (/unhealthy|readiness|liveness|probe/.test(text)) {
    return 'Readiness 실패';
  }
  if (/build.*fail|docker build|build/.test(text)) {
    return 'Build 실패';
  }
  if (/failed|errimagepull|image pull|pull.*fail|실패/.test(text)) {
    return 'Failed';
  }
  if (/pulled/.test(text)) {
    return 'Pulled';
  }
  if (/created/.test(text)) {
    return 'Created';
  }
  if (/scheduled/.test(text)) {
    return 'Scheduled';
  }
  if (/addedinterface/.test(text)) {
    return 'AddedInterface';
  }
  return row.title.replace(/^샘플:\s*/, '').split(' · ')[0];
};

export const eventObjectKind = (row: AlertEventRow): string => {
  const text = `${row.title} ${row.detail} ${row.source} ${row.target}`.toLowerCase();
  if (/build|docker/.test(text)) {
    return 'Build';
  }
  if (/route|ingress/.test(text)) {
    return 'Route';
  }
  if (/node|kubelet|pressure/.test(text)) {
    return 'Node';
  }
  if (/deployment|replicaset|statefulset|daemonset/.test(text)) {
    return 'Workload';
  }
  if (/pod|container|backoff|probe|scheduled|pulled|created/.test(text)) {
    return 'Pod';
  }
  return row.category === '샘플' ? 'Sample' : 'Resource';
};

export const isNormalLifecycleEvent = (row: AlertEventRow): boolean =>
  row.severity === 'ok' || /^(Pulled|Created|Scheduled|AddedInterface)$/i.test(eventReason(row));

export const isPodIssue = (item: QueueItem | undefined): boolean =>
  Boolean(item && /(^resource-pods$)|pod|pods|파드/i.test(`${item.id} ${item.title} ${item.target ?? ''}`));

export const isDerivedWorkloadIssue = (item: QueueItem | undefined): boolean =>
  Boolean(item && /deployment|디플로이먼트|replicaset|레플리카셋|statefulset|daemonset/i.test(`${item.id} ${item.title} ${item.target ?? ''}`));

const relatedIssueForEvent = (
  group: Pick<EventInboxGroup, 'kind' | 'reason' | 'target'>,
  queues: QueueItem[],
): QueueItem | undefined => {
  const haystack = `${group.kind} ${group.reason} ${group.target}`.toLowerCase();
  if (/pod|backoff|probe|failed|readiness/.test(haystack)) {
    return queues.find(isPodIssue) ?? queues.find(isDerivedWorkloadIssue);
  }
  if (/build/.test(haystack)) {
    return queues.find((item) => /build|deployment|디플로이먼트/i.test(`${item.title} ${item.detail}`));
  }
  return queues.find((item) => item.severity === 'risk') ?? queues[0];
};

export const buildEventInboxGroups = (
  rows: AlertEventRow[],
  queues: QueueItem[],
): EventInboxGroup[] => {
  const groups = new Map<string, EventInboxGroup>();

  rows.forEach((row) => {
    const reason = eventReason(row);
    const kind = eventObjectKind(row);
    const key = `${reason}-${kind}-${row.severity}`;
    const current = groups.get(key);
    if (!current) {
      const seed: EventInboxGroup = {
        detail: row.detail,
        id: key,
        kind,
        namespace: row.namespace,
        reason,
        rows: [row],
        severity: row.severity,
        target: row.target,
        time: row.time,
        title: reason,
      };
      seed.relatedIssue = relatedIssueForEvent(seed, queues);
      groups.set(key, seed);
      return;
    }

    current.rows.push(row);
    current.severity =
      eventSeverityRank[row.severity] > eventSeverityRank[current.severity]
        ? row.severity
        : current.severity;
    if (current.target === '-' && row.target !== '-') {
      current.target = row.target;
    }
    if (current.namespace === '-' && row.namespace !== '-') {
      current.namespace = row.namespace;
    }
  });

  return Array.from(groups.values()).sort(
    (a, b) =>
      eventSeverityRank[b.severity] - eventSeverityRank[a.severity] ||
      b.rows.length - a.rows.length,
  );
};

export const eventGroupFromRow = (
  row: AlertEventRow,
  queues: QueueItem[],
): EventInboxGroup => {
  const reason = eventReason(row);
  const group: EventInboxGroup = {
    detail: row.detail,
    id: row.id,
    kind: eventObjectKind(row),
    namespace: row.namespace,
    reason,
    rows: [row],
    severity: row.severity,
    target: row.target,
    time: row.time,
    title: reason,
  };
  group.relatedIssue = relatedIssueForEvent(group, queues);
  return group;
};
