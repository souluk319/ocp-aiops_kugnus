import { isDerivedWorkloadIssue, isPodIssue } from './eventInboxModel';
import { formatTime } from './portalModel';
import { evidenceLabel, evidenceRows } from './rcaEvidenceModel';
import type { ClusterSummary, QueueItem } from './types';

const displayOpenShiftVersion = (version?: string): string => {
  if (!version) {
    return '-';
  }
  return version.replace(/-local\\b/i, '');
};

export const sampleRcaQueues: QueueItem[] = [
  {
    id: 'sample-rca-cluster-update-blocked',
    title: '샘플: 클러스터 업데이트 차단',
    category: '클러스터 버전',
    detail: '현재 4.20.23 · 추천 업데이트 4.20.26, 4.20.25 · AdminAckRequired',
    evidence: [
      'current 4.20.23',
      'recommended updates 4.20.26, 4.20.25',
      'conditional updates 4.20.24',
      'reason AdminAckRequired',
      'issues 1',
    ],
    source: '샘플 데이터',
    target: 'ClusterVersion/version',
    updatedAt: '07. 03. 오전 09:40',
    severity: 'warn',
  },
  {
    id: 'sample-rca-api-latency',
    title: '샘플: API 응답 지연 조사',
    category: '샘플 RCA',
    detail: '서비스 p95 지연 1.8s · 최근 배포 직후 증가 · 파드 재시작 없음',
    evidence: [
      'target cyntra/cyntra-api',
      'cpu 82%',
      'memory 71%',
      'reason readiness probe latency increased',
      'issues 1',
    ],
    source: '샘플 데이터',
    target: 'cyntra/cyntra-api',
    updatedAt: '07. 03. 오전 09:30',
    severity: 'warn',
  },
  {
    id: 'sample-rca-node-pressure',
    title: '샘플: 워커 노드 디스크 압박',
    category: '샘플 RCA',
    detail: 'worker-2 DiskPressure · 이미지 캐시 증가 · evict 후보 파드 3개',
    evidence: [
      'target worker-2',
      'kind Node',
      'reason DiskPressure=True',
      'issues 3',
    ],
    source: '샘플 데이터',
    target: 'worker-2',
    updatedAt: '07. 03. 오전 09:24',
    severity: 'risk',
  },
];

export type RcaQueueGroup = {
  id: string;
  items: QueueItem[];
  title: string;
};

export type RcaEvidencePackRow = {
  collector: string;
  command: string;
  field: string;
  freshness: string;
  source: string;
  status: 'attention' | 'collected' | 'excluded' | 'normal';
  value: string;
};

export type RcaFindingRow = {
  detail: string;
  kicker: string;
  meta: string;
  title: string;
  tone: 'primary' | 'supporting' | 'validation';
};

export type RcaRunbookGate = {
  command: string;
  detail: string;
  gate: string;
  id: string;
  status: string;
  title: string;
  tone: 'ok' | 'warn' | 'risk';
};

export type RcaIssueType =
  | 'WORKLOAD_PODS'
  | 'WORKLOAD_DERIVED'
  | 'PLATFORM_UPDATE'
  | 'CLUSTER_OPERATOR'
  | 'NODE_HEALTH'
  | 'AIOPS_CONTROL'
  | 'OTHER';

export type PodRcaSummary = {
  active: number;
  completed: number;
  failed: number;
  issueCandidates: number;
  pending: number;
  ready: number;
  restartsTotal: number;
  running: number;
  runningNotReady: number;
  total: number;
};

export type RcaCaseHeaderModel = {
  baseline: string;
  caseState: string;
  family: string;
  finding: string;
  issueLine: string;
  metrics: Array<{ label: string; value: string }>;
  scope: string;
  title: string;
};

export type RcaCommandBundleItem = {
  command: string;
  title: string;
};

export type RcaTimelineItem = {
  detail: string;
  title: string;
};

export const isClusterUpdateIssue = (item: QueueItem): boolean =>
  item.category === '클러스터 버전' || /clusterversion|cluster update|upgradeable|업데이트 사전|ocp 업데이트/i.test(`${item.id} ${item.title} ${item.target ?? ''}`);

export const rcaIssueType = (item: QueueItem | undefined): RcaIssueType => {
  if (!item) {
    return 'OTHER';
  }
  if (isPodIssue(item)) {
    return 'WORKLOAD_PODS';
  }
  if (isDerivedWorkloadIssue(item)) {
    return 'WORKLOAD_DERIVED';
  }
  if (isClusterUpdateIssue(item)) {
    return 'PLATFORM_UPDATE';
  }
  if (item.category === '오퍼레이터') {
    return 'CLUSTER_OPERATOR';
  }
  if (item.category === '노드') {
    return 'NODE_HEALTH';
  }
  if (item.category === 'AIOps 기록') {
    return 'AIOPS_CONTROL';
  }
  return 'OTHER';
};

export const resourceById = (summary: ClusterSummary, id: string) =>
  (summary.resources?.items ?? []).find((resource) => resource.id === id);

const detailNumber = (detail: string | undefined, label: string): number => {
  if (!detail) {
    return 0;
  }
  const match = detail.match(new RegExp(`(?:^|[·,])\\s*${label}\\s+([0-9]+)`, 'i'));
  return match ? Number(match[1]) : 0;
};

export const buildPodRcaSummary = (summary: ClusterSummary): PodRcaSummary => {
  const pods = resourceById(summary, 'pods');
  const running = detailNumber(pods?.detail, 'Running');
  const ready = detailNumber(pods?.detail, 'Ready') || Number(pods?.ready ?? 0);
  const pending = detailNumber(pods?.detail, 'Pending');
  const failed = detailNumber(pods?.detail, 'Failed');
  const completed = detailNumber(pods?.detail, 'Succeeded') || detailNumber(pods?.detail, 'Completed');
  const restartsTotal = detailNumber(pods?.detail, 'Restarts');
  const runningNotReady = Math.max(0, running - ready);
  const calculatedCandidates = pending + failed + runningNotReady;
  const issueCandidates = calculatedCandidates || pods?.issues || 0;

  return {
    active: running + pending + failed,
    completed,
    failed,
    issueCandidates,
    pending,
    ready,
    restartsTotal,
    running,
    runningNotReady,
    total: pods?.total ?? 0,
  };
};

const podMetricLine = (podSummary: PodRcaSummary): string =>
  `실행중 ${podSummary.running} · 준비 ${podSummary.ready} · 대기 ${podSummary.pending} · 실패 ${podSummary.failed} · 완료 ${podSummary.completed} · 재시작 ${podSummary.restartsTotal}`;

const podIssueFormula = (podSummary: PodRcaSummary): string =>
  `이슈 후보 ${podSummary.issueCandidates} = 대기 ${podSummary.pending} + 실패 ${podSummary.failed} + 실행중 미준비 ${podSummary.runningNotReady}`;

export const buildRcaQueueGroups = (queues: QueueItem[]): RcaQueueGroup[] => {
  const groupedIds = new Set<string>();
  const take = (predicate: (item: QueueItem) => boolean) =>
    queues.filter((item) => {
      if (!predicate(item) || groupedIds.has(item.id)) {
        return false;
      }
      groupedIds.add(item.id);
      return true;
    });
  const workloadOrder = (item: QueueItem): number => {
    if (isPodIssue(item)) {
      return 0;
    }
    if (/deployment|디플로이먼트/i.test(`${item.id} ${item.title} ${item.target ?? ''}`)) {
      return 1;
    }
    if (/replicaset|레플리카셋/i.test(`${item.id} ${item.title} ${item.target ?? ''}`)) {
      return 2;
    }
    return 3;
  };
  const workloadItems = take((item) => isPodIssue(item) || isDerivedWorkloadIssue(item)).sort(
    (a, b) => workloadOrder(a) - workloadOrder(b),
  );
  const groups: RcaQueueGroup[] = [
    { id: 'workload', title: '워크로드 런타임', items: workloadItems },
    { id: 'platform', title: '플랫폼 라이프사이클', items: take((item) => isClusterUpdateIssue(item) || item.category === '오퍼레이터') },
    { id: 'infra', title: '인프라', items: take((item) => item.category === '노드') },
    { id: 'aiops', title: 'AIOps 제어', items: take((item) => item.category === 'AIOps 기록') },
  ];
  const other = queues.filter((item) => !groupedIds.has(item.id));
  if (other.length > 0) {
    groups.push({ id: 'other', title: '기타 신호', items: other });
  }
  return groups.filter((group) => group.items.length > 0);
};

export const defaultRcaSelection = (queues: QueueItem[]): string =>
  queues.find(isPodIssue)?.id ?? queues.find((item) => item.severity === 'risk')?.id ?? queues.find(isClusterUpdateIssue)?.id ?? queues[0]?.id ?? '';

export const rcaCaseId = (item: QueueItem | undefined, index: number): string =>
  item && isClusterUpdateIssue(item) ? 'RCA-20250703-004' : `RCA-20250703-${String(index + 1).padStart(3, '0')}`;

export const rcaReason = (summary: ClusterSummary, item?: QueueItem): string => {
  const reasonEvidence = item ? evidenceRows(item).find((row) => row.label === 'reason')?.value : '';
  return summary.version.upgradeableReason ?? reasonEvidence ?? 'AdminAckRequired';
};

export const rcaCurrentVersion = (summary: ClusterSummary, item?: QueueItem): string => {
  const current = item ? evidenceRows(item).find((row) => row.label === 'current')?.value : '';
  return displayOpenShiftVersion(summary.version.version ?? current ?? '-');
};

export const rcaAvailableUpdates = (summary: ClusterSummary, item?: QueueItem): string => {
  const evidence = item ? evidenceRows(item).find((row) => row.label === 'recommended updates')?.value : '';
  return summary.version.availableUpdates?.join(' · ') || evidence || '-';
};

export const rcaConditionalUpdates = (summary: ClusterSummary, item?: QueueItem): string => {
  const evidence = item ? evidenceRows(item).find((row) => row.label === 'conditional updates')?.value : '';
  return summary.version.conditionalUpdates?.join(' · ') || evidence || '-';
};

export const buildRcaCaseHeader = (
  summary: ClusterSummary,
  item: QueueItem | undefined,
  podSummary: PodRcaSummary,
  clusterName: string,
): RcaCaseHeaderModel => {
  const issueType = rcaIssueType(item);
  if (issueType === 'PLATFORM_UPDATE') {
    return {
      baseline: `클러스터 기준: OCP ${rcaCurrentVersion(summary, item)}`,
      caseState: '조사 중 · 관리자 확인 필요 · 변경 창 검증 필요',
      family: '플랫폼 라이프사이클 / RCA 케이스',
      finding: `ClusterVersion Upgradeable=False · 사유 ${rcaReason(summary, item)}`,
      issueLine: `업데이트 후보 ${rcaAvailableUpdates(summary, item)} · 조건부 업데이트 ${rcaConditionalUpdates(summary, item)}`,
      metrics: [
        { label: '현재', value: rcaCurrentVersion(summary, item) },
        { label: '후보', value: rcaAvailableUpdates(summary, item) },
        { label: '조건부', value: rcaConditionalUpdates(summary, item) },
        { label: 'CO 저하', value: String(summary.operators.degraded) },
      ],
      scope: `ClusterVersion/version · 스냅샷 ${formatTime(summary.updatedAt)} · 게이트웨이 정상`,
      title: '클러스터 업데이트 차단',
    };
  }

  if (issueType === 'WORKLOAD_PODS' || issueType === 'WORKLOAD_DERIVED') {
    const derivedTitle = issueType === 'WORKLOAD_DERIVED'
      ? `${item?.target ?? item?.title ?? '워크로드'} 가용성 변화`
      : '파드 상태 저하';
    return {
      baseline: `클러스터 기준: OCP ${displayOpenShiftVersion(summary.version.version)}`,
      caseState: '조사 중 · 증거 일부 수집 · 노드/PVC 검증 필요',
      family: issueType === 'WORKLOAD_DERIVED' ? '워크로드 런타임 / 파생 신호' : '워크로드 런타임 / RCA 케이스',
      finding: issueType === 'WORKLOAD_DERIVED'
        ? '컨트롤러 가용성 변화는 파드 준비 상태와 소유 관계를 함께 검증해야 합니다'
        : '활성 파드 상태 변화가 감지되어 컨테이너/이벤트 검증이 필요합니다',
      issueLine: `${podIssueFormula(podSummary)} · 완료 파드는 활성 상태 점수에서 제외`,
      metrics: [
        { label: '실행중', value: String(podSummary.running) },
        { label: '준비', value: String(podSummary.ready) },
        { label: '대기', value: String(podSummary.pending) },
        { label: '실패', value: String(podSummary.failed) },
        { label: '완료', value: String(podSummary.completed) },
        { label: '재시작', value: String(podSummary.restartsTotal) },
      ],
      scope: `전체 네임스페이스 · 이슈 후보 ${podSummary.issueCandidates} · 스냅샷 ${formatTime(summary.updatedAt)} · 게이트웨이 정상`,
      title: derivedTitle,
    };
  }

  return {
    baseline: `클러스터 기준: OCP ${displayOpenShiftVersion(summary.version.version)}`,
    caseState: '조사 중 · 증거 일부 수집 · 수동 검증 필요',
    family: `${issueType} / RCA 케이스`,
    finding: item?.detail ?? '게이트웨이 신호 검증 필요',
    issueLine: item?.evidence.slice(0, 3).join(' · ') || '증거 수집 대기',
    metrics: [
      { label: '클러스터', value: clusterName },
      { label: '심각도', value: item?.severity === 'risk' ? '높음' : '중간' },
      { label: '출처', value: item?.source ?? '게이트웨이 요약' },
      { label: '스냅샷', value: formatTime(summary.updatedAt) },
    ],
    scope: `${item?.target ?? '클러스터 범위'} · 게이트웨이 정상`,
    title: item?.title ?? '조사 대상 없음',
  };
};

export const rcaQueueBadgeLabel = (item: QueueItem): string => {
  if (isDerivedWorkloadIssue(item)) {
    return '파생';
  }
  return item.severity === 'risk' ? '높음' : '중간';
};

export const rcaQueueDetail = (summary: ClusterSummary, item: QueueItem, podSummary: PodRcaSummary): string => {
  if (isPodIssue(item)) {
    return `활성 이슈 후보 ${podSummary.issueCandidates}개 · 재시작 ${podSummary.restartsTotal}`;
  }
  if (isDerivedWorkloadIssue(item)) {
    return `${item.detail} · 파드 준비 상태에서 파생`;
  }
  if (isClusterUpdateIssue(item)) {
    return `ClusterVersion ${rcaCurrentVersion(summary, item)} · ${rcaReason(summary, item)}`;
  }
  return item.detail;
};

export const buildRcaFindings = (summary: ClusterSummary, item: QueueItem | undefined, podSummary: PodRcaSummary): RcaFindingRow[] => {
  if (!item) {
    return [];
  }

  if (isClusterUpdateIssue(item)) {
    const reason = rcaReason(summary, item);
    return [
      {
        detail: `Reason ${reason}`,
        kicker: '주 원인',
        meta: '신뢰도 높음 · 증거 5 · 미검증 2 · 반증 0',
        title: 'ClusterVersion Upgradeable=False',
        tone: 'primary',
      },
      {
        detail: `${rcaCurrentVersion(summary, item)} -> ${rcaAvailableUpdates(summary, item)}`,
        kicker: '보조 근거',
        meta: `conditionalUpdates ${rcaConditionalUpdates(summary, item)}`,
        title: '추천 업데이트 경로 존재',
        tone: 'supporting',
      },
      {
        detail: 'ClusterOperators, MachineConfigPools, Nodes 상태를 추가 검증해야 합니다.',
        kicker: '추가 검증',
        meta: 'CO status · MCP degraded/updating · NotReady nodes',
        title: '플랫폼 의존성 게이트',
        tone: 'validation',
      },
    ];
  }

  if (isPodIssue(item) || isDerivedWorkloadIssue(item)) {
    return [
      {
        detail: isDerivedWorkloadIssue(item)
          ? '컨트롤러 가용성 변화가 관측됐으며, 실제 원인은 관련 파드 상태와 이벤트로 확인해야 합니다.'
          : '현재 실패/대기 상태가 관측됐으며, 실제 원인은 컨테이너 종료 사유와 이벤트로 확인해야 합니다.',
        kicker: '주 원인 후보',
        meta: `${podMetricLine(podSummary)} · 이슈 후보 ${podSummary.issueCandidates}`,
        title: isDerivedWorkloadIssue(item) ? '컨트롤러 가용성 변화' : '파드 런타임 이상 신호',
        tone: 'primary',
      },
      {
        detail: '파드 -> 컨테이너 상태 -> 이벤트 -> 소유 관계 -> 노드 -> PVC 순서로 검증합니다.',
        kicker: '보조 근거',
        meta: `활성 ${podSummary.active} · 완료 ${podSummary.completed} 제외 · 재시작 ${podSummary.restartsTotal}`,
        title: '예상 점검 경로',
        tone: 'supporting',
      },
      {
        detail: '컨테이너 대기 사유, 마지막 종료 상태, 재시작 상위 파드, 경고 이벤트, 노드 압박, 볼륨 마운트 실패 증거가 아직 필요합니다.',
        kicker: '추가 검증',
        meta: '컨테이너 상태 · 이벤트 · 재시작 상위 · 노드 압박 · PVC 마운트',
        title: '미수집 증거',
        tone: 'validation',
      },
    ];
  }

  return [
    {
      detail: item.detail,
      kicker: '주 원인',
      meta: `${item.category ?? '운영 이슈'} · ${item.source ?? '게이트웨이 요약'}`,
      title: item.title,
      tone: 'primary',
    },
    {
      detail: 'Pod phase, container state, restart count, events를 같은 네임스페이스 기준으로 확인합니다.',
      kicker: '보조 근거',
      meta: 'Pod lifecycle · Event stream · Controller status',
      title: '워크로드 런타임 신호',
      tone: 'supporting',
    },
    {
      detail: 'Node condition, PVC mount, image pull, readiness/liveness probe를 배제해야 합니다.',
      kicker: '추가 검증',
      meta: 'Node · PVC · Image · Probe',
      title: '런타임 의존성 점검',
      tone: 'validation',
    },
  ];
};

export const buildRcaEvidencePack = (
  summary: ClusterSummary,
  item: QueueItem | undefined,
  podSummary: PodRcaSummary,
): RcaEvidencePackRow[] => {
  const collectedAt = formatTime(summary.updatedAt) || item?.updatedAt || '-';
  if (item && isClusterUpdateIssue(item)) {
    const reason = rcaReason(summary, item);
    return [
      {
        collector: 'gateway/config.openshift.io',
        command: 'oc get clusterversion version -o yaml',
        field: 'status.desired.version',
        freshness: '실시간',
        source: 'ClusterVersion/version',
        status: 'normal',
        value: rcaCurrentVersion(summary, item),
      },
      {
        collector: 'gateway/config.openshift.io',
        command: 'oc get clusterversion version -o jsonpath={.status.availableUpdates}',
        field: 'status.availableUpdates',
        freshness: collectedAt,
        source: 'ClusterVersion/version',
        status: 'collected',
        value: rcaAvailableUpdates(summary, item),
      },
      {
        collector: 'gateway/config.openshift.io',
        command: 'oc get clusterversion version -o jsonpath={.status.conditionalUpdates}',
        field: 'status.conditionalUpdates',
        freshness: collectedAt,
        source: 'ClusterVersion/version',
        status: 'collected',
        value: rcaConditionalUpdates(summary, item),
      },
      {
        collector: 'gateway/config.openshift.io',
        command: 'oc get clusterversion version -o yaml',
        field: 'conditions[Upgradeable].status',
        freshness: collectedAt,
        source: 'ClusterVersion/version',
        status: 'attention',
        value: summary.version.upgradeable === false || reason !== '-' ? 'False' : '-',
      },
      {
        collector: 'gateway/config.openshift.io',
        command: 'oc get clusterversion version -o yaml',
        field: 'conditions[Upgradeable].reason',
        freshness: collectedAt,
        source: 'ClusterVersion/version',
        status: 'attention',
        value: reason,
      },
      {
        collector: 'gateway/config.openshift.io',
        command: 'oc get clusterversion version -o yaml',
        field: 'conditions[Upgradeable].message',
        freshness: collectedAt,
        source: 'ClusterVersion/version',
        status: 'collected',
        value: summary.version.upgradeableMessage ?? 'Admin acknowledgement required before this update edge can proceed.',
      },
    ];
  }

  if (item && (isPodIssue(item) || isDerivedWorkloadIssue(item))) {
    const inventoryCommand = 'oc get pods -A -o json';
    return [
      {
        collector: '게이트웨이 클러스터 요약',
        command: inventoryCommand,
        field: '종류',
        freshness: collectedAt,
        source: '파드 인벤토리',
        status: 'collected',
        value: 'Pod',
      },
      {
        collector: '게이트웨이 클러스터 요약',
        command: inventoryCommand,
        field: '전체',
        freshness: collectedAt,
        source: '파드 인벤토리',
        status: 'collected',
        value: String(podSummary.total),
      },
      {
        collector: '게이트웨이 클러스터 요약',
        command: inventoryCommand,
        field: '실행중',
        freshness: collectedAt,
        source: '파드 인벤토리',
        status: 'collected',
        value: String(podSummary.running),
      },
      {
        collector: '게이트웨이 클러스터 요약',
        command: inventoryCommand,
        field: '준비',
        freshness: collectedAt,
        source: '파드 인벤토리',
        status: 'collected',
        value: String(podSummary.ready),
      },
      {
        collector: '게이트웨이 클러스터 요약',
        command: inventoryCommand,
        field: '대기',
        freshness: collectedAt,
        source: '파드 인벤토리',
        status: podSummary.pending > 0 ? 'attention' : 'normal',
        value: String(podSummary.pending),
      },
      {
        collector: '게이트웨이 클러스터 요약',
        command: inventoryCommand,
        field: '실패',
        freshness: collectedAt,
        source: '파드 인벤토리',
        status: podSummary.failed > 0 ? 'attention' : 'normal',
        value: String(podSummary.failed),
      },
      {
        collector: '게이트웨이 클러스터 요약',
        command: inventoryCommand,
        field: '완료',
        freshness: collectedAt,
        source: '파드 인벤토리',
        status: 'excluded',
        value: String(podSummary.completed),
      },
      {
        collector: '게이트웨이 클러스터 요약',
        command: inventoryCommand,
        field: '이슈 후보',
        freshness: collectedAt,
        source: '파드 상태 계산',
        status: podSummary.issueCandidates > 0 ? 'attention' : 'normal',
        value: String(podSummary.issueCandidates),
      },
      {
        collector: '게이트웨이 클러스터 요약',
        command: inventoryCommand,
        field: '총 재시작',
        freshness: collectedAt,
        source: '파드 재시작 요약',
        status: podSummary.restartsTotal > 0 ? 'attention' : 'normal',
        value: String(podSummary.restartsTotal),
      },
    ];
  }

  return (item ? evidenceRows(item) : []).map((row): RcaEvidencePackRow => ({
    collector: item?.source ?? '게이트웨이 요약',
    command: item?.category === '노드' ? 'oc describe node <node>' : 'oc describe pod -n <namespace> <pod>',
    field: evidenceLabel(row.label),
    freshness: item?.updatedAt ?? collectedAt,
    source: item?.target ?? item?.title ?? '-',
    status: row.status,
    value: row.value,
  }));
};

export const buildRcaRunbookGates = (
  summary: ClusterSummary,
  item: QueueItem | undefined,
  podSummary: PodRcaSummary,
): RcaRunbookGate[] => {
  if (item && isClusterUpdateIssue(item)) {
    return [
      {
        command: 'oc get clusterversion version -o yaml',
        detail: 'ClusterVersion 조건과 history를 원본 YAML로 확인합니다.',
        gate: 'Upgradeable=False',
        id: 'cv-condition',
        status: '필수',
        title: 'ClusterVersion 조건 확인',
        tone: 'warn',
      },
      {
        command: 'oc get clusterversion version -o jsonpath={.status.conditions[?(@.type=="Upgradeable")].reason}',
        detail: `Reason ${rcaReason(summary, item)}`,
        gate: 'AdminAckRequired',
        id: 'upgradeable-reason',
        status: '게이트 실패',
        title: 'Upgradeable 사유 확인',
        tone: 'risk',
      },
      {
        command: 'oc get clusterversion version -o jsonpath={.status.availableUpdates}',
        detail: `availableUpdates ${rcaAvailableUpdates(summary, item)} · conditionalUpdates ${rcaConditionalUpdates(summary, item)}`,
        gate: '추천 edge / 조건부 edge 분리',
        id: 'update-edges',
        status: '수집됨',
        title: '업데이트 경로 비교',
        tone: 'ok',
      },
      {
        command: 'oc get clusteroperators',
        detail: `Available ${summary.operators.available}/${summary.operators.total} · Degraded ${summary.operators.degraded}`,
        gate: 'Available=True, Degraded=False',
        id: 'clusteroperators',
        status: summary.operators.degraded > 0 ? '게이트 실패' : '수집됨',
        title: 'ClusterOperators 점검',
        tone: summary.operators.degraded > 0 ? 'risk' : 'ok',
      },
      {
        command: 'oc get mcp && oc get nodes',
        detail: `Ready nodes ${summary.nodes.ready}/${summary.nodes.total} · NotReady ${summary.nodes.notReady}`,
        gate: 'DEGRADED=False, NotReady=0',
        id: 'mcp-nodes',
        status: '미수집',
        title: 'MCP / 노드 준비 상태 점검',
        tone: summary.nodes.notReady > 0 ? 'risk' : 'warn',
      },
      {
        command: 'oc adm upgrade --acknowledge <admin-ack-id>',
        detail: 'Admin acknowledgement 또는 change ticket 필요 여부를 결정합니다.',
        gate: '변경 승인 필요',
        id: 'change-request',
        status: '권장',
        title: '변경 승인 생성',
        tone: 'warn',
      },
    ];
  }

  if (item && (isPodIssue(item) || isDerivedWorkloadIssue(item))) {
    return [
      {
        command: 'oc get pods -A -o wide',
        detail: podMetricLine(podSummary),
        gate: `대기 / 실패 / 실행중 미준비 / 재시작 상위 파드 확인 · ${podIssueFormula(podSummary)}`,
        id: 'pod-inventory',
        status: '수집됨',
        title: '파드 인벤토리 및 준비 상태',
        tone: podSummary.issueCandidates > 0 ? 'risk' : 'ok',
      },
      {
        command: 'oc get pods -A -o json',
        detail: '컨테이너 대기 사유, 마지막 종료 상태, restartCount 상위 파드가 필요합니다.',
        gate: '컨테이너 대기/종료/재시작 상태',
        id: 'container-state',
        status: '미수집',
        title: '컨테이너 상태 증거',
        tone: 'warn',
      },
      {
        command: 'oc get events -A --field-selector involvedObject.kind=Pod --sort-by=.lastTimestamp',
        detail: '최근 Warning 이벤트와 probe/image/volume 관련 reason을 확인합니다.',
        gate: '최근 경고 이벤트',
        id: 'pod-events',
        status: '필수',
        title: '최근 파드 경고 이벤트',
        tone: 'warn',
      },
      {
        command: 'oc get deploy,rs,sts,ds -A',
        detail: 'Deployment / ReplicaSet / StatefulSet / DaemonSet owner chain을 파드 후보와 연결합니다.',
        gate: '소유 관계 매핑',
        id: 'owner-chain',
        status: isDerivedWorkloadIssue(item) ? '필수' : '권장',
        title: '컨트롤러 소유 관계',
        tone: 'warn',
      },
      {
        command: 'oc get nodes && oc get pvc -A',
        detail: `Node Ready ${summary.nodes.ready}/${summary.nodes.total} · PVC ${resourceById(summary, 'persistentvolumeclaims')?.score ?? '-'}`,
        gate: '노드 압박 / PVC 마운트 검증',
        id: 'runtime-dependency',
        status: '미수집',
        title: '런타임 의존성 검증',
        tone: summary.nodes.notReady > 0 ? 'risk' : 'warn',
      },
    ];
  }

  return [
    {
      command: 'oc get pods -A -o wide',
      detail: '비정상 파드를 네임스페이스 기준으로 분리합니다.',
      gate: 'Pending/Failed/CrashLoopBackOff',
      id: 'pod-phase',
      status: '필수',
      title: '파드 phase / 컨테이너 상태 확인',
      tone: 'warn',
    },
    {
      command: 'oc describe pod -n <namespace> <pod>',
      detail: '이벤트, probe, image pull, volume mount 실패를 확인합니다.',
      gate: 'Events / Probe / Image / Volume',
      id: 'pod-events',
      status: '필수',
      title: '파드 이벤트 확인',
      tone: 'warn',
    },
    {
      command: 'oc get node && oc describe node <node>',
      detail: '스케줄링/노드 압박/NotReady를 배제합니다.',
      gate: 'Node Ready=True',
      id: 'node-check',
      status: '미수집',
      title: '노드 의존성 점검',
      tone: 'warn',
    },
  ];
};

export const buildRcaCommandBundle = (
  item: QueueItem | undefined,
  runbookGates: RcaRunbookGate[],
): RcaCommandBundleItem[] => {
  if (item && (isPodIssue(item) || isDerivedWorkloadIssue(item))) {
    return [
      { title: '파드 인벤토리', command: 'oc get pods -A -o wide' },
      {
        title: '최근 파드 경고',
        command: 'oc get events -A --field-selector involvedObject.kind=Pod --sort-by=.lastTimestamp',
      },
      { title: '선택 파드 상세', command: 'oc describe pod -n <namespace> <pod>' },
      { title: '파드 YAML', command: 'oc get pod -n <namespace> <pod> -o yaml' },
      { title: '소유 관계', command: 'oc get deploy,rs,sts,ds -A' },
    ];
  }

  return runbookGates.map((gate) => ({ title: gate.title, command: gate.command }));
};

export const buildRcaTimeline = (
  summary: ClusterSummary,
  item: QueueItem | undefined,
  podSummary: PodRcaSummary,
  findings: RcaFindingRow[],
): RcaTimelineItem[] => {
  if (item && (isPodIssue(item) || isDerivedWorkloadIssue(item))) {
    return [
      {
        detail: podMetricLine(podSummary),
        title: '파드 인벤토리 수집',
      },
      {
        detail: `${podIssueFormula(podSummary)} · 완료 ${podSummary.completed}개 제외`,
        title: '이슈 후보 계산',
      },
      {
        detail: 'Deployment · ReplicaSet · StatefulSet · DaemonSet 소유 관계 매핑 필요',
        title: '컨트롤러 소유 관계 대기',
      },
      {
        detail: `노드 정상 ${summary.nodes.ready}/${summary.nodes.total} · PVC ${resourceById(summary, 'persistentvolumeclaims')?.score ?? '-'}`,
        title: '런타임 의존성 연결',
      },
      {
        detail: findings[0]?.title ?? '컨테이너/이벤트 검증 필요',
        title: 'RCA 판단 생성',
      },
    ];
  }

  if (item && isClusterUpdateIssue(item)) {
    return [
      { detail: 'ClusterVersion Upgradeable 상태 수집', title: 'ClusterVersion condition collected' },
      { detail: 'availableUpdates / conditionalUpdates 비교', title: 'Update edges parsed' },
      { detail: `Reason ${rcaReason(summary, item)}`, title: 'AdminAckRequired detected' },
      { detail: findings[0]?.title ?? 'ClusterVersion finding generated', title: 'RCA judgment generated' },
    ];
  }

  return [
    { detail: item?.source ?? '게이트웨이 요약', title: 'Signal collected' },
    { detail: item?.detail ?? '증거 수집 대기', title: 'Evidence reviewed' },
    { detail: findings[0]?.title ?? '판단 생성 대기', title: 'RCA judgment generated' },
  ];
};
