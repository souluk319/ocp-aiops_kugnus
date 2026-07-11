import { ledgerKindLabel } from './executionLedgerModel';
import { formatTime } from './portalModel';
import type { ClusterSummary, Endpoint, Severity } from './types';

const PUBLIC_WEB_URL_RE =
  /\bhttps?:\/\/(?:github\.com|docs\.openshift\.com|docs\.redhat\.com|access\.redhat\.com)\/[^\s)]+/gi;

const stripPublicWebUrls = (value: string): string =>
  value
    .replace(/\s*See also\s+https?:\/\/(?:github\.com|docs\.openshift\.com|docs\.redhat\.com|access\.redhat\.com)\/[^\s)]+/gi, '')
    .replace(PUBLIC_WEB_URL_RE, '')
    .replace(/\s{2,}/g, ' ')
    .trim();

export const localizeTelemetryText = (value: string): string =>
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

export const displayApiEndpoint = (apiUrl?: string): string => {
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

export const displayOpenShiftVersion = (version?: string): string => {
  if (!version) {
    return '-';
  }
  return version.replace(/-local\b/i, '');
};

export const displayNamespaceLabel = (namespace?: string): string => {
  if (!namespace) {
    return '-';
  }
  if (/^komsco-ai-local$/i.test(namespace)) {
    return '검증 네임스페이스';
  }
  return localizeTelemetryText(namespace);
};

export const clusterLabel = (summary: ClusterSummary): string => {
  if (!summary.apiUrl) {
    return '게이트웨이 연결 대기';
  }
  return displayApiEndpoint(summary.apiUrl);
};

export const pressureLabels = (pressures: ClusterSummary['nodes']['items'][number]['pressures']): string[] => {
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

export const nodeSeverity = (node: ClusterSummary['nodes']['items'][number]): Severity => {
  if (!node.ready) {
    return 'risk';
  }
  return pressureLabels(node.pressures).length > 0 ? 'warn' : 'ok';
};

export const operatorSeverity = (operator: ClusterSummary['operators']['issues'][number]): Severity => {
  if (!operator.available || operator.degraded) {
    return 'risk';
  }
  return operator.progressing ? 'warn' : 'ok';
};

export const formatCpu = (value?: string): string => {
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

export const formatMemory = (value?: string): string => {
  if (!value) {
    return '-';
  }
  if (value.endsWith('Ki')) {
    const gib = Number(value.slice(0, -2)) / 1024 / 1024;
    return Number.isFinite(gib) ? `${gib.toFixed(1)} GiB` : value;
  }
  return value;
};

export const aiopsWorkloadItems = (summary: ClusterSummary) => [
  ...(summary.aiopsWorkloads?.deployments ?? []),
  ...(summary.aiopsWorkloads?.daemonsets ?? []),
];

export const buildEndpoints = (summary: ClusterSummary): Endpoint[] => {
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
    ? [{
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
      }]
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
