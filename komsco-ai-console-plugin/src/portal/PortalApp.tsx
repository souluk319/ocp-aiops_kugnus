import * as React from 'react';
import {
  ChevronLeft,
  ChevronRight,
  ClipboardCheck,
  Cpu,
  FileText,
  GitBranch,
  Network,
  Search,
  ShieldCheck,
  X,
} from 'lucide-react';
import AssistantLauncher from '../components/AssistantLauncher';
import type {
  AiopsExecutionMode,
  AssistantDraftPrompt,
  AssistantLaunchContext,
} from '../components/assistant.types';
import {
  standaloneRouteByView,
  viewFromLocation,
} from './portalNavigation';
import { RcaView } from './RcaView';
import { severityClass, severityLabel, StatusBadge } from './portalBadges';
import {
  actionRecords,
  ledgerActionLabel,
  ledgerKindLabel,
  ledgerResultLabel,
  recordKindLabel,
  recordPhase,
  recordTarget,
} from './executionLedgerModel';
import { ExecutionRecordsView } from './ExecutionRecordsView';
import { DashboardView, KpiCard } from './DashboardView';
import {
  sampleAlertEvents,
} from './eventInboxModel';
import type { AlertEventRow, EventInboxGroup } from './eventInboxModel';
import { AlertsEventsView } from './AlertsEventsView';
import { aiopsAlarmCount, formatTime } from './portalModel';
import { evidenceLabel, evidenceRows, evidenceStatusLabel } from './rcaEvidenceModel';
import { useLiveClock, usePortalRuntime } from './portalRuntime';
import { ClusterSignalStrip, Sidebar, Topbar } from './portalShell';
import { ReportsView } from './ReportsView';
import { WikiDocsView } from './WikiDocsView';
import { buildPodRcaSummary, resourceById, sampleRcaQueues } from './rcaViewModel';
import type {
  ActivityItem,
  AiopsEventFeed,
  AiopsEventItem,
  AiopsRuntimeStatus,
  AlertItem,
  ClusterSummary,
  Endpoint,
  NavView,
  QueueItem,
  ScopeItem,
  Severity,
} from './types';
import './styles.css';

type AssistantLaunchRequest = {
  context: AssistantLaunchContext;
  executionMode?: AiopsExecutionMode;
  taskMode?: AssistantDraftPrompt['taskMode'];
};

type AssistantLaunchHandler = (request: AssistantLaunchRequest) => void;

const cleanAssistantText = (value?: string): string | undefined => {
  const text = value?.trim();
  return text && text !== '-' ? text : undefined;
};

const parseAssistantTarget = (
  target?: string,
  fallbackKind?: string,
): Pick<AssistantLaunchContext, 'kind' | 'name' | 'namespace'> => {
  const cleanTarget = cleanAssistantText(target);
  if (!cleanTarget) {
    return fallbackKind ? { kind: fallbackKind } : {};
  }

  const slashParts = cleanTarget
    .split(/\s*\/\s*/)
    .map((part) => part.trim())
    .filter(Boolean);

  if (slashParts.length >= 3) {
    return {
      namespace: cleanAssistantText(slashParts[0]),
      kind: cleanAssistantText(slashParts[1]) ?? fallbackKind,
      name: cleanAssistantText(slashParts.slice(2).join('/')),
    };
  }

  if (slashParts.length === 2) {
    return {
      namespace: cleanAssistantText(slashParts[0]),
      kind: fallbackKind,
      name: cleanAssistantText(slashParts[1]),
    };
  }

  return {
    kind: fallbackKind,
    name: cleanTarget,
  };
};

const resourceEvidenceValue = (item: QueueItem, key: 'kind' | 'total' | 'ready' | 'issues'): string | undefined => {
  const prefix = `${key} `;
  return item.evidence
    .find((entry) => entry.toLowerCase().startsWith(prefix))
    ?.slice(prefix.length)
    .trim();
};

const isResourceSummaryQueueItem = (item: QueueItem): boolean =>
  item.id.startsWith('resource-') || item.source === '게이트웨이 클러스터 요약';

const resourceSummaryEvidenceLine = (entry: string): string => {
  const [key, ...rest] = entry.trim().split(/\s+/);
  const value = rest.join(' ');
  const labels: Record<string, string> = {
    issues: '이슈 수',
    kind: '리소스 종류',
    ready: 'Ready 수',
    total: '전체 수',
  };
  return labels[key] && value ? `${labels[key]}: ${value}` : entry;
};

const assistantTargetLine = (context: AssistantLaunchContext): string =>
  [context.namespace, context.kind, context.name].filter(Boolean).join(' / ') ||
  context.name ||
  context.reason ||
  '클러스터';

const buildAssistantPrompt = (context: AssistantLaunchContext): string => {
  const evidence = context.evidenceRefs?.filter(Boolean).slice(0, 4) ?? [];
  return [
    '다음 AIOps for OCP 운영 신호를 RCA 관점으로 분석하고 필요한 경우 Action Plan 판단 조건까지 제시해줘.',
    '',
    `대상: ${assistantTargetLine(context)}`,
    context.severity ? `심각도: ${context.severity}` : '',
    context.reason ? `이유: ${context.reason}` : '',
    context.actionType ? `요청 작업: ${context.actionType}` : '',
    evidence.length > 0 ? `확인 결과: ${evidence.join(' / ')}` : '',
    '',
    '답변 형식: 요약, 영향 범위, 확인 결과, 원인 후보, Action Plan, 검증/롤백, 추가 확인 순서.',
  ]
    .filter((line) => line !== '')
    .join('\n');
};

const buildResourceSummaryAssistantPrompt = (item: QueueItem, resourceKind: string): string => {
  const evidence = item.evidence.filter(Boolean).slice(0, 6).map(resourceSummaryEvidenceLine);
  return [
    '다음 AIOps for OCP 운영 신호를 RCA 관점으로 분석하고 필요한 경우 Action Plan 판단 조건까지 제시해줘.',
    '',
    `대상: ${ledgerKindLabel(resourceKind)} 리소스 전체 요약`,
    '범위: 접근 가능한 전체 namespace',
    '신호 성격: 특정 Pod 또는 Deployment 하나가 아니라 클러스터 리소스 집계 결과',
    item.severity ? `심각도: ${item.severity}` : '',
    item.detail ? `이유: ${item.detail}` : '',
    '요청 작업: resource_summary_rca',
    evidence.length > 0 ? ['확인 결과:', ...evidence.map((line) => `- ${line}`)].join('\n') : '',
    '',
    '답변 형식: 요약, 영향 범위, 확인 결과, 원인 후보, Action Plan, 검증/롤백, 추가 확인 순서.',
  ]
    .filter((line) => line !== '')
    .join('\n');
};

const queueAssistantContext = (
  item: QueueItem,
  source: AssistantLaunchContext['source'],
  actionType = 'rca',
): AssistantLaunchContext => {
  if (isResourceSummaryQueueItem(item)) {
    const resourceKind = resourceEvidenceValue(item, 'kind') ?? item.category ?? item.title;
    const base: AssistantLaunchContext = {
      actionType: 'resource_summary_rca',
      evidenceRefs: item.evidence,
      kind: resourceKind,
      reason: item.detail || item.title,
      severity: item.severity,
      source,
      promptDraft: '',
    };
    return {
      ...base,
      promptDraft: buildResourceSummaryAssistantPrompt(item, resourceKind),
    };
  }

  const target = parseAssistantTarget(item.target, item.category);
  const base: AssistantLaunchContext = {
    ...target,
    actionType,
    evidenceRefs: item.evidence,
    reason: item.category ?? item.title,
    severity: item.severity,
    source,
    promptDraft: '',
  };
  return {
    ...base,
    promptDraft: buildAssistantPrompt(base),
  };
};


const endpointPageSizeOptions = [10, 25, 50];

const asObject = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' ? (value as Record<string, unknown>) : {};

const textValue = (value: unknown, fallback = '-'): string => {
  if (value === undefined || value === null || value === '') {
    return fallback;
  }

  if (typeof value === 'string') {
    return value;
  }

  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }

  return JSON.stringify(value);
};

const PUBLIC_WEB_URL_RE =
  /\bhttps?:\/\/(?:github\.com|docs\.openshift\.com|docs\.redhat\.com|access\.redhat\.com)\/[^\s)]+/gi;

const stripPublicWebUrls = (value: string): string =>
  value
    .replace(/\s*See also\s+https?:\/\/(?:github\.com|docs\.openshift\.com|docs\.redhat\.com|access\.redhat\.com)\/[^\s)]+/gi, '')
    .replace(PUBLIC_WEB_URL_RE, '')
    .replace(/\s{2,}/g, ' ')
    .trim();

const localizeTelemetryText = (value: string): string =>
  stripPublicWebUrls(value)
    .replace(/\blocal-aiops-fixture-ledger\b/gi, 'Gateway 검증 원장')
    .replace(/\brun-local-fixture\b/gi, 'Gateway 검증 실행')
    .replace(/\blocal-fixture\b/gi, 'Gateway 검증')
    .replace(/\bserved local-only AIOps fixture\b/gi, 'Gateway 검증 응답 기록')
    .replace(/\blocal-only AIOps fixture\b/gi, 'Gateway 검증 응답')
    .replace(/\blocal simulator state: ready ([0-9]+\/[0-9]+)/gi, '검증 워크로드 ready $1')
    .replace(/\bready ([0-9]+\/[0-9]+) in local simulator\b/gi, 'ready $1')
    .replace(/\bCrashLoopBackOff fixture for Action Plan testing\b/gi, 'Action Plan 검증용 CrashLoopBackOff')
    .replace(/\bopenshift-marketplace\/appscan360-catalog fixture is not ready\b/gi, 'openshift-marketplace/appscan360-catalog 준비 상태 확인 필요')
    .replace(/\blocal simulator\b/gi, '검증 환경')
    .replace(/\blocal fixture\b/gi, '검증 환경')
    .replace(/\bfixture\b/gi, '검증')
    .replace(/\bPod status\b/g, '파드 상태')
    .replace(/\bKubernetes Event\b/g, '쿠버네티스 이벤트')
    .replace(/\bReady replicas\b/g, '정상 레플리카')
    .replace(/\bRunning\b/g, '실행 중')
    .replace(/\bReady\b/g, '정상')
    .replace(/\bNotReady\b/g, '비정상')
    .replace(/\bPending\b/g, '대기')
    .replace(/\bFailed\b/g, '실패')
    .replace(/\bSucceeded\b/g, '성공')
    .replace(/\bRestarts\b/g, '재시작')
    .replace(/\bAvailable\b/g, '가용')
    .replace(/\bUpdated\b/g, '업데이트')
    .replace(/\bIssues\b/g, '이슈')
    .replace(/\bIssue\b/g, '이슈')
    .replace(/\bTotal\b/g, '전체')
    .replace(/\bCurrent\b/g, '현재')
    .replace(/\bDegraded\b/g, '저하')
    .replace(/\bProgressing\b/g, '진행 중')
    .replace(/\bUnavailable\b/g, '사용 불가')
    .replace(/\bUpdate available\b/g, '업데이트 가능')
    .replace(/\bphase=/g, '상태=')
    .replace(/\bready=/g, '준비=')
    .replace(/\brestart=/g, '재시작=')
    .replace(/\bcreated=/g, '생성=')
    .replace(/\blast=/g, '마지막=')
    .replace(/\brunning\b/g, '실행 중')
    .replace(/\bwaiting\b/g, '대기')
    .replace(/\bsucceeded\b/g, '성공')
    .replace(/\bsince\b/g, '이후')
    .replace(/\broles\b/g, '역할');

const sourceLabel = (value?: string): string => {
  const labels: Record<string, string> = {
    'AIOps Gateway': 'AIOps 게이트웨이',
    'Gateway cluster summary': '게이트웨이 클러스터 요약',
    'Kubernetes Event': '쿠버네티스 이벤트',
    'OpenShift ClusterOperator API': 'OpenShift ClusterOperator API',
    'OpenShift ClusterVersion API': 'OpenShift ClusterVersion API',
    'OpenShift Node API': 'OpenShift Node API',
  };
  return value ? labels[value] ?? value : '-';
};

const resourceNameLabel = (id: string, name: string, kind: string): string => {
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

const displayApiEndpoint = (apiUrl?: string): string => {
  if (!apiUrl) {
    return 'OpenShift 상태 확인 필요';
  }

  try {
    const host = new URL(apiUrl).hostname;
    if (/local-aiops\.invalid|\.invalid$/i.test(host)) {
      return 'Gateway 검증 환경';
    }
    return host;
  } catch {
    return /local-aiops|\.invalid/i.test(apiUrl) ? 'Gateway 검증 환경' : apiUrl;
  }
};

const displayOpenShiftVersion = (version?: string): string => {
  if (!version) {
    return '-';
  }
  return version.replace(/-local\b/i, '');
};

const displayNamespaceLabel = (namespace?: string): string => {
  if (!namespace) {
    return '-';
  }
  if (/^komsco-ai-local$/i.test(namespace)) {
    return '검증 네임스페이스';
  }
  return localizeTelemetryText(namespace);
};

const clusterLabel = (summary: ClusterSummary): string => {
  if (!summary.apiUrl) {
    return '게이트웨이 연결 대기';
  }
  return displayApiEndpoint(summary.apiUrl);
};

const resourceKeywords: Record<string, string[]> = {
  daemonsets: ['데몬셋', 'daemonset'],
  deployments: ['디플로이', '디플로이먼트', '배포', 'deployment'],
  namespaces: ['네임스페이스', 'namespace', '프로젝트'],
  persistentvolumeclaims: ['pvc', '볼륨', '스토리지', 'persistentvolumeclaim'],
  pods: ['파드', 'pod'],
  replicasets: ['레플리카셋', 'replicaset'],
  routes: ['라우트', 'route'],
  services: ['서비스', 'service'],
  statefulsets: ['스테이트풀셋', 'statefulset'],
};

const pressureLabels = (pressures: ClusterSummary['nodes']['items'][number]['pressures']): string[] => {
  const labels = [];
  if (pressures.disk) {
    labels.push('디스크 압박');
  }
  if (pressures.memory) {
    labels.push('메모리 압박');
  }
  if (pressures.pid) {
    labels.push('PID 압박');
  }
  return labels;
};

const nodeSeverity = (node: ClusterSummary['nodes']['items'][number]): Severity => {
  if (!node.ready) {
    return 'risk';
  }

  return pressureLabels(node.pressures).length > 0 ? 'warn' : 'ok';
};

const operatorSeverity = (operator: ClusterSummary['operators']['issues'][number]): Severity => {
  if (!operator.available || operator.degraded) {
    return 'risk';
  }

  return operator.progressing ? 'warn' : 'ok';
};

const formatCpu = (value?: string): string => {
  if (!value) {
    return '-';
  }

  if (value.endsWith('n')) {
    const cores = Number(value.slice(0, -1)) / 1_000_000_000;
    return Number.isFinite(cores) ? `${cores.toFixed(2)} cores` : value;
  }

  if (value.endsWith('m')) {
    const cores = Number(value.slice(0, -1)) / 1000;
    return Number.isFinite(cores) ? `${cores.toFixed(2)} cores` : value;
  }

  return value;
};

const formatMemory = (value?: string): string => {
  if (!value) {
    return '-';
  }

  if (value.endsWith('Ki')) {
    const gib = Number(value.slice(0, -2)) / 1024 / 1024;
    return Number.isFinite(gib) ? `${gib.toFixed(1)} GiB` : value;
  }

  return value;
};

const aiopsWorkloadItems = (summary: ClusterSummary) => [
  ...(summary.aiopsWorkloads?.deployments ?? []),
  ...(summary.aiopsWorkloads?.daemonsets ?? []),
];

const aiopsWorkloadNames = (summary: ClusterSummary, limit = 3): string => {
  const workloads = aiopsWorkloadItems(summary);
  const names = workloads.slice(0, limit).map((workload) => `${workload.namespace}/${workload.name}`);
  const extra = workloads.length - names.length;
  return extra > 0 ? `${names.join(', ')} 외 ${extra}` : names.join(', ');
};

const buildScopes = (summary: ClusterSummary, status: AiopsRuntimeStatus): ScopeItem[] => {
  const records = actionRecords(status);
  const auditCount = status.spec.records.auditRecords?.length ?? 0;
  const resources = summary.resources?.items ?? [];
  const operatorSeverityValue: Severity =
    summary.operators.degraded > 0 || summary.operators.unavailable > 0
      ? 'risk'
      : summary.operators.progressing > 0
        ? 'warn'
        : 'ok';

  return [
    {
      id: 'cluster',
      keywords: ['클러스터', 'api', 'ocp', 'openshift'],
      name: clusterLabel(summary),
      detail: `OCP ${displayOpenShiftVersion(summary.version.version)} · API ${displayApiEndpoint(summary.apiUrl)}`,
      score: `${summary.healthScore}%`,
      severity: summary.healthScore >= 90 ? 'ok' : summary.healthScore >= 70 ? 'warn' : 'risk',
    },
    {
      id: 'nodes',
      keywords: ['노드', 'node'],
      name: '노드',
      detail: `정상 ${summary.nodes.ready} · 비정상 ${summary.nodes.notReady} · 압박 ${summary.nodes.pressureCount}`,
      score: `${summary.nodes.ready}/${summary.nodes.total}`,
      severity: summary.nodes.notReady > 0 ? 'risk' : summary.nodes.pressureCount > 0 ? 'warn' : 'ok',
    },
    ...resources.map(
      (resource): ScopeItem => ({
        detail: localizeTelemetryText(resource.detail),
        detailRows: [
          { label: '종류', value: ledgerKindLabel(resource.kind) },
          { label: '전체', value: String(resource.total) },
          { label: '정상', value: String(resource.ready) },
          { label: '이슈', value: String(resource.issues) },
        ],
        id: `resource-${resource.id}`,
        keywords: resourceKeywords[resource.id] ?? [],
        name: resourceNameLabel(resource.id, resource.name, resource.kind),
        score: resource.score,
        severity: resource.severity,
      }),
    ),
    {
      id: 'operators',
      keywords: ['오퍼레이터', 'operator'],
      name: '클러스터 오퍼레이터',
      detail: `정상 ${summary.operators.available} · 저하 ${summary.operators.degraded} · 진행 중 ${summary.operators.progressing}`,
      score: `${summary.operators.available}/${summary.operators.total}`,
      severity: operatorSeverityValue,
    },
    {
      id: 'records',
      keywords: ['aiops', '기록', '감사', '액션'],
      name: 'AIOps 기록',
      detail: `감사 ${auditCount} · 조치 ${records.length}`,
      score: String(auditCount + records.length),
      severity: records.length > 0 ? 'warn' : 'ok',
    },
  ];
};

const scopeDetailRows = (
  scope: ScopeItem,
  summary: ClusterSummary,
  status: AiopsRuntimeStatus,
): Array<{ label: string; value: string }> => {
  const records = actionRecords(status);
  const auditCount = status.spec.records.auditRecords?.length ?? 0;

  if (scope.detailRows) {
    return scope.detailRows;
  }

  if (scope.id === 'nodes') {
    return [
      { label: '정상', value: `${summary.nodes.ready}/${summary.nodes.total}` },
      { label: '비정상', value: String(summary.nodes.notReady) },
      { label: '압박', value: String(summary.nodes.pressureCount) },
      { label: '메트릭', value: summary.nodes.metricsAvailable ? '수집 가능' : '수집 불가' },
    ];
  }

  if (scope.id === 'operators') {
    return [
      { label: '정상', value: `${summary.operators.available}/${summary.operators.total}` },
      { label: '저하', value: String(summary.operators.degraded) },
      { label: '진행 중', value: String(summary.operators.progressing) },
      { label: '사용 불가', value: String(summary.operators.unavailable) },
    ];
  }

  if (scope.id === 'records') {
    return [
      { label: '감사', value: String(auditCount) },
      { label: '조치', value: String(records.length) },
      { label: '진단', value: String(status.spec.records.diagnosticRequests.length) },
      { label: '실행기', value: status.spec.capabilities.actionExecutorConfigured ? '설정됨' : '미설정' },
    ];
  }

  return [
    { label: '건강도', value: `${summary.healthScore}%` },
    { label: 'API', value: displayApiEndpoint(summary.apiUrl) },
    { label: 'OpenShift', value: displayOpenShiftVersion(summary.version.version) },
    { label: '업데이트', value: formatTime(summary.updatedAt) },
  ];
};

const buildQueues = (summary: ClusterSummary, status: AiopsRuntimeStatus): QueueItem[] => {
  const nodeQueues = summary.nodes.items
    .filter((node) => nodeSeverity(node) !== 'ok')
    .map((node): QueueItem => {
      const pressures = pressureLabels(node.pressures);
      const severity: QueueItem['severity'] = !node.ready ? 'risk' : 'warn';
      const detail = [
        `역할 ${node.roles.join(', ') || '-'}`,
        node.ready ? '정상' : '비정상',
        pressures.length ? pressures.join(', ') : '',
      ]
        .filter(Boolean)
        .join(' · ');

      return {
        id: `node-${node.name}`,
        title: node.name,
        category: '노드',
        detail,
        evidence: [
          `kubelet ${node.kubeletVersion ?? '-'}`,
          `cpu ${formatCpu(node.usage.cpu)} · memory ${formatMemory(node.usage.memory)}`,
          `os ${localizeTelemetryText(node.osImage ?? '-')}`,
        ],
        source: 'OpenShift Node API',
        target: node.name,
        updatedAt: formatTime(summary.updatedAt),
        severity,
      };
    });

  const operatorQueues = summary.operators.issues.map((operator): QueueItem => {
    const severity = operatorSeverity(operator) === 'risk' ? 'risk' : 'warn';
    return {
      id: `operator-${operator.name}`,
      title: operator.name,
      category: '오퍼레이터',
      detail: localizeTelemetryText(operator.reason ?? operator.message ?? 'ClusterOperator 이슈'),
      evidence: [
        `available ${operator.available}`,
        `degraded ${operator.degraded}`,
        `progressing ${operator.progressing}`,
        operator.message ?? '',
      ].filter(Boolean),
      source: 'OpenShift ClusterOperator API',
      target: operator.name,
      updatedAt: formatTime(summary.updatedAt),
      severity,
    };
  });

  const versionQueue: QueueItem[] =
    summary.version.updateAvailable && summary.version.upgradeable === false
      ? [
          {
            id: 'version-upgrade-blocked',
            title: 'OCP 업데이트 사전 확인 필요',
            category: '클러스터 버전',
            detail: [
              `현재 ${displayOpenShiftVersion(summary.version.version)}`,
              summary.version.availableUpdates?.length
                ? `추천 업데이트 ${summary.version.availableUpdates.join(', ')}`
                : '추천 업데이트 확인됨',
              summary.version.upgradeableReason ?? 'Upgradeable=False',
            ].join(' · '),
            evidence: [
              `current ${displayOpenShiftVersion(summary.version.version)}`,
              `recommended updates ${summary.version.availableUpdates?.join(', ') || '-'}`,
              `conditional updates ${summary.version.conditionalUpdates?.join(', ') || '-'}`,
              `reason ${summary.version.upgradeableReason ?? 'Upgradeable=False'}`,
              summary.version.upgradeableMessage ?? 'ClusterVersion가 updateAvailable=true를 보고했습니다.',
            ],
            source: 'OpenShift ClusterVersion API',
            target: `OpenShift ${displayOpenShiftVersion(summary.version.version)}`,
            updatedAt: formatTime(summary.updatedAt),
            severity: 'warn',
          },
        ]
      : [];

  const pendingActionQueues = actionRecords(status)
    .filter((record) => {
      const phase = recordPhase(record).toLowerCase();
      return phase.includes('approval') || phase.includes('pending') || phase.includes('failed');
    })
    .map((record): QueueItem => {
      const phase = recordPhase(record);
      const severity: QueueItem['severity'] = phase.toLowerCase().includes('failed') ? 'risk' : 'warn';
      return {
        id: `record-${record.metadata?.name ?? record.kind ?? phase}`,
        title: record.metadata?.name ?? recordKindLabel(record.kind),
        category: 'AIOps 기록',
        detail: `${recordKindLabel(record.kind)} · ${ledgerResultLabel(phase)} · ${recordTarget(record)}`,
        evidence: [`created ${formatTime(record.metadata?.createdAt)}`, `target ${recordTarget(record)}`],
        source: recordKindLabel(record.kind),
        target: recordTarget(record),
        updatedAt: formatTime(record.metadata?.createdAt),
        severity,
      };
    });

  const resourceQueues = (summary.resources?.items ?? [])
    .filter((resource) => resource.issues > 0)
    .map((resource): QueueItem => {
      const severity: QueueItem['severity'] = resource.severity === 'risk' ? 'risk' : 'warn';
      return {
        id: `resource-${resource.id}`,
        title: `${resourceNameLabel(resource.id, resource.name, resource.kind)} 확인 필요`,
        category: '리소스',
        detail: localizeTelemetryText(resource.detail),
        evidence: [
          `kind ${resource.kind}`,
          `total ${resource.total}`,
          `ready ${resource.ready}`,
          `issues ${resource.issues}`,
        ],
        source: '게이트웨이 클러스터 요약',
        target: resourceNameLabel(resource.id, resource.name, resource.kind),
        updatedAt: formatTime(summary.updatedAt),
        severity,
      };
    });

  return [...resourceQueues, ...nodeQueues, ...operatorQueues, ...versionQueue, ...pendingActionQueues];
};

const buildAlerts = (summary: ClusterSummary, status: AiopsRuntimeStatus): AlertItem[] =>
  buildQueues(summary, status).map((item) => ({
    id: `alert-${item.id}`,
    title: item.title,
    target: localizeTelemetryText(item.detail),
    severity: item.severity,
    time: formatTime(summary.updatedAt),
  }));

const buildEndpoints = (summary: ClusterSummary): Endpoint[] => {
  const nodeEndpoints = summary.nodes.items.map((node): Endpoint => ({
    id: `node-${node.name}`,
    name: node.name,
    type: '노드',
    group: node.roles.join(', ') || '-',
    severity: nodeSeverity(node),
    cpu: formatCpu(node.usage.cpu),
    memory: formatMemory(node.usage.memory),
    latency: '-',
    lastEvent: formatTime(summary.updatedAt),
    path: `${localizeTelemetryText(node.osImage ?? '-')} / ${displayOpenShiftVersion(node.kubeletVersion ?? '-')}`,
  }));

  const operatorEndpoints = summary.operators.issues.map((operator): Endpoint => ({
    id: `operator-${operator.name}`,
    name: operator.name,
    type: '클러스터 오퍼레이터',
    group: operator.reason ?? '-',
    severity: operatorSeverity(operator),
    cpu: '-',
    memory: '-',
    latency: '-',
    lastEvent: formatTime(summary.updatedAt),
    path: localizeTelemetryText(operator.message ?? 'ClusterOperator 이슈'),
  }));

  const versionEndpoint: Endpoint[] = summary.version.version
    ? [
        {
          id: 'clusterversion-version',
          name: `OpenShift ${displayOpenShiftVersion(summary.version.version)}`,
          type: 'ClusterVersion',
          group: summary.version.channel ?? '-',
          severity: summary.version.upgradeable === false ? 'warn' : 'ok',
          cpu: '-',
          memory: '-',
          latency: '-',
          lastEvent: formatTime(summary.updatedAt),
          path: summary.version.upgradeableReason ?? (summary.version.updateAvailable ? '업데이트 가능' : '현재 버전'),
        },
      ]
    : [];

  const aiopsWorkloadEndpoints = aiopsWorkloadItems(summary).map((workload): Endpoint => ({
    id: `aiops-${workload.kind}-${workload.namespace}-${workload.name}`,
    name: workload.name,
    type: `AI/Ops ${ledgerKindLabel(workload.kind)}`,
    group: workload.namespace,
    severity: workload.severity,
    cpu: '-',
    memory: '-',
    latency: `정상 ${workload.ready}/${workload.desired}`,
    lastEvent: formatTime(workload.createdAt ?? summary.updatedAt),
    path: localizeTelemetryText(workload.detail),
  }));

  const resourceEndpoints = (summary.resources?.items ?? []).map((resource): Endpoint => ({
    id: `resource-${resource.id}`,
    name: resourceNameLabel(resource.id, resource.name, resource.kind),
    type: ledgerKindLabel(resource.kind),
    group: `전체 ${resource.total}`,
    severity: resource.severity,
    cpu: '-',
    memory: '-',
    latency: `이슈 ${resource.issues}건`,
    lastEvent: formatTime(summary.updatedAt),
    path: localizeTelemetryText(resource.detail),
  }));

  return [
    ...aiopsWorkloadEndpoints,
    ...resourceEndpoints,
    ...nodeEndpoints,
    ...operatorEndpoints,
    ...versionEndpoint,
  ];
};

const eventTone = (event: AiopsEventItem): ActivityItem['tone'] => {
  if (event.severity === 'risk') {
    return 'red';
  }
  if (event.severity === 'warn') {
    return 'orange';
  }
  if (event.source === 'AIOps Gateway') {
    return 'blue';
  }
  return 'green';
};

const eventActivityDetail = (event: AiopsEventItem): string =>
  [
    localizeTelemetryText(event.detail),
    sourceLabel(event.source),
    event.namespace ? `네임스페이스=${displayNamespaceLabel(event.namespace)}` : '',
  ]
    .filter(Boolean)
    .join(' · ');

const buildActivities = (
  summary: ClusterSummary,
  status: AiopsRuntimeStatus,
  eventFeed: AiopsEventFeed,
): ActivityItem[] => {
  const eventActivities = eventFeed.spec.items.map((event): ActivityItem => ({
    category: event.category,
    detail: eventActivityDetail(event),
    id: event.id,
    source: sourceLabel(event.source),
    target: event.target,
    time: event.time,
    title: event.title,
    tone: eventTone(event),
  }));

  if (eventActivities.length > 0) {
    return eventActivities.slice(0, 20);
  }

  const audits = (status.spec.records.auditRecords ?? []).map((record): ActivityItem => ({
    id: `audit-${record.metadata?.name ?? record.metadata?.createdAt}`,
    title: ledgerActionLabel(textValue(asObject(record.spec).action, 'audit_record')),
    detail: `${recordKindLabel(record.kind)} · ${formatTime(record.metadata?.createdAt)}`,
    tone: 'blue',
  }));

  const actions = actionRecords(status).map((record): ActivityItem => ({
    id: `action-${record.kind ?? 'record'}-${record.metadata?.name ?? record.metadata?.createdAt}`,
    title: record.metadata?.name ?? recordKindLabel(record.kind),
    detail: `${ledgerResultLabel(recordPhase(record))} · ${recordTarget(record)}`,
    tone: recordPhase(record).toLowerCase().includes('failed') ? 'red' : 'green',
  }));

  const aiopsWorkloads = summary.aiopsWorkloads;
  const signals: ActivityItem[] = [];

  if (summary.updatedAt) {
    signals.push({
      id: 'signal-summary-refresh',
      title: '클러스터 요약 수집',
      detail: `${clusterLabel(summary)} · ${formatTime(summary.updatedAt)}`,
      tone: 'blue',
    });
  }

  if (aiopsWorkloads && aiopsWorkloads.total > 0) {
    signals.push({
      id: 'signal-aiops-workloads-detected',
      title: 'AI/Ops 워크로드 감지',
      detail: [
        `디플로이먼트 ${aiopsWorkloads.deployments.length}`,
        `데몬셋 ${aiopsWorkloads.daemonsets.length}`,
        `이슈 ${aiopsWorkloads.issues}`,
        aiopsWorkloadNames(summary),
      ]
        .filter(Boolean)
        .join(' · '),
      tone: aiopsWorkloads.issues > 0 ? 'orange' : 'green',
    });
  }

  if (summary.version.upgradeable === false) {
    signals.push({
      id: 'signal-version-upgrade-blocked',
      title: 'ClusterVersion Upgradeable=False',
      detail: `${displayOpenShiftVersion(summary.version.version)} · ${summary.version.upgradeableReason ?? '사전 확인 필요'}`,
      tone: 'orange',
    });
  }

  const resourceSignals = (summary.resources?.items ?? [])
    .filter((resource) => resource.issues > 0)
    .slice(0, 4)
    .map((resource): ActivityItem => ({
      id: `signal-resource-${resource.id}`,
      title: `${resourceNameLabel(resource.id, resource.name, resource.kind)} 이슈 감지`,
      detail: localizeTelemetryText(resource.detail),
      tone: resource.severity === 'risk' ? 'red' : 'orange',
    }));

  return [...signals, ...audits, ...actions, ...resourceSignals].slice(0, 10);
};

const buildAlertEventRows = (
  summary: ClusterSummary,
  status: AiopsRuntimeStatus,
  eventFeed: AiopsEventFeed,
): AlertEventRow[] => {
  const eventRows = eventFeed.spec.items.map((event): AlertEventRow => ({
    category: event.category || '게이트웨이',
    detail: localizeTelemetryText(event.detail),
    id: `event-${event.id}`,
    namespace: event.namespace ?? '-',
    sample: false,
    severity: event.severity,
    source: sourceLabel(event.source),
    target: event.target ?? '-',
    time: formatTime(event.time),
    title: event.title,
  }));
  const alertRows = buildAlerts(summary, status).map((alert): AlertEventRow => ({
    category: '클러스터 알림',
    detail: alert.target,
    id: `alert-row-${alert.id}`,
    namespace: '-',
    sample: false,
    severity: alert.severity,
    source: '게이트웨이 요약',
    target: alert.target,
    time: alert.time,
    title: alert.title,
  }));
  const rows = [...eventRows, ...alertRows];
  return rows.length > 0 ? rows : sampleAlertEvents;
};

const eventAssistantContext = (
  group: EventInboxGroup,
  source: AssistantLaunchContext['source'],
): AssistantLaunchContext => {
  const base: AssistantLaunchContext = {
    ...parseAssistantTarget(
      [group.namespace, group.target].filter((value) => value && value !== '-').join('/'),
      group.kind,
    ),
    actionType: 'event-rca',
    evidenceRefs: [
      group.detail,
      `${group.rows.length} events`,
      group.relatedIssue?.title ?? '',
    ].filter(Boolean),
    reason: group.reason,
    severity: group.severity,
    source,
    promptDraft: '',
  };
  return {
    ...base,
    promptDraft: buildAssistantPrompt(base),
  };
};


type TopologyNodeKey =
  | 'daemonsets'
  | 'deployments'
  | 'nodes'
  | 'persistentvolumeclaims'
  | 'pods'
  | 'replicasets'
  | 'routes'
  | 'services'
  | 'statefulsets';

type TopologyEdgeMode = 'all' | 'ownership' | 'runtime' | 'traffic';

type TraceInspectorModel = {
  commands: Array<{ command: string; title: string }>;
  focus: string;
  insight: string;
  reasons: Array<{ detail: string; label: string }>;
  severity: Severity;
  signals: Array<{ label: string; tone?: Severity; value: string }>;
  title: string;
  trace: string;
};


const EmptyState: React.FC<{ label: string }> = ({ label }) => (
  <div className="empty-state">{label}</div>
);

const resourceNodeDetail = (
  resource: NonNullable<ClusterSummary['resources']>['items'][number] | undefined,
  fallback: string,
): string => (resource ? `${resource.score} · ${resource.issues > 0 ? `이슈 ${resource.issues}건` : '정상'}` : fallback);

const resourceNodeSeverity = (
  resource: NonNullable<ClusterSummary['resources']>['items'][number] | undefined,
  fallback: Severity = 'ok',
): Severity => resource?.severity ?? fallback;

const topologyNodeLabel: Record<TopologyNodeKey, string> = {
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

const topologyPrimarySignals = (summary: ClusterSummary): number =>
  resourceById(summary, 'pods')?.issues ?? 0;

const topologyDerivedSignals = (summary: ClusterSummary): number =>
  (resourceById(summary, 'deployments')?.issues ?? 0) + (resourceById(summary, 'replicasets')?.issues ?? 0);

const topologyOtherSignals = (summary: ClusterSummary): number =>
  Math.max(0, (summary.resources?.issues ?? 0) - topologyPrimarySignals(summary) - topologyDerivedSignals(summary));

const topologyNodeSummary = (
  summary: ClusterSummary,
  key: TopologyNodeKey,
): { detail: string; score: string; severity: Severity; title: string } => {
  if (key === 'nodes') {
    return {
      detail: summary.nodes.total === 1
        ? `정상 ${summary.nodes.ready}/${summary.nodes.total} · 단일 노드 런타임`
        : `정상 ${summary.nodes.ready}/${summary.nodes.total} · 비정상 ${summary.nodes.notReady}`,
      score: `${summary.nodes.ready}/${summary.nodes.total}`,
      severity: summary.nodes.notReady > 0 ? 'risk' : summary.nodes.pressureCount > 0 ? 'warn' : 'ok',
      title: '노드',
    };
  }

  const resource = resourceById(summary, key);
  return {
    detail: resourceNodeDetail(resource, `${topologyNodeLabel[key]} 스냅샷 없음`),
    score: resource?.score ?? '-',
    severity: resourceNodeSeverity(resource),
    title: resource ? resourceNameLabel(resource.id, resource.name, resource.kind) : topologyNodeLabel[key],
  };
};

const topologyTracePath = (key: TopologyNodeKey): string => {
  const paths: Record<TopologyNodeKey, string> = {
    daemonsets: 'DaemonSet -> Pods',
    deployments: 'Deployment -> ReplicaSet -> Pods',
    nodes: 'Pods -> Nodes',
    persistentvolumeclaims: 'Pods -> PVC',
    pods: 'Route -> Service -> Pods',
    replicasets: 'Deployment -> ReplicaSet -> Pods',
    routes: 'Route -> Service',
    services: 'Route -> Service -> Pods',
    statefulsets: 'StatefulSet -> Pods',
  };
  return paths[key];
};

const buildTraceInspector = (summary: ClusterSummary, key: TopologyNodeKey): TraceInspectorModel => {
  const resource = resourceById(summary, key);
  const podSummary = buildPodRcaSummary(summary);
  const nodeSummary = topologyNodeSummary(summary, key);

  if (key === 'pods') {
    return {
      commands: [
        { title: '파드 인벤토리', command: 'oc get pods -A -o wide' },
        { title: '최근 파드 이벤트', command: 'oc get events -A --field-selector involvedObject.kind=Pod --sort-by=.lastTimestamp' },
        { title: '파드 상세', command: 'oc describe pod -n <namespace> <pod>' },
      ],
      focus: 'Pods · 런타임 수렴 지점',
      insight: '서비스 선택자와 컨트롤러 소유 관계가 Pod로 모입니다. 영향 후보는 활성 Pod 기준으로 계산합니다.',
      reasons: [
        { label: '서비스 선택 대상', detail: 'Service가 선택하는 실제 런타임 대상' },
        { label: '컨트롤러 소유 대상', detail: 'Deployment / ReplicaSet / StatefulSet / DaemonSet의 ownerRef 종착점' },
        { label: '런타임 의존성 대상', detail: 'Node와 PVC 상태가 직접 영향을 주는 대상' },
        { label: '헬스 신호 원천', detail: '대기 / 실패 / 미준비 / 재시작이 관측되는 지점' },
      ],
      severity: nodeSummary.severity,
      signals: [
        { label: '영향 후보', tone: nodeSummary.severity, value: String(podSummary.issueCandidates) },
        { label: '활성 Ready', value: String(podSummary.ready) },
        { label: '전체 Pod', value: String(podSummary.total) },
        { label: '실패', tone: podSummary.failed > 0 ? 'risk' : 'ok', value: String(podSummary.failed) },
        { label: '재시작', tone: podSummary.restartsTotal > 0 ? 'warn' : 'ok', value: String(podSummary.restartsTotal) },
        { label: '완료 제외', value: String(podSummary.completed) },
      ],
      title: '파드',
      trace: topologyTracePath(key),
    };
  }

  if (key === 'nodes') {
    return {
      commands: [
        { title: '노드 목록', command: 'oc get nodes -o wide' },
        { title: '노드 상태', command: 'oc describe node <node>' },
      ],
      focus: `Nodes · ${summary.nodes.total === 1 ? '단일 노드 런타임' : '스케줄링 기반'}`,
      insight: summary.nodes.total === 1
        ? '단일 노드에서는 Pod 장애가 노드 중복성 부족과 함께 해석됩니다.'
        : 'Pod가 스케줄링되는 기반입니다. 비정상 노드와 압박 신호를 먼저 배제합니다.',
      reasons: [
        { label: '스케줄링 대상', detail: 'Pod가 실제로 실행되는 노드 기반' },
        { label: '런타임 압박', detail: 'Disk / Memory / PID pressure가 Pod 준비 상태에 영향' },
        { label: '배제 근거', detail: 'Ready 상태와 pressure 신호가 정상이면 Pod 원인에서 분리' },
      ],
      severity: nodeSummary.severity,
      signals: [
        { label: 'Ready', tone: nodeSummary.severity, value: `${summary.nodes.ready}/${summary.nodes.total}` },
        { label: '비정상', tone: summary.nodes.notReady > 0 ? 'risk' : 'ok', value: String(summary.nodes.notReady) },
        { label: 'Pressure', tone: summary.nodes.pressureCount > 0 ? 'warn' : 'ok', value: String(summary.nodes.pressureCount) },
        { label: 'Metrics', value: summary.nodes.metricsAvailable ? '수집됨' : '미수집' },
      ],
      title: '노드',
      trace: topologyTracePath(key),
    };
  }

  if (key === 'persistentvolumeclaims') {
    return {
      commands: [
        { title: 'PVC 목록', command: 'oc get pvc -A' },
        { title: 'PVC 상세', command: 'oc describe pvc -n <namespace> <pvc>' },
      ],
      focus: 'PVC · 스토리지 의존성',
      insight: resource?.issues
        ? 'PVC 신호가 있어 Pod 마운트와 이벤트를 같이 확인해야 합니다.'
        : 'PVC는 현재 Bound 상태로 보이며, Pod 원인에서 우선 배제할 수 있습니다.',
      reasons: [
        { label: '볼륨 마운트 대상', detail: 'Pod 실행에 필요한 스토리지 연결 지점' },
        { label: '스토리지 배제', detail: 'Bound와 mount 이벤트 이상 여부로 영향 여부 판단' },
        { label: '집계 한계', detail: '현재 화면은 개별 Pod-PVC 매핑까지는 분리하지 않음' },
      ],
      severity: nodeSummary.severity,
      signals: [
        { label: 'Bound', tone: nodeSummary.severity, value: resource?.score ?? '-' },
        { label: '전체 PVC', value: String(resource?.total ?? '-') },
        { label: '이슈', tone: resource?.issues ? 'warn' : 'ok', value: String(resource?.issues ?? 0) },
      ],
      title: 'PVC',
      trace: topologyTracePath(key),
    };
  }

  const relationNote: Record<TopologyNodeKey, string> = {
    daemonsets: 'DaemonSet은 노드 단위 파드를 소유하며 파드 런타임 신호로 파생될 수 있습니다.',
    deployments: 'Deployment 가용성 변화는 ReplicaSet과 파드 준비 상태에서 파생될 수 있습니다.',
    nodes: '',
    persistentvolumeclaims: '',
    pods: '',
    replicasets: 'ReplicaSet은 Deployment와 Pod 사이의 소유 관계를 구성합니다.',
    routes: 'Route 리소스는 Service 대상을 외부/내부 트래픽 진입점으로 노출합니다.',
    services: 'Service는 셀렉터/엔드포인트 관계로 Pod 집합을 선택합니다.',
    statefulsets: 'StatefulSet은 안정적인 identity와 볼륨을 가진 파드를 소유합니다.',
  };

  const focusLabel: Record<TopologyNodeKey, string> = {
    daemonsets: 'DaemonSet · 노드 단위 소유자',
    deployments: 'Deployment · 워크로드 선언',
    nodes: '',
    persistentvolumeclaims: '',
    pods: '',
    replicasets: 'ReplicaSet · Pod 소유 체인',
    routes: 'Route · 트래픽 진입점',
    services: 'Service · 셀렉터 경계',
    statefulsets: 'StatefulSet · 안정 identity 소유자',
  };

  const commandByNode: Record<TopologyNodeKey, Array<{ command: string; title: string }>> = {
    daemonsets: [{ title: '데몬셋', command: 'oc get ds -A' }],
    deployments: [{ title: '디플로이먼트', command: 'oc get deploy -A' }],
    nodes: [],
    persistentvolumeclaims: [],
    pods: [],
    replicasets: [{ title: '레플리카셋', command: 'oc get rs -A' }],
    routes: [{ title: '라우트', command: 'oc get routes -A' }],
    services: [
      { title: '서비스', command: 'oc get svc -A' },
      { title: 'EndpointSlice', command: 'oc get endpointslice -A' },
    ],
    statefulsets: [{ title: '스테이트풀셋', command: 'oc get sts -A' }],
  };

  return {
    commands: commandByNode[key],
    focus: focusLabel[key],
    insight: relationNote[key] || '선택한 리소스의 상태와 관계를 기준으로 영향 경로를 확인합니다.',
    reasons: [
      { label: key === 'routes' ? '노출 경계' : key === 'services' ? '셀렉터 경계' : '소유 관계', detail: relationNote[key] || '리소스 관계 확인 대상' },
      { label: '현재 상태', detail: resource?.detail ? localizeTelemetryText(resource.detail) : '스냅샷 없음' },
      { label: resource?.issues ? '영향 신호' : '배제 근거', detail: resource?.issues ? `이슈 ${resource.issues}건이 감지됨` : '현재 활성 이슈 없음' },
    ],
    severity: nodeSummary.severity,
    signals: [
      { label: '상태', tone: nodeSummary.severity, value: nodeSummary.score },
      { label: '전체', value: String(resource?.total ?? '-') },
      { label: '이슈', tone: resource?.issues ? nodeSummary.severity : 'ok', value: String(resource?.issues ?? 0) },
    ],
    title: topologyNodeLabel[key],
    trace: topologyTracePath(key),
  };
};

type ResourceSummaryItem = NonNullable<ClusterSummary['resources']>['items'][number];

type ImpactSignalRow = {
  actionLabel?: string;
  chips: string[];
  description: string;
  detail: string;
  id: string;
  metric: string;
  node: TopologyNodeKey;
  severity: Severity;
  title: string;
};

type ImpactSignalSection = {
  id: 'primary' | 'derived' | 'cleared';
  label: string;
  rows: ImpactSignalRow[];
};

const resourceReadyText = (resource: ResourceSummaryItem | undefined): string =>
  resource ? String(resource.ready) : '-';

const buildDerivedImpactRow = (resource: ResourceSummaryItem): ImpactSignalRow => {
  const isReplicaSet = /replicaset/i.test(resource.id);
  const node: TopologyNodeKey = isReplicaSet
    ? 'replicasets'
    : /statefulset/i.test(resource.id)
      ? 'statefulsets'
      : /daemonset/i.test(resource.id)
        ? 'daemonsets'
        : 'deployments';
  const driftLabel = isReplicaSet ? '준비 차이' : '가용 차이';
  const sourceLabel = isReplicaSet ? 'ownerRef 체인에서 파생' : 'Pod 준비 상태 신호에서 파생';

  return {
    actionLabel: '관련 경로 보기',
    chips: [
      `${driftLabel} ${resource.issues}`,
      `목표 ${resource.total}`,
      `${isReplicaSet ? '준비' : '가용'} ${resourceReadyText(resource)}`,
      isReplicaSet ? '소유관계' : '파생',
    ],
    description: sourceLabel,
    detail: localizeTelemetryText(resource.detail),
    id: resource.id,
    metric: `${driftLabel} ${resource.issues}건`,
    node,
    severity: resource.severity,
    title: resourceNameLabel(resource.id, resource.name, resource.kind),
  };
};

const buildImpactSignalStack = (summary: ClusterSummary): ImpactSignalSection[] => {
  const podResource = resourceById(summary, 'pods');
  const podSummary = buildPodRcaSummary(summary);
  const pvcResource = resourceById(summary, 'persistentvolumeclaims');
  const derivedRows = (summary.resources?.items ?? [])
    .filter((resource) => ['deployments', 'replicasets', 'statefulsets', 'daemonsets'].includes(resource.id) && resource.issues > 0)
    .map(buildDerivedImpactRow);

  const sections: ImpactSignalSection[] = [
    {
      id: 'primary',
      label: '주 신호',
      rows: [
        {
          actionLabel: 'RCA 열기',
          chips: [
            `대기 ${podSummary.pending}`,
            `실패 ${podSummary.failed}`,
            `미준비 ${podSummary.runningNotReady}`,
            `재시작 ${podSummary.restartsTotal}`,
          ],
          description: '서비스 선택자와 컨트롤러 ownerRef가 수렴하는 런타임 지점',
          detail: '경로: Route -> Service -> Pods <- ReplicaSet / StatefulSet / DaemonSet',
          id: 'primary-pods',
          metric: `영향 후보 ${podSummary.issueCandidates}건`,
          node: 'pods',
          severity: podResource?.severity ?? (podSummary.issueCandidates > 0 ? 'risk' : 'ok'),
          title: '파드',
        },
      ],
    },
    {
      id: 'derived',
      label: '파생 영향',
      rows: derivedRows,
    },
    {
      id: 'cleared',
      label: '배제된 의존성',
      rows: [
        {
          chips: [
            `Ready ${summary.nodes.ready}/${summary.nodes.total}`,
            `압박 ${summary.nodes.pressureCount}`,
            summary.nodes.metricsAvailable ? '메트릭 수집' : '메트릭 미수집',
          ],
          description: summary.nodes.pressureCount > 0 ? '노드 압박 신호 확인 필요' : '노드 압박 신호 없음',
          detail: summary.nodes.total === 1 ? '단일 노드 런타임 · 영향 해석 시 중복성 제한 고려' : '스케줄링 기반 확인 완료',
          id: 'cleared-nodes',
          metric: `Ready ${summary.nodes.ready}/${summary.nodes.total}`,
          node: 'nodes',
          severity: summary.nodes.notReady > 0 ? 'risk' : summary.nodes.pressureCount > 0 ? 'warn' : 'ok',
          title: '노드',
        },
        {
          chips: [
            `Bound ${pvcResource?.score ?? '-'}`,
            `PVC ${pvcResource?.total ?? '-'}`,
            pvcResource?.issues ? `이슈 ${pvcResource.issues}` : '스토리지 신호 없음',
          ],
          description: pvcResource?.issues ? 'PVC 마운트/스토리지 신호 확인 필요' : '마운트/스토리지 신호 없음',
          detail: pvcResource?.detail ? localizeTelemetryText(pvcResource.detail) : 'PVC 스냅샷 없음',
          id: 'cleared-pvc',
          metric: pvcResource?.score ? `Bound ${pvcResource.score}` : 'Bound -',
          node: 'persistentvolumeclaims',
          severity: pvcResource?.severity ?? 'ok',
          title: 'PVC',
        },
      ],
    },
  ];

  return sections.filter((section) => section.id !== 'derived' || section.rows.length > 0);
};

const ClusterTopologyMap: React.FC<{
  affectedOnly?: boolean;
  edgeMode?: TopologyEdgeMode;
  onSelectNode?: (node: TopologyNodeKey) => void;
  selectedNode?: TopologyNodeKey;
  showEdgeLabels?: boolean;
  summary: ClusterSummary;
  variant?: 'service' | 'runtime';
}> = ({
  affectedOnly = false,
  edgeMode = 'all',
  onSelectNode,
  selectedNode,
  showEdgeLabels = true,
  summary,
  variant = 'service',
}) => {
  const nodeState: Severity = summary.nodes.notReady > 0 ? 'risk' : summary.nodes.pressureCount > 0 ? 'warn' : 'ok';
  const resources = summary.resources?.items ?? [];
  const routes = resources.find((resource) => resource.id === 'routes');
  const services = resources.find((resource) => resource.id === 'services');
  const deployments = resources.find((resource) => resource.id === 'deployments');
  const statefulSets = resources.find((resource) => resource.id === 'statefulsets');
  const daemonSets = resources.find((resource) => resource.id === 'daemonsets');
  const replicaSets = resources.find((resource) => resource.id === 'replicasets');
  const pods = resources.find((resource) => resource.id === 'pods');
  const pvcs = resources.find((resource) => resource.id === 'persistentvolumeclaims');
  const issueCount = summary.resources?.issues ?? 0;
  const podSummary = buildPodRcaSummary(summary);
  const isRuntimeTrace = variant === 'runtime';
  const nodeInteraction = (node: TopologyNodeKey) => {
    const nodeSummary = topologyNodeSummary(summary, node);
    return {
      dimmed: affectedOnly && nodeSummary.severity === 'ok',
      nodeId: node,
      onSelectNode,
      selected: selectedNode === node,
    };
  };

  const mapClassName = [
    'impact-map',
    isRuntimeTrace ? 'is-runtime-trace' : '',
    affectedOnly ? 'is-affected-only' : '',
    `is-edge-${edgeMode}`,
    showEdgeLabels ? 'has-edge-labels' : 'has-hidden-edge-labels',
  ].filter(Boolean).join(' ');

  return (
    <div className={mapClassName} role="img" aria-label={isRuntimeTrace ? '워크로드 런타임 추적' : '클러스터 리소스 관계도'}>
      <div className="impact-map__grid" aria-hidden="true" />
      <div className="impact-map__top">
        <div>
          <span>{isRuntimeTrace ? '워크로드 런타임 추적' : '서비스 영향 경로'}</span>
          <strong>{clusterLabel(summary)}</strong>
        </div>
        <div className="impact-map__snapshot">
          <span>스냅샷</span>
          <strong>{formatTime(summary.updatedAt)}</strong>
        </div>
      </div>

      <div className="impact-map__canvas">
        <svg aria-hidden="true" className="impact-map__links" preserveAspectRatio="none" viewBox="0 0 100 100">
          <defs>
            <marker id="impact-arrow" markerHeight="5" markerUnits="strokeWidth" markerWidth="5" orient="auto" refX="4.4" refY="2.5">
              <path d="M0,0 L5,2.5 L0,5 Z" fill="#7aa7d9" />
            </marker>
            <marker id="impact-arrow-warn" markerHeight="5" markerUnits="strokeWidth" markerWidth="5" orient="auto" refX="4.4" refY="2.5">
              <path d="M0,0 L5,2.5 L0,5 Z" fill="#f59e0b" />
            </marker>
          </defs>
          <path className="impact-link is-traffic" d="M14 27 C14 34 14 42 14 49" markerEnd="url(#impact-arrow)" />
          <path className="impact-link is-selector" d="M23 56 C37 56 55 53 72 53" markerEnd="url(#impact-arrow)" />
          <path className="impact-link is-owner" d="M50 20 C52 20 53 20 55 20" markerEnd="url(#impact-arrow)" />
          <path className="impact-link is-warn" d="M71 22 C76 28 77 40 72 48" markerEnd="url(#impact-arrow-warn)" />
          <path className="impact-link is-owner is-warn" d="M50 50 C57 50 64 51 72 53" markerEnd="url(#impact-arrow-warn)" />
          <path className="impact-link is-owner is-warn" d="M50 78 C59 75 66 64 72 57" markerEnd="url(#impact-arrow-warn)" />
          <path className="impact-link is-runtime" d="M70 76 C73 70 78 65 81 62" markerEnd="url(#impact-arrow)" />
          <path className="impact-link is-runtime" d="M88 76 C88 70 85 65 83 62" markerEnd="url(#impact-arrow)" />
        </svg>

        <div className="impact-map__zone impact-map__zone--entry">트래픽 진입</div>
        <div className="impact-map__zone impact-map__zone--workload">워크로드 컨트롤러</div>
        <div className="impact-map__zone impact-map__zone--runtime">파드 런타임</div>
        <div className="impact-map__zone impact-map__zone--substrate">런타임 기반</div>
        <span className="impact-edge-label impact-edge-label--exposes">노출</span>
        <span className="impact-edge-label impact-edge-label--selector">선택</span>
        <span className="impact-edge-label impact-edge-label--owner">소유</span>
        <span className="impact-edge-label impact-edge-label--scheduled">스케줄</span>
        <span className="impact-edge-label impact-edge-label--mounts">마운트</span>

        <ImpactNode
          className="impact-node--routes"
          detail={resourceNodeDetail(routes, '라우트 스냅샷 없음')}
          icon={<Network />}
          label={routes ? resourceNameLabel(routes.id, routes.name, routes.kind) : '라우트'}
          severity={resourceNodeSeverity(routes)}
          {...nodeInteraction('routes')}
        />
        <ImpactNode
          className="impact-node--services"
          detail={resourceNodeDetail(services, '서비스 스냅샷 없음')}
          icon={<Network />}
          label={services ? resourceNameLabel(services.id, services.name, services.kind) : '서비스'}
          severity={resourceNodeSeverity(services)}
          {...nodeInteraction('services')}
        />
        <ImpactNode
          className="impact-node--deployments"
          detail={resourceNodeDetail(deployments, '디플로이먼트 스냅샷 없음')}
          icon={<Cpu />}
          label={deployments ? resourceNameLabel(deployments.id, deployments.name, deployments.kind) : '디플로이먼트'}
          severity={resourceNodeSeverity(deployments)}
          {...nodeInteraction('deployments')}
        />
        <ImpactNode
          className="impact-node--statefulsets"
          detail={resourceNodeDetail(statefulSets, '스테이트풀셋 스냅샷 없음')}
          icon={<Cpu />}
          label={statefulSets ? resourceNameLabel(statefulSets.id, statefulSets.name, statefulSets.kind) : '스테이트풀셋'}
          severity={resourceNodeSeverity(statefulSets)}
          {...nodeInteraction('statefulsets')}
        />
        <ImpactNode
          className="impact-node--daemonsets"
          detail={resourceNodeDetail(daemonSets, '데몬셋 스냅샷 없음')}
          icon={<Cpu />}
          label={daemonSets ? resourceNameLabel(daemonSets.id, daemonSets.name, daemonSets.kind) : '데몬셋'}
          severity={resourceNodeSeverity(daemonSets)}
          {...nodeInteraction('daemonsets')}
        />
        <ImpactNode
          className="impact-node--replicasets"
          detail={resourceNodeDetail(replicaSets, '레플리카셋 스냅샷 없음')}
          icon={<Cpu />}
          label={replicaSets ? resourceNameLabel(replicaSets.id, replicaSets.name, replicaSets.kind) : '레플리카셋'}
          severity={resourceNodeSeverity(replicaSets)}
          {...nodeInteraction('replicasets')}
        />
        <ImpactNode
          className="impact-node--pods"
          detail={resourceNodeDetail(pods, '파드 스냅샷 없음')}
          icon={<Cpu />}
          label={pods ? resourceNameLabel(pods.id, pods.name, pods.kind) : '파드'}
          severity={resourceNodeSeverity(pods)}
          {...nodeInteraction('pods')}
        />
        <ImpactNode
          className="impact-node--nodes"
          detail={topologyNodeSummary(summary, 'nodes').detail}
          icon={<ShieldCheck />}
          label="노드"
          severity={nodeState}
          {...nodeInteraction('nodes')}
        />
        <ImpactNode
          className="impact-node--pvcs"
          detail={resourceNodeDetail(pvcs, 'PVC 스냅샷 없음')}
          icon={<GitBranch />}
          label={pvcs ? resourceNameLabel(pvcs.id, pvcs.name, pvcs.kind) : 'PVC'}
          severity={resourceNodeSeverity(pvcs)}
          {...nodeInteraction('persistentvolumeclaims')}
        />

        <div className="impact-map__legend">
          {isRuntimeTrace ? (
            <>
              <span><i className="is-warn" /> 이상 신호</span>
              <span><i className="is-owner" /> 소유 관계</span>
              <span><i className="is-selector" /> 서비스 셀렉터</span>
              <span><i className="is-runtime" /> 런타임 의존성</span>
              <strong>
                라우트가 서비스를 노출 · 서비스가 파드를 선택 · 컨트롤러가 파드를 소유 · 노드/PVC가 런타임을 지원 · 활성 파드 이슈 후보 {podSummary.issueCandidates}건
              </strong>
            </>
          ) : (
            <>
              <span><i className="is-ok" /> 정상</span>
              <span><i className="is-warn" /> 이상 신호</span>
              <span><i className="is-selector" /> 노출/선택</span>
              <span><i className="is-owner" /> 소유 관계</span>
              <span><i className="is-runtime" /> 스케줄/마운트</span>
              <strong>
                라우트가 서비스를 노출 · 서비스가 파드를 선택 · 컨트롤러가 파드를 소유 · 노드/PVC가 런타임을 지원 · 영향 후보 {issueCount}건
              </strong>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

const ImpactNode: React.FC<{
  className: string;
  detail: string;
  dimmed?: boolean;
  icon: React.ReactNode;
  label: string;
  nodeId?: TopologyNodeKey;
  onSelectNode?: (node: TopologyNodeKey) => void;
  selected?: boolean;
  severity: Severity;
}> = ({ className, detail, dimmed = false, icon, label, nodeId, onSelectNode, selected = false, severity }) => {
  const interactive = Boolean(nodeId && onSelectNode);
  const handleSelect = () => {
    if (nodeId && onSelectNode) {
      onSelectNode(nodeId);
    }
  };

  return (
    <article
      aria-pressed={interactive ? selected : undefined}
      className={`impact-node ${className} ${severityClass(severity)} ${selected ? 'is-selected' : ''} ${dimmed ? 'is-dimmed' : ''}`}
      onClick={interactive ? handleSelect : undefined}
      onKeyDown={
        interactive
          ? (event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                handleSelect();
              }
            }
          : undefined
      }
      role={interactive ? 'button' : undefined}
      tabIndex={interactive ? 0 : undefined}
    >
      <span className="impact-node__icon">{icon}</span>
      <div>
        <strong>{label}</strong>
        <small>{detail}</small>
      </div>
      <span aria-label={severityLabel[severity]} className="impact-node__status-dot" />
    </article>
  );
};

const issueSeverityLabel: Record<QueueItem['severity'], string> = {
  risk: '위험',
  warn: '주의',
};

const issueNextSteps = (item: QueueItem): string[] => {
  if (item.category === '클러스터 버전') {
    return [
      'ClusterVersion의 Upgradeable=False reason/message를 확인합니다.',
      '추천 업데이트와 조건부 업데이트를 구분해 적용 가능 범위를 확인합니다.',
      'AdminAck 또는 mirror signature 준비가 필요하면 업데이트 전 사전 작업으로 분리합니다.',
    ];
  }

  if (item.category === '리소스') {
    return [
      '클러스터 리소스 테이블에서 같은 리소스 유형의 상세 상태를 확인합니다.',
      '실패/대기/사용 불가 항목이 어떤 네임스페이스에 있는지 추가 조회합니다.',
      '조치가 필요하면 RCA 센터에서 증거와 실행 계획을 분리합니다.',
    ];
  }

  if (item.category === '오퍼레이터') {
    return [
      'ClusterOperator 조건의 reason/message를 우선 확인합니다.',
      '관련 네임스페이스의 파드 및 이벤트를 함께 조회합니다.',
      '진행 중인 업데이트나 재시도 상태인지 RCA 센터에서 교차 확인합니다.',
    ];
  }

  return [
    '게이트웨이가 수집한 증거와 현재 상태를 먼저 대조합니다.',
    '관련 리소스의 최근 이벤트와 상태 변화를 확인합니다.',
    '변경 작업은 승인/실행 기록 화면에서 별도로 추적합니다.',
  ];
};

const incidentLevelLabel: Record<QueueItem['severity'], string> = {
  risk: '심각 신호',
  warn: '주의 신호',
};

const issueMetrics = (item: QueueItem): string[] =>
  item.detail
    .split(' · ')
    .map((metric) => metric.trim())
    .filter(Boolean)
    .slice(0, 6);

const affectedScope = (item: QueueItem): string => {
  const issueEvidence = evidenceRows(item).find((row) => row.label === 'issues');
  if (issueEvidence?.value && issueEvidence.value !== '0') {
    return `이슈 후보 ${issueEvidence.value}건`;
  }

  const failedMetric = issueMetrics(item).find((metric) => /failed|pending|notready|unavailable|issues/i.test(metric));
  return failedMetric ?? issueSeverityLabel[item.severity];
};

const impactRows = (item: QueueItem): Array<{ label: string; value: string }> => [
  { label: '리소스', value: item.target ?? item.title },
  { label: '분류', value: item.category ?? '운영 이슈' },
  { label: '데이터 소스', value: item.source ?? '게이트웨이 요약' },
  { label: '스냅샷', value: item.updatedAt ?? '-' },
  { label: '영향 범위', value: affectedScope(item) },
];

const DetailDrawer: React.FC<{
  clusterName: string;
  item: QueueItem | null;
  onClose: () => void;
  onNavigate: (view: NavView) => void;
}> = ({ clusterName, item, onClose, onNavigate }) => {
  const runCommand = (view: NavView) => {
    onClose();
    onNavigate(view);
  };
  const metrics = item ? issueMetrics(item) : [];
  const impacts = item ? impactRows(item) : [];
  const evidence = item ? evidenceRows(item) : [];
  const runbook = item ? issueNextSteps(item) : [];

  return (
    <div className={`portal-drawer ${item ? 'is-open' : ''}`} onClick={onClose}>
      <aside className="portal-drawer__panel" onClick={(event) => event.stopPropagation()}>
        <div className="portal-drawer__head">
          <div>
            <span>이슈 대응 레일</span>
            <strong>{item ? item.title : '이슈 상세'}</strong>
          </div>
          <button aria-label="닫기" className="portal-icon-btn" onClick={onClose} title="닫기" type="button">
            <X />
          </button>
        </div>
        <div className="portal-drawer__body">
          {item ? (
            <>
              <section className={`incident-header ${severityClass(item.severity)}`}>
                <div className="incident-header__edge" aria-hidden="true" />
                <div className="incident-header__signal">
                  <span>{incidentLevelLabel[item.severity]}</span>
                  <h2>{item.title}</h2>
                  <p>
                    {clusterName} / {item.category ?? '운영 이슈'} / {item.target ?? item.title}
                  </p>
                </div>
                <div className="incident-header__telemetry">
                  <span>감지 시각</span>
                  <strong>{item.updatedAt ?? '-'}</strong>
                  <span>데이터 소스</span>
                  <strong>{item.source ?? '게이트웨이 요약'}</strong>
                  <span>신뢰도</span>
                  <strong>{item.updatedAt ? '실시간 소스' : '스냅샷'}</strong>
                </div>
                <div className="incident-metrics">
                  {metrics.map((metric) => (
                    <span key={metric}>{metric}</span>
                  ))}
                </div>
              </section>

              <section className="incident-block">
                <div className="incident-block__title">
                  <Network />
                  영향 범위
                </div>
                <div className="impact-rows">
                  {impacts.map((row) => (
                    <div className="impact-row" key={row.label}>
                      <span>{row.label}</span>
                      <strong>{row.value}</strong>
                    </div>
                  ))}
                </div>
              </section>

              <section className="incident-block">
                <div className="incident-block__title">
                  <FileText />
                  증거 스트림
                </div>
                <div className="evidence-stream">
                  <div className="evidence-stream__head">
                    <span>신호</span>
                    <span>값</span>
                    <span>상태</span>
                  </div>
                  {evidence.map((row) => (
                    <div className="evidence-row" key={`${row.label}-${row.value}`}>
                      <span>{evidenceLabel(row.label)}</span>
                      <strong>{row.value}</strong>
                      <em className={`is-${row.status}`}>{evidenceStatusLabel(row.status)}</em>
                    </div>
                  ))}
                </div>
              </section>

              <section className="incident-block">
                <div className="incident-block__title">
                  <ClipboardCheck />
                  런북 체크포인트
                </div>
                <ol className="runbook-list">
                  {runbook.map((step, index) => (
                    <li key={step}>
                      <span>{String(index + 1).padStart(2, '0')}</span>
                      <p>{step}</p>
                      <em>{index === 2 ? '자동화 가능' : '미확인'}</em>
                    </li>
                  ))}
                </ol>
              </section>
            </>
          ) : (
            <EmptyState label="선택된 이슈가 없습니다." />
          )}
        </div>
        {item && (
          <div className="incident-command-bar">
            <div>
              <span>다음 명령</span>
              <strong>권장: RCA 추적</strong>
            </div>
            <button className="incident-command-bar__primary" onClick={() => runCommand('rca')} type="button">
              RCA 추적 열기
            </button>
            <button onClick={() => runCommand('endpoints')} type="button">
              리소스 상태 보기
            </button>
            <button onClick={onClose} type="button">
              닫기
            </button>
          </div>
        )}
      </aside>
    </div>
  );
};

const Panel: React.FC<{
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  title: string;
}> = ({ action, children, className = '', title }) => (
  <section className={`portal-panel ${className}`}>
    <div className="portal-panel__head">
      <div className="portal-panel__title">{title}</div>
      {action}
    </div>
    <div className="portal-panel__body">{children}</div>
  </section>
);

const EndpointTable: React.FC<{
  endpoints: Endpoint[];
}> = ({ endpoints }) => {
  const [page, setPage] = React.useState(1);
  const [pageSize, setPageSize] = React.useState(10);
  const [query, setQuery] = React.useState('');
  const [severityFilter, setSeverityFilter] = React.useState<'all' | Severity>('all');
  const okCount = endpoints.filter((endpoint) => endpoint.severity === 'ok').length;
  const warnCount = endpoints.filter((endpoint) => endpoint.severity === 'warn').length;
  const riskCount = endpoints.filter((endpoint) => endpoint.severity === 'risk').length;
  const endpointTabs: Array<{ id: 'all' | Severity; label: string; value: number }> = [
    { id: 'all', label: '전체', value: endpoints.length },
    { id: 'ok', label: '정상', value: okCount },
    { id: 'warn', label: '주의', value: warnCount },
    { id: 'risk', label: '위험', value: riskCount },
  ];
  const normalizedQuery = query.trim().toLowerCase();
  const visibleEndpoints = endpoints.filter((endpoint) => {
    const matchesSeverity = severityFilter === 'all' || endpoint.severity === severityFilter;
    const searchable = `${endpoint.name} ${endpoint.type} ${endpoint.group} ${endpoint.path}`.toLowerCase();
    return matchesSeverity && (!normalizedQuery || searchable.includes(normalizedQuery));
  });
  const pageCount = Math.max(1, Math.ceil(visibleEndpoints.length / pageSize));
  const currentPage = Math.min(page, pageCount);
  const startIndex = (currentPage - 1) * pageSize;
  const pageEndpoints = visibleEndpoints.slice(startIndex, startIndex + pageSize);
  const rangeStart = visibleEndpoints.length === 0 ? 0 : startIndex + 1;
  const rangeEnd = Math.min(startIndex + pageSize, visibleEndpoints.length);

  React.useEffect(() => {
    setPage(1);
  }, [normalizedQuery, pageSize, severityFilter]);

  React.useEffect(() => {
    setPage((current) => Math.min(current, pageCount));
  }, [pageCount]);

  return (
    <section className="portal-panel table-panel">
      <div className="table-panel__top">
        <div className="portal-panel__title">클러스터 리소스</div>
        <div className="portal-tabs">
          {endpointTabs.map((tab) => (
            <button
              className={severityFilter === tab.id ? 'is-active' : ''}
              key={tab.id}
              onClick={() => setSeverityFilter(tab.id)}
              type="button"
            >
              {tab.label} {tab.value}
            </button>
          ))}
        </div>
        <label className="portal-search">
          <Search />
          <input
            onChange={(event) => setQuery(event.target.value)}
            placeholder="리소스 검색"
            value={query}
          />
        </label>
        <label className="table-page-size">
          <span>페이지당</span>
          <select
            aria-label="페이지당 리소스 수"
            onChange={(event) => setPageSize(Number(event.target.value))}
            value={pageSize}
          >
            {endpointPageSizeOptions.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="table-scroll">
        <table className="endpoint-table">
          <thead>
            <tr>
              <th>이름</th>
              <th>유형</th>
              <th>그룹</th>
              <th>상태</th>
              <th>CPU</th>
              <th>메모리</th>
              <th>응답시간</th>
              <th>최근 이벤트</th>
            </tr>
          </thead>
          <tbody>
            {visibleEndpoints.length === 0 ? (
              <tr>
                <td colSpan={8}>조건에 맞는 리소스가 없습니다.</td>
              </tr>
            ) : (
              pageEndpoints.map((endpoint) => (
                <tr key={endpoint.id}>
                  <td>
                    <strong>{endpoint.name}</strong>
                    <small>{endpoint.path}</small>
                  </td>
                  <td>{endpoint.type}</td>
                  <td>{endpoint.group}</td>
                  <td>
                    <StatusBadge severity={endpoint.severity} />
                  </td>
                  <td>{endpoint.cpu}</td>
                  <td>{endpoint.memory}</td>
                  <td>{endpoint.latency}</td>
                  <td>
                    <span className={`event-dot ${severityClass(endpoint.severity)}`} />
                    {endpoint.lastEvent}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <div className="table-pagination">
        <span className="table-pagination__summary">
          {rangeStart}-{rangeEnd} / {visibleEndpoints.length}
        </span>
        <div className="table-pagination__controls">
          <button
            aria-label="이전 페이지"
            className="portal-icon-btn"
            disabled={currentPage <= 1}
            onClick={() => setPage((current) => Math.max(1, current - 1))}
            title="이전 페이지"
            type="button"
          >
            <ChevronLeft />
          </button>
          <strong>{currentPage} / {pageCount}</strong>
          <button
            aria-label="다음 페이지"
            className="portal-icon-btn"
            disabled={currentPage >= pageCount}
            onClick={() => setPage((current) => Math.min(pageCount, current + 1))}
            title="다음 페이지"
            type="button"
          >
            <ChevronRight />
          </button>
        </div>
      </div>
    </section>
  );
};
const ServiceMapView: React.FC<{ onNavigate: (view: NavView) => void; summary: ClusterSummary }> = ({
  onNavigate,
  summary,
}) => {
  const [affectedOnly, setAffectedOnly] = React.useState(false);
  const [edgeMode, setEdgeMode] = React.useState<TopologyEdgeMode>('all');
  const [showEdgeLabels, setShowEdgeLabels] = React.useState(true);
  const [selectedNode, setSelectedNode] = React.useState<TopologyNodeKey>('pods');
  const [showInspectorCommands, setShowInspectorCommands] = React.useState(false);
  const primarySignals = topologyPrimarySignals(summary);
  const derivedSignals = topologyDerivedSignals(summary);
  const otherSignals = topologyOtherSignals(summary);
  const inspector = buildTraceInspector(summary, selectedNode);
  const impactSignalSections = buildImpactSignalStack(summary);
  const traceNodes = inspector.trace.split(/\s*->\s*/);
  const compactFocus = inspector.focus.includes('·') ? inspector.focus.split('·').slice(1).join('·').trim() : inspector.focus;
  const summarySignals = inspector.signals.filter((signal) => signal.label !== '완료 제외').slice(0, 5);
  const nextChecksByNode: Record<TopologyNodeKey, string[]> = {
    daemonsets: ['DaemonSet 상태', '노드별 Pod', '이벤트'],
    deployments: ['가용 수량', 'ReplicaSet', 'Pod readiness'],
    nodes: ['Node condition', 'Pressure', '스케줄링'],
    persistentvolumeclaims: ['PVC Bound', '마운트 이벤트', 'Pod 볼륨'],
    pods: ['Pod 이벤트', 'Container 상태', 'Owner chain'],
    replicasets: ['Ready 차이', 'Owner chain', 'Pod readiness'],
    routes: ['Route 대상', 'Service 연결', 'TLS/Host'],
    services: ['Selector', 'EndpointSlice', 'Pod 연결'],
    statefulsets: ['Ready 수량', 'PVC 연결', 'Pod identity'],
  };
  const nextChecks = nextChecksByNode[selectedNode];
  const impactRows = impactSignalSections.flatMap((section) =>
    section.id === 'cleared'
      ? []
      : section.rows.map((row) => ({
          ...row,
          roleLabel: section.id === 'primary' ? 'Primary signal' : 'Derived',
        })),
  );
  const clearedRows = impactSignalSections.find((section) => section.id === 'cleared')?.rows ?? [];
  const copyInspectorCommands = React.useCallback(() => {
    const commands = inspector.commands.map((command) => `# ${command.title}\n${command.command}`).join('\n\n');
    void navigator.clipboard?.writeText(commands);
  }, [inspector.commands]);
  const copyCommand = React.useCallback((command: string) => {
    void navigator.clipboard?.writeText(command);
  }, []);
  const edgeButtons: Array<{ id: TopologyEdgeMode; label: string }> = [
    { id: 'all', label: '전체 관계' },
    { id: 'traffic', label: '트래픽' },
    { id: 'ownership', label: '소유 관계' },
    { id: 'runtime', label: '런타임' },
  ];

  return (
    <section className="service-map-workbench stack-view">
      <section className="map-control-strip">
        <div className="map-control-strip__main">
          <span>서비스 맵 / 클러스터 토폴로지</span>
          <strong>{clusterLabel(summary)}</strong>
          <p>
            전체 네임스페이스 · 스냅샷 {formatTime(summary.updatedAt)} · 게이트웨이 정상 · OCP {displayOpenShiftVersion(summary.version.version)}
            {summary.nodes.total === 1 ? ' · 단일 노드 런타임' : ''}
          </p>
          <small>
            활성 신호 {summary.resources?.issues ?? 0}건 · Primary 파드 {primarySignals}건 · Derived 컨트롤러 {derivedSignals}건
            {otherSignals > 0 ? ` · 기타 ${otherSignals}건` : ''}
          </small>
        </div>
        <div className="map-control-strip__controls">
          <button className={affectedOnly ? 'is-active' : ''} onClick={() => setAffectedOnly((value) => !value)} type="button">
            영향만
          </button>
          {edgeButtons.map((button) => (
            <button
              className={edgeMode === button.id ? 'is-active' : ''}
              key={button.id}
              onClick={() => setEdgeMode(button.id)}
              type="button"
            >
              {button.label}
            </button>
          ))}
          <button className={showEdgeLabels ? 'is-active' : ''} onClick={() => setShowEdgeLabels((value) => !value)} type="button">
            관계 라벨
          </button>
        </div>
      </section>

      <section className="portal-panel service-map-page">
        <div className="portal-panel__head">
          <div className="portal-panel__title">클러스터 리소스 관계도</div>
          <StatusBadge label={`노드 ${summary.nodes.ready}/${summary.nodes.total}`} severity={summary.nodes.notReady > 0 ? 'risk' : 'ok'} />
        </div>
        <div className="portal-panel__body">
          <ClusterTopologyMap
            affectedOnly={affectedOnly}
            edgeMode={edgeMode}
            onSelectNode={setSelectedNode}
            selectedNode={selectedNode}
            showEdgeLabels={showEdgeLabels}
            summary={summary}
          />
        </div>
      </section>

      <section className="portal-panel topology-inspector">
        <div className="portal-panel__head">
          <div className="portal-panel__title">선택 경로 요약</div>
          <div className="rca-command-actions">
            <button className="portal-button" onClick={() => onNavigate('rca')} type="button">RCA 열기</button>
            <button
              className="portal-button"
              disabled={inspector.commands.length === 0}
              onClick={() => setShowInspectorCommands((value) => !value)}
              type="button"
            >
              {showInspectorCommands ? 'oc 명령 닫기' : 'oc 명령 보기'}
            </button>
          </div>
        </div>
        <div className="trace-summary">
          <div className="trace-summary__main">
            <span className="trace-summary__eyebrow">선택 경로</span>
            <div className="trace-path" aria-label={inspector.trace}>
              {traceNodes.map((node, index) => (
                <React.Fragment key={`${node}-${index}`}>
                  {index > 0 && <ChevronRight aria-hidden="true" />}
                  <strong>{node}</strong>
                </React.Fragment>
              ))}
            </div>
            <div className="trace-summary__finding">
              <div>
                <strong>{inspector.title} · {compactFocus}</strong>
                <p>{inspector.insight}</p>
              </div>
              <StatusBadge severity={inspector.severity} />
            </div>
          </div>
          <div className="trace-summary__signals">
            {summarySignals.map((signal) => (
              <article key={`${signal.label}-${signal.value}`}>
                <span>{signal.label}</span>
                <strong>{signal.value}</strong>
              </article>
            ))}
          </div>
          <div className="trace-summary__next">
            <span>다음 확인</span>
            <div>
              {nextChecks.map((check) => (
                <b key={`${selectedNode}-${check}`}>{check}</b>
              ))}
            </div>
          </div>
          {showInspectorCommands && (
            <div className="command-bundle">
              <div className="command-bundle__head">
                <span>oc 명령</span>
                <button className="command-copy" onClick={copyInspectorCommands} type="button">전체 복사</button>
              </div>
              {inspector.commands.map((command) => (
                <article key={`${command.title}-${command.command}`}>
                  <div>
                    <strong>{command.title}</strong>
                    <code>{command.command}</code>
                  </div>
                  <button className="command-copy" onClick={() => copyCommand(command.command)} type="button">복사</button>
                </article>
              ))}
            </div>
          )}
        </div>
      </section>

      <Panel title="영향 후보">
        <div className="impact-candidate-list">
          {impactRows.map((row) => (
            <article className={`impact-candidate-row ${severityClass(row.severity)}`} key={row.id}>
              <StatusBadge severity={row.severity} />
              <div className="impact-candidate-row__body">
                <div className="impact-candidate-row__top">
                  <strong>{row.title}</strong>
                  <b>{row.metric}</b>
                </div>
                <p>{row.chips.slice(0, row.roleLabel === 'Primary signal' ? 4 : 3).join(' · ')}</p>
                <small>{row.roleLabel === 'Primary signal' ? 'Primary signal' : row.description}</small>
              </div>
            </article>
          ))}
          {clearedRows.length > 0 && (
            <div className="impact-cleared-line">
              <span>정상 의존성</span>
              <strong>{clearedRows.map((row) => `${row.title} ${row.metric}`).join(' · ')}</strong>
            </div>
          )}
        </div>
      </Panel>
    </section>
  );
};

const ResourceInventoryView: React.FC<{
  summary: ClusterSummary;
}> = ({ summary }) => {
  const endpoints = buildEndpoints(summary);
  const resources = summary.resources?.items ?? [];
  const risk = endpoints.filter((endpoint) => endpoint.severity === 'risk').length;
  const warn = endpoints.filter((endpoint) => endpoint.severity === 'warn').length;

  return (
    <section className="resource-inventory stack-view">
      <section className="inventory-summary-grid">
        <KpiCard color={risk > 0 ? 'red' : 'green'} label="위험 리소스" sub={`주의 ${warn}`} value={risk} />
        <KpiCard color="blue" label="전체 리소스" sub="표시 대상" value={endpoints.length} />
        <KpiCard color={summary.nodes.notReady > 0 ? 'red' : 'green'} label="노드 상태" sub={`비정상 ${summary.nodes.notReady}`} value={`${summary.nodes.ready}/${summary.nodes.total}`} />
        <KpiCard color={summary.resources?.issues ? 'red' : 'green'} label="리소스 이슈" sub="게이트웨이 요약" value={summary.resources?.issues ?? 0} />
      </section>
      <EndpointTable endpoints={endpoints} />
      <Panel title="리소스 그룹 분포">
        <div className="resource-distribution">
          {resources.map((resource) => (
            <article key={resource.id}>
              <div>
                <strong>{resourceNameLabel(resource.id, resource.name, resource.kind)}</strong>
                <span>{localizeTelemetryText(resource.detail)}</span>
              </div>
              <div className="meter"><span style={{ width: `${Math.min(100, Number(resource.ready) / Math.max(1, resource.total) * 100)}%` }} /></div>
              <b>{resource.score}</b>
            </article>
          ))}
        </div>
      </Panel>
    </section>
  );
};

const SettingsView: React.FC<{ status: AiopsRuntimeStatus; summary: ClusterSummary }> = ({ status, summary }) => {
  const capabilities = status.spec.capabilities;
  const [policyMode, setPolicyMode] = React.useState(capabilities.mutationsEnabled ? '승인 후 실행' : '읽기/증거 수집');
  const [notifyOps, setNotifyOps] = React.useState(true);
  const [notifyAudit, setNotifyAudit] = React.useState(false);

  return (
    <section className="settings-workbench stack-view">
      <section className="sample-banner is-config">
        <strong>화면 설정</strong>
        <span>현재 설정 화면은 포털에서 정책과 표시 옵션을 확인하는 UI입니다.</span>
      </section>
      <section className="settings-grid">
        <Panel title="게이트웨이 연결">
          <div className="settings-form">
            <label><span>API URL</span><input readOnly value={displayApiEndpoint(summary.apiUrl)} /></label>
            <label><span>클러스터</span><input readOnly value={clusterLabel(summary)} /></label>
            <label><span>상태</span><input readOnly value={summary.healthScore >= 90 ? '정상' : '확인 필요'} /></label>
          </div>
        </Panel>
        <Panel title="승인/실행 정책">
          <div className="settings-form">
            <label>
              <span>정책 모드</span>
              <select onChange={(event) => setPolicyMode(event.target.value)} value={policyMode}>
                <option>읽기/증거 수집</option>
                <option>승인 후 실행</option>
                <option>수동 승인 전용</option>
              </select>
            </label>
            <div className="capability-list">
              <span>변경 실행 <strong>{capabilities.mutationsEnabled ? '허용' : '차단'}</strong></span>
              <span>조치 실행기 <strong>{capabilities.actionExecutorConfigured ? '설정됨' : '미설정'}</strong></span>
              <span>감사 원장 <strong>{capabilities.recordStoreEnabled ? '켜짐' : '꺼짐'}</strong></span>
            </div>
          </div>
        </Panel>
        <Panel title="알림 채널">
          <div className="toggle-list">
            <label><input checked={notifyOps} onChange={(event) => setNotifyOps(event.target.checked)} type="checkbox" /> 운영 채널 알림</label>
            <label><input checked={notifyAudit} onChange={(event) => setNotifyAudit(event.target.checked)} type="checkbox" /> 감사 채널 알림</label>
            <label><input checked readOnly type="checkbox" /> 포털 배너 알림</label>
          </div>
        </Panel>
        <Panel title="데이터 보존">
          <div className="settings-form">
            <label><span>감사 ConfigMap</span><input readOnly value={capabilities.recordStoreConfigMap ?? '미설정'} /></label>
            <label><span>이벤트 폴링</span><input readOnly value="30초" /></label>
            <label><span>샘플 데이터</span><input readOnly value="문서/보고서 화면에만 표시" /></label>
          </div>
        </Panel>
      </section>
    </section>
  );
};

const AppContent: React.FC<{
  activeView: NavView;
  clock: string;
  events: AiopsEventFeed;
  onAssistantLaunch?: AssistantLaunchHandler;
  onNavigate: (view: NavView) => void;
  onOpenItem: (item: QueueItem) => void;
  onPageContextChange?: (context: Record<string, unknown>) => void;
  status: AiopsRuntimeStatus;
  summary: ClusterSummary;
}> = ({ activeView, clock, events, onAssistantLaunch, onNavigate, onOpenItem, onPageContextChange, status, summary }) => {
  if (activeView === 'dashboard') {
    return (
      <DashboardView
        activities={buildActivities(summary, status, events)}
        alerts={buildAlerts(summary, status)}
        clock={clock}
        endpoints={buildEndpoints(summary)}
        formatActivitySource={sourceLabel}
        formatOpenShiftVersion={displayOpenShiftVersion}
        getScopeDetailRows={(scope) => scopeDetailRows(scope, summary, status)}
        onNavigate={onNavigate}
        onOpenItem={onOpenItem}
        queues={buildQueues(summary, status)}
        renderEndpointTable={(endpoints) => <EndpointTable endpoints={endpoints} />}
        renderTopology={() => <ClusterTopologyMap summary={summary} />}
        scopes={buildScopes(summary, status)}
        status={status}
        summary={summary}
      />
    );
  }
  if (activeView === 'executions') {
    return <ExecutionRecordsView onNavigate={onNavigate} status={status} />;
  }
  if (activeView === 'rca') {
    const rcaQueues = buildQueues(summary, status);
    return (
      <RcaView
        buildAssistantContext={(item, actionType) => queueAssistantContext(item, 'rca-center', actionType)}
        clusterName={clusterLabel(summary)}
        fallbackQueues={sampleRcaQueues}
        liveQueues={rcaQueues}
        onAssistantLaunch={onAssistantLaunch}
        onNavigate={onNavigate}
        onOpenItem={onOpenItem}
        onPageContextChange={onPageContextChange}
        renderRuntimeTopology={() => <ClusterTopologyMap summary={summary} variant="runtime" />}
        summary={summary}
      />
    );
  }
  if (activeView === 'service-map') {
    return <ServiceMapView onNavigate={onNavigate} summary={summary} />;
  }
  if (activeView === 'endpoints') {
    return <ResourceInventoryView summary={summary} />;
  }
  if (activeView === 'alerts') {
    const alertQueues = buildQueues(summary, status);
    return (
      <AlertsEventsView
        buildAssistantContext={(group) => eventAssistantContext(group, 'event-detail')}
        clusterName={clusterLabel(summary)}
        fallbackQueues={sampleRcaQueues}
        lastUpdatedAt={summary.updatedAt}
        onAssistantLaunch={onAssistantLaunch}
        onOpenItem={onOpenItem}
        onPageContextChange={onPageContextChange}
        queues={alertQueues}
        rows={buildAlertEventRows(summary, status, events)}
        status={status}
      />
    );
  }
  if (activeView === 'wiki') {
    return <WikiDocsView />;
  }
  if (activeView === 'reports') {
    const reportIssues = buildQueues(summary, status);
    return (
      <ReportsView
        clusterName={clusterLabel(summary)}
        issueOptions={reportIssues.length > 0 ? reportIssues : sampleRcaQueues}
        openShiftVersion={displayOpenShiftVersion(summary.version.version)}
        status={status}
        summary={summary}
      />
    );
  }
  return <SettingsView status={status} summary={summary} />;
};

export const App: React.FC = () => {
  const clock = useLiveClock();
  const runtime = usePortalRuntime();
  const [activeView, setActiveView] = React.useState<NavView>(() => viewFromLocation());
  const [drawerItem, setDrawerItem] = React.useState<QueueItem | null>(null);
  const navigateToView = React.useCallback((view: NavView) => {
    if (activeView === view && viewFromLocation() === view) {
      return;
    }

    setActiveView((current) => (current === view ? current : view));
    setDrawerItem(null);

    const nextPath = standaloneRouteByView[view] ?? standaloneRouteByView.dashboard;
    if (window.location.pathname !== nextPath || window.location.hash) {
      window.history.pushState({ view }, '', nextPath);
    }
  }, [activeView]);

  React.useEffect(() => {
    const handleHistoryChange = () => {
      setActiveView(viewFromLocation());
      setDrawerItem(null);
    };

    window.addEventListener('popstate', handleHistoryChange);
    window.addEventListener('hashchange', handleHistoryChange);
    return () => {
      window.removeEventListener('popstate', handleHistoryChange);
      window.removeEventListener('hashchange', handleHistoryChange);
    };
  }, []);

  return (
    <div className="aiops-console-portal portal-shell">
      <Sidebar
        activeView={activeView}
        clock={clock}
        setActiveView={navigateToView}
        summary={runtime.summary}
      />
      <main className="portal-main">
        <Topbar
          activeView={activeView}
          alarmCount={aiopsAlarmCount(runtime.events)}
          clusterName={clusterLabel(runtime.summary)}
          isLive={runtime.isLive}
          loading={runtime.loading}
          onNavigate={navigateToView}
          onRefresh={runtime.refresh}
        />
        <section className="portal-content">
          {runtime.error && (
            <ClusterSignalStrip
              error={runtime.error}
              lastSnapshot={formatTime(runtime.summary.updatedAt)}
              onNavigate={navigateToView}
              onRefresh={runtime.refresh}
            />
          )}
          <AppContent
            activeView={activeView}
            clock={clock}
            events={runtime.events}
            onNavigate={navigateToView}
            onOpenItem={setDrawerItem}
            status={runtime.status}
            summary={runtime.summary}
          />
        </section>
      </main>
      <DetailDrawer
        clusterName={clusterLabel(runtime.summary)}
        item={drawerItem}
        onClose={() => setDrawerItem(null)}
        onNavigate={navigateToView}
      />
    </div>
  );
};

export const PortalEmbeddedPage: React.FC<{ view: NavView }> = ({ view }) => {
  const clock = useLiveClock();
  const runtime = usePortalRuntime();
  const [assistantDraftPrompt, setAssistantDraftPrompt] = React.useState<AssistantDraftPrompt | undefined>();
  const [assistantPageContext, setAssistantPageContext] = React.useState<Record<string, unknown>>({});
  const [drawerItem, setDrawerItem] = React.useState<QueueItem | null>(null);
  const assistantPageContextJsonRef = React.useRef('');

  const navigateToView = React.useCallback((nextView: NavView) => {
    setDrawerItem(null);
    const nextRoute = standaloneRouteByView[nextView] ?? standaloneRouteByView.dashboard;
    if (window.location.pathname !== nextRoute) {
      window.location.assign(nextRoute);
    }
  }, []);

  React.useEffect(() => {
    setDrawerItem(null);
  }, [view]);

  const updateAssistantPageContext = React.useCallback((context: Record<string, unknown>) => {
    const nextJson = JSON.stringify(context);
    if (assistantPageContextJsonRef.current === nextJson) {
      return;
    }
    assistantPageContextJsonRef.current = nextJson;
    setAssistantPageContext(context);
  }, []);

  const launchAssistant = React.useCallback<AssistantLaunchHandler>(
    ({ context, executionMode, taskMode = 'troubleshooting' }) => {
      setAssistantDraftPrompt({
        id: `aiops-${context.source}-${Date.now().toString(36)}`,
        pageContext: {
          aiopsExecutionMode: executionMode,
          aiopsLaunchContext: context,
          actionType: context.actionType,
          evidenceRefs: context.evidenceRefs,
          kind: context.kind,
          name: context.name,
          namespace: context.namespace,
          reason: context.reason,
          severity: context.severity,
          source: context.source,
        },
        prompt: context.promptDraft,
        taskMode,
      });
    },
    [],
  );

  return (
    <div className="aiops-console-portal portal-shell portal-shell--embedded">
      <main className="portal-main">
        <Topbar
          activeView={view}
          alarmCount={aiopsAlarmCount(runtime.events)}
          clusterName={clusterLabel(runtime.summary)}
          isLive={runtime.isLive}
          loading={runtime.loading}
          onNavigate={navigateToView}
          onRefresh={runtime.refresh}
        />
        <section className="portal-content">
          {runtime.error && (
            <ClusterSignalStrip
              error={runtime.error}
              lastSnapshot={formatTime(runtime.summary.updatedAt)}
              onNavigate={navigateToView}
              onRefresh={runtime.refresh}
            />
          )}
          <AppContent
            activeView={view}
            clock={clock}
            events={runtime.events}
            onAssistantLaunch={launchAssistant}
            onNavigate={navigateToView}
            onOpenItem={setDrawerItem}
            onPageContextChange={updateAssistantPageContext}
            status={runtime.status}
            summary={runtime.summary}
          />
        </section>
      </main>
      <DetailDrawer
        clusterName={clusterLabel(runtime.summary)}
        item={drawerItem}
        onClose={() => setDrawerItem(null)}
        onNavigate={navigateToView}
      />
      <AssistantLauncher
        ambientPageContext={assistantPageContext}
        draftPrompt={assistantDraftPrompt}
        onRunComplete={runtime.refresh}
      />
    </div>
  );
};
