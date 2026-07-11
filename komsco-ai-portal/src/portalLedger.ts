import { formatTime } from './portalModel';
import type { ActivityItem, AiopsRecord, AiopsRuntimeStatus } from './types';

const asObject = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' ? (value as Record<string, unknown>) : {};

const textValue = (value: unknown, fallback = '-'): string => {
  if (value === undefined || value === null || value === '') return fallback;
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return JSON.stringify(value);
};

export const actionRecords = (status: AiopsRuntimeStatus): AiopsRecord[] => [
  ...status.spec.records.actionProposals,
  ...status.spec.records.sealedActionPlans,
  ...status.spec.records.approvalDecisions,
  ...status.spec.records.executionRecords,
];

export const recordPhase = (record: AiopsRecord): string => {
  const spec = asObject(record.spec);
  const status = asObject(spec.status);
  const approvalDecision = asObject(spec.approvalDecision);
  const mutationOutcome = asObject(spec.mutationOutcome);

  return textValue(
    status.phase ?? approvalDecision.status ?? mutationOutcome.status ?? spec.action,
    'recorded',
  );
};

export const recordTarget = (record: AiopsRecord): string => {
  const spec = asObject(record.spec);
  const target = asObject(spec.target);
  const candidate = asObject(spec.candidate);
  const candidateTarget = asObject(candidate.targetNode);
  const sealedActionPlan = asObject(spec.sealedActionPlan);
  const sealedTarget = asObject(sealedActionPlan.target);
  const finalTarget =
    Object.keys(target).length > 0
      ? target
      : Object.keys(candidateTarget).length > 0
        ? candidateTarget
        : sealedTarget;
  const namespace = textValue(finalTarget.namespace, '');
  const name = textValue(finalTarget.name ?? finalTarget.nodeName ?? spec.requestId, '');

  if (namespace && name) {
    return `${namespace}/${name}`;
  }

  return name || textValue(spec.runId ?? spec.incidentId, '-');
};

export const recordKindLabel = (kind?: string): string => {
  const labels: Record<string, string> = {
    ActionProposal: '조치 제안',
    ActionProposalRecord: '조치 후보 생성',
    ApprovalDecision: '승인 결정',
    ApprovalDecisionRecord: '승인 결정',
    AuditRecord: '감사',
    DiagnosticRequestRecord: '진단',
    ExecutionRecord: '실행/검토 기록',
    SealedActionPlan: '승인 필요 계획',
    SealedActionPlanRecord: '승인용 계획 생성',
  };
  return kind ? labels[kind] ?? kind : '기록';
};

const recordTone = (record: AiopsRecord, variant: 'audit' | 'action' = 'action'): ActivityItem['tone'] => {
  if (variant === 'audit') {
    return 'blue';
  }

  const phase = recordPhase(record).toLowerCase();
  if (phase.includes('failed') || phase.includes('denied') || phase.includes('rejected') || phase.includes('error')) {
    return 'red';
  }
  if (phase.includes('succeeded') || phase.includes('approved') || phase.includes('completed')) {
    return 'green';
  }
  if (phase.includes('pending') || phase.includes('proposed') || phase.includes('sealed')) {
    return 'orange';
  }
  return 'violet';
};

export type LedgerEntry = {
  action: string;
  actor: string;
  artifact: string;
  auditId: string;
  category: 'approval' | 'evidence' | 'gateway' | 'mutation' | 'proposal';
  evidenceId: string;
  gate: string;
  id: string;
  kind: string;
  name: string;
  namespace: string;
  phase: string;
  result: string;
  runId: string;
  sample: boolean;
  target: string;
  time: string;
  title: string;
  tone: ActivityItem['tone'];
  variant: 'action' | 'audit';
};

const targetProjection = (record: AiopsRecord): { kind: string; name: string; namespace: string; target: string } => {
  const spec = asObject(record.spec);
  const target = asObject(spec.target);
  const candidate = asObject(spec.candidate);
  const candidateTarget = asObject(candidate.targetNode);
  const sealedActionPlan = asObject(spec.sealedActionPlan);
  const sealedTarget = asObject(sealedActionPlan.target);
  const finalTarget =
    Object.keys(target).length > 0
      ? target
      : Object.keys(candidateTarget).length > 0
        ? candidateTarget
        : sealedTarget;
  const namespace = textValue(finalTarget.namespace, '');
  const kind = textValue(finalTarget.kind ?? finalTarget.resource ?? finalTarget.resourceKind, '');
  const name = textValue(finalTarget.name ?? finalTarget.nodeName ?? spec.runId ?? spec.requestId, '');
  const parts = [namespace, kind, name].filter(Boolean);

  return {
    kind: kind || '-',
    name: name || '-',
    namespace: namespace || '-',
    target: parts.length > 0 ? parts.join(' / ') : recordTarget(record),
  };
};

const ledgerCategory = (record: AiopsRecord, variant: 'action' | 'audit'): LedgerEntry['category'] => {
  const kind = record.kind ?? '';
  const action = textValue(asObject(record.spec).action, '').toLowerCase();
  if (variant === 'audit') {
    if (action.includes('evidence')) {
      return 'evidence';
    }
    if (action.includes('approval')) {
      return 'approval';
    }
    return 'gateway';
  }
  if (kind === 'ExecutionRecord') {
    return 'mutation';
  }
  if (kind === 'ApprovalDecision' || kind === 'SealedActionPlan') {
    return 'approval';
  }
  return 'proposal';
};

const ledgerPhase = (entry: Pick<LedgerEntry, 'category'>, record: AiopsRecord, variant: 'action' | 'audit'): string => {
  if (variant === 'audit') {
    const labels: Record<LedgerEntry['category'], string> = {
      approval: '승인',
      evidence: '증거 수집',
      gateway: '접수',
      mutation: '변경 실행',
      proposal: '조치 제안',
    };
    return labels[entry.category];
  }
  const labels: Record<string, string> = {
    ActionProposal: '조치 후보 생성',
    ActionProposalRecord: '조치 후보 생성',
    ApprovalDecision: '승인 결정',
    ApprovalDecisionRecord: '승인 결정',
    ExecutionRecord: '실행/검토 기록',
    SealedActionPlan: '승인용 계획 생성',
    SealedActionPlanRecord: '승인용 계획 생성',
  };
  return labels[record.kind ?? ''] ?? recordKindLabel(record.kind);
};

export const buildLedgerEntries = (
  records: AiopsRecord[],
  auditRecords: AiopsRecord[],
  options: { sample: boolean },
): LedgerEntry[] => {
  const input = [
    ...records.map((record) => ({ record, variant: 'action' as const })),
    ...auditRecords.map((record) => ({ record, variant: 'audit' as const })),
  ];

  return input
    .map(({ record, variant }, index): LedgerEntry => {
      const spec = asObject(record.spec);
      const target = targetProjection(record);
      const category = ledgerCategory(record, variant);
      const phase = ledgerPhase({ category }, record, variant);
      const action = textValue(spec.action, variant === 'audit' ? textValue(spec.action, record.metadata?.name ?? 'audit_record') : recordPhase(record));
      const result = textValue(spec.result ?? recordPhase(record), variant === 'audit' ? 'recorded' : 'recorded');
      const runId = textValue(spec.runId ?? spec.requestId, 'crashloop-remediation');
      const time = record.metadata?.createdAt ?? '';
      const title = record.metadata?.name ?? action;

      return {
        action,
        actor: textValue(spec.actor, variant === 'audit' ? 'gateway' : 'aiops-gateway'),
        artifact: textValue(spec.artifact ?? spec.requestId ?? spec.runId, '-'),
        auditId: textValue(spec.auditId ?? record.metadata?.name, '-'),
        category,
        evidenceId: textValue(spec.evidenceId, '-'),
        gate: textValue(spec.gate, category === 'mutation' ? 'Executor' : category === 'approval' ? 'Approval' : 'Gateway'),
        id: `${variant}-${record.kind ?? 'record'}-${record.metadata?.name ?? index}`,
        kind: target.kind,
        name: target.name,
        namespace: target.namespace,
        phase,
        result,
        runId,
        sample: options.sample,
        target: target.target,
        time,
        title,
        tone: recordTone(record, variant),
        variant,
      };
    })
    .sort((a, b) => String(a.time).localeCompare(String(b.time)));
};

export const runWindowLabel = (entries: LedgerEntry[]): string => {
  if (entries.length === 0) {
    return '-';
  }
  const first = formatTime(entries[0].time);
  const last = formatTime(entries[entries.length - 1].time);
  return first === last ? first : `${first} - ${last}`;
};

export const ledgerNamespaceRangeLabel = (entries: LedgerEntry[]): string => {
  const namespaces = Array.from(new Set(entries.map((entry) => entry.namespace).filter((namespace) => namespace && namespace !== '-')));
  if (namespaces.length === 0) {
    return '전체/미지정';
  }
  if (namespaces.length === 1) {
    return namespaces[0];
  }
  return `혼합 ${namespaces.length}개 네임스페이스`;
};

export const ledgerActionLabel = (value: string): string => {
  const labels: Record<string, string> = {
    approval_recorded: '승인 기록',
    approve_mutation: '변경 승인',
    audit_record: '감사 기록',
    chat_request_accepted: '요청 접수',
    chat_request_completed: '요청 처리 완료',
    evidence_collected: '증거 수집',
    executed: '승인 결정 처리',
    proposed: '조치 후보 생성',
    recorded: '기록 저장',
    review_recorded: '검토 기록 저장',
    restart_rollout: '롤아웃 재시작 제안',
    rollout_restart: '롤아웃 재시작 실행',
    sealed: '승인용 계획 생성',
    seal_mutation_plan: '변경 계획 봉인',
    sealed_pending_approval: '승인 대기 계획',
  };
  return labels[value] ?? value;
};

export const ledgerGateLabel = (value: string): string => {
  const labels: Record<string, string> = {
    Approval: '승인',
    'Approval Seal': '승인 검증',
    Diagnostics: '진단',
    Executor: '실행기',
    Gateway: '게이트웨이',
    Ledger: '원장',
  };
  return labels[value] ?? value;
};

export const ledgerKindLabel = (value: string): string => {
  const labels: Record<string, string> = {
    Approval: '승인',
    DaemonSet: '데몬셋',
    Deployment: '디플로이먼트',
    Evidence: '증거',
    Node: '노드',
    Pod: '파드',
    ReplicaSet: '레플리카셋',
    Route: '라우트',
    Run: '실행',
    Service: '서비스',
    StatefulSet: '스테이트풀셋',
  };
  return labels[value] ?? value;
};

export const resourceNameLabel = (id: string, name: string, kind: string): string => {
  const labels: Record<string, string> = {
    clusteroperators: '클러스터 오퍼레이터',
    daemonsets: '데몬셋',
    deployments: '디플로이먼트',
    nodes: '노드',
    persistentvolumeclaims: 'PVC',
    pods: '파드',
    replicasets: '레플리카셋',
    routes: '라우트',
    services: '서비스',
    statefulsets: '스테이트풀셋',
  };
  const kindLabel = ledgerKindLabel(kind);
  return labels[id] ?? (kindLabel || name);
};

export const ledgerTargetLabel = (entry: Pick<LedgerEntry, 'kind' | 'name' | 'namespace' | 'target'>): string => {
  const parts = [
    entry.namespace !== '-' ? entry.namespace : '',
    entry.kind !== '-' ? ledgerKindLabel(entry.kind) : '',
    entry.name !== '-' ? entry.name : '',
  ].filter(Boolean);

  return parts.length > 0 ? parts.join(' / ') : entry.target;
};

export const ledgerResultLabel = (value: string): string => {
  const labels: Record<string, string> = {
    accepted: '접수됨',
    approved: '승인됨',
    blocked: '차단됨',
    collected: '수집됨',
    executed: '처리됨',
    failed: '실패',
    proposed: '제안됨',
    recorded: '기록됨',
    review_recorded: '검토 기록 완료',
    sealed: '승인 대기 계획',
    sealed_pending_approval: '승인 대기',
    succeeded: '성공',
    waiting_approval: '승인 대기',
  };
  return labels[value] ?? value;
};

export const mutationStatusLabel = (value: string): string => {
  const labels: Record<string, string> = {
    Blocked: '차단됨',
    Executed: '실행됨',
    'Not executed': '미실행',
    'Waiting approval': '승인 대기',
  };
  return labels[value] ?? value;
};
