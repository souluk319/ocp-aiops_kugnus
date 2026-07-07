import * as React from 'react';
import { Button } from '@patternfly/react-core';
import {
  BoltIcon,
  CheckCircleIcon,
  ClipboardCheckIcon,
  ExclamationTriangleIcon,
  HistoryIcon,
  ServerIcon,
  ShieldAltIcon,
} from '@patternfly/react-icons';

import {
  type AiopsActionCandidate,
  type AiopsAnomalyFinding,
  type AiopsOverview,
  type AiopsRecord,
  type AiopsRuntimeStatus,
  type ClusterSummary,
} from '../services/aiGateway';
import { safeEvidenceText } from '../utils/evidenceDisplay';

type Tone = 'danger' | 'info' | 'success' | 'warning';

type AiopsDashboardData = {
  overview: AiopsOverview | null;
  status: AiopsRuntimeStatus | null;
  summary: ClusterSummary | null;
};

const ACTION_CANDIDATE_DISPLAY_LIMIT = 3;

export type AssistantDraftPromptRequest = {
  id: string;
  pageContext: Record<string, unknown>;
  prompt: string;
  taskMode: 'troubleshooting';
};

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

const compactDigest = (value?: string): string => {
  if (!value) {
    return '';
  }

  return value.length > 28 ? value.slice(0, 24) + '...' : value;
};

const recordPhase = (record: AiopsRecord): string => {
  const spec = asObject(record.spec);
  const status = asObject(spec.status);
  const approvalDecision = asObject(spec.approvalDecision);
  const mutationOutcome = asObject(spec.mutationOutcome);

  return textValue(
    status.phase ?? approvalDecision.status ?? mutationOutcome.status ?? spec.action,
    'recorded',
  );
};

const runtimeModeLabel = (mode?: string): string => {
  if (mode === 'read-only' || mode === 'read_only') {
    return '읽기 전용';
  }
  if (mode === 'execute') {
    return '실행 가능';
  }
  if (mode === 'controlled_execution') {
    return '승인 실행';
  }
  if (mode === 'evidence_check') {
    return '증거 확인';
  }
  if (mode === 'unrestricted') {
    return '무제한 실행';
  }
  return mode || '상태 확인 중';
};
const anomalyStatusTone = (status?: string): Tone => {
  if (status === 'normal') {
    return 'success';
  }
  if (status === 'risk' || status === 'error') {
    return 'danger';
  }
  return 'warning';
};

const anomalySeverityTone = (severity?: string): Tone => {
  if (severity === '위험') {
    return 'danger';
  }
  if (severity === '정상') {
    return 'success';
  }
  return 'warning';
};

const anomalyResourceLabel = (finding: AiopsAnomalyFinding): string => {
  const resource = finding.resource ?? {};
  const namespace = finding.namespace || resource.namespace || 'cluster-scoped';
  const name = resource.name || finding.title;
  const kind = resource.kind || finding.category || 'Resource';

  return `${namespace}/${kind}/${name}`;
};

const actionCandidateTone = (riskLevel?: string, status?: string): Tone => {
  if (status === 'normal') {
    return 'success';
  }
  if (status === 'blocked' || riskLevel === 'high') {
    return 'danger';
  }
  return 'warning';
};

const actionCandidateTargetLabel = (candidate: AiopsActionCandidate): string => {
  const target = candidate.target ?? {};
  const namespace = target.namespace || 'cluster-scoped';
  const kind = target.kind || 'Resource';
  const name = target.name || candidate.title;
  return `${namespace}/${kind}/${name}`;
};

const actionCandidateDisplayTitle = (candidate: AiopsActionCandidate): string =>
  candidate.title.replace(/\s*조치 후보\s*$/u, '');

const actionCandidateRank = (candidate: AiopsActionCandidate): number =>
  typeof candidate.priority === 'number' ? candidate.priority : 999;

const actionCandidateGroupKey = (candidate: AiopsActionCandidate): string => {
  const target = candidate.target ?? {};
  return [
    textValue(target.namespace, 'cluster-scoped'),
    textValue(target.kind, 'Resource'),
    textValue(target.name, candidate.title),
  ].join('/');
};

const rankActionCandidatesForDisplay = (
  candidates: AiopsActionCandidate[],
): AiopsActionCandidate[] => {
  const ranked = [...candidates].sort(
    (left, right) => actionCandidateRank(left) - actionCandidateRank(right),
  );
  const byTarget = new Map<string, AiopsActionCandidate>();

  ranked.forEach((candidate) => {
    const key = actionCandidateGroupKey(candidate);
    if (!byTarget.has(key)) {
      byTarget.set(key, candidate);
    }
  });

  return [...byTarget.values()];
};

const isImagePullBackOffCandidate = (candidate: AiopsActionCandidate): boolean => {
  const haystack = [
    candidate.title,
    candidate.evidence,
    candidate.statusLabel,
    candidate.recommendationSteps?.join(' '),
    candidate.prerequisiteChecks?.join(' '),
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();
  return haystack.includes('imagepullbackoff') || haystack.includes('image pull');
};

type ActionCandidateNextAction = 'approve-plan' | 'create-plan' | 'done' | 'execute-approval';

export type ActionCandidateLifecycleState = {
  action: ActionCandidateNextAction;
  approvalId?: string;
  disabledReason?: string;
  label: string;
  phaseLabel: string;
  planDigest?: string;
  planId?: string;
  proof: string;
};

const recordName = (record?: AiopsRecord): string => record?.metadata?.name ?? '';

const candidateExecutableTool = (candidate: AiopsActionCandidate): string => {
  const kind = candidate.target?.kind ?? '';
  if (kind === 'Deployment') {
    return 'rollout_restart_deployment';
  }
  if (kind === 'Pod') {
    return 'evict_one_unhealthy_controller_owned_pod';
  }
  return '';
};

const planDigest = (record?: AiopsRecord): string => {
  const sealedActionPlan = asObject(asObject(record?.spec).sealedActionPlan);
  const digest = asObject(sealedActionPlan.digest);
  return textValue(digest.planDigest, '');
};

const approvalDecision = (record?: AiopsRecord): Record<string, unknown> =>
  asObject(asObject(record?.spec).approvalDecision);

const approvalId = (record?: AiopsRecord): string =>
  textValue(approvalDecision(record).approvalId, recordName(record));

const approvalPlanDigest = (record?: AiopsRecord): string =>
  textValue(approvalDecision(record).planDigest, '');

const targetMatchesCandidate = (
  target: Record<string, unknown>,
  candidate: AiopsActionCandidate,
): boolean => {
  const candidateTarget = candidate.target ?? {};
  return (
    textValue(target.kind, '') === textValue(candidateTarget.kind, '') &&
    textValue(target.namespace, '') === textValue(candidateTarget.namespace, '') &&
    textValue(target.name, '') === textValue(candidateTarget.name, '')
  );
};

const actionRecordMatchesCandidate = (
  record: AiopsRecord,
  candidate: AiopsActionCandidate,
): boolean => {
  const toolName = candidateExecutableTool(candidate);
  if (!toolName) {
    return false;
  }

  const spec = asObject(record.spec);
  const proposal = asObject(spec.candidateActionRequest);
  const sealedActionPlan = asObject(spec.sealedActionPlan);
  const action =
    Object.keys(proposal).length > 0
      ? asObject(proposal.action)
      : asObject(sealedActionPlan.action);
  const target =
    Object.keys(proposal).length > 0
      ? asObject(proposal.target)
      : asObject(sealedActionPlan.target);

  return textValue(action.toolName, '') === toolName && targetMatchesCandidate(target, candidate);
};

const actionCandidateLifecycle = (
  candidate: AiopsActionCandidate,
  status: AiopsRuntimeStatus | null,
): ActionCandidateLifecycleState => {
  const toolName = candidateExecutableTool(candidate);
  if (!toolName) {
    return {
      action: 'done',
      disabledReason: '현재 실행 API는 Deployment 재시작과 Pod eviction 후보만 연결되어 있습니다.',
      label: '실행 API 없음',
      phaseLabel: '설계 필요',
      proof: '이 후보는 아직 Gateway action registry에 묶이지 않았습니다.',
    };
  }

  if (
    isImagePullBackOffCandidate(candidate) &&
    toolName === 'evict_one_unhealthy_controller_owned_pod'
  ) {
    return {
      action: 'done',
      disabledReason:
        'ImagePullBackOff는 Pod eviction으로 해결하지 않습니다. 이미지 이름, registry 접근, pull secret을 먼저 확인해야 합니다.',
      label: '실행 보류',
      phaseLabel: '확인 필요',
      proof: '이미지 pull 실패는 eviction 실행 후보에서 제외했습니다.',
    };
  }

  const records = status?.spec.records;
  const plan = (records?.sealedActionPlans ?? []).find((item) =>
    actionRecordMatchesCandidate(item, candidate),
  );
  const digest = planDigest(plan);
  const approval = (records?.approvalDecisions ?? []).find(
    (item) => approvalPlanDigest(item) === digest && approvalDecision(item).status === 'approved',
  );
  const execution = (records?.executionRecords ?? []).find((item) => {
    const spec = asObject(item.spec);
    return (
      textValue(spec.planDigest, '') === digest ||
      (approval ? textValue(spec.approvalId, '') === approvalId(approval) : false)
    );
  });

  if (execution) {
    return {
      action: 'done',
      disabledReason: '이미 실행 기록이 있습니다.',
      label: '완료',
      phaseLabel: '실행 완료',
      proof: `${recordName(execution)} · ${recordPhase(execution)}`,
    };
  }

  if (approval && plan) {
    return {
      action: 'execute-approval',
      approvalId: approvalId(approval),
      label: '실행',
      phaseLabel: '승인 완료',
      planDigest: digest,
      planId: recordName(plan),
      proof: `${approvalId(approval)} · ${compactDigest(digest)}`,
    };
  }

  if (plan) {
    return {
      action: 'approve-plan',
      label: '승인 요청',
      phaseLabel: '승인 대기',
      planDigest: digest,
      planId: recordName(plan),
      proof: `${recordName(plan)} · ${compactDigest(digest)}`,
    };
  }

  return {
    action: 'create-plan',
    label: '해결 계획 만들기',
    phaseLabel: '계획 전',
    proof: `${toolName} · live target 확인 후 계획 생성`,
  };
};

export const OperatorFlowBoard: React.FC<{ data: AiopsDashboardData }> = ({ data }) => {
  const overview = data.overview;
  const status = data.status;
  const summary = data.summary;
  const overviewLoaded = Boolean(data.overview);
  const statusLoaded = Boolean(data.status);
  const anomalies = overview?.spec.anomalies?.spec;
  const actionCandidates = overview?.spec.actionCandidates?.spec;
  const evidenceStatus = status?.spec.safetyContract?.evidenceStatus ?? [];
  const collectedEvidence = evidenceStatus
    .filter((item) => item.status === 'collected')
    .reduce((total, item) => total + item.count, 0);
  const mutationsEnabled = Boolean(status?.spec.capabilities.mutationsEnabled);
  const actionExecutorReady = Boolean(status?.spec.capabilities.actionExecutorConfigured);
  const executionReady = mutationsEnabled && actionExecutorReady;
  const rcaStatus = status?.spec.safetyContract?.rcaContextStatus?.status;
  const rcaStatusLabel =
    rcaStatus === 'ready'
      ? 'RCA 확인 결과 준비됨'
      : rcaStatus === 'missing_question'
        ? '질문 후 RCA 확인 결과 생성'
        : statusLoaded
          ? 'RCA 확인 결과 확인 중'
          : '질문 후 RCA 확인 결과 생성';
  const flowItems = [
    {
      detail: summary ? `${summary.nodes.ready}/${summary.nodes.total} ready` : '상태 수집 중',
      icon: <ServerIcon />,
      label: '클러스터 상태',
      tone: !summary || summary.nodes.notReady ? 'warning' : 'success',
      value: overview
        ? (overview.spec.controlTower.statusLabel ?? '관제 상태 확인 중')
        : '관제 상태 확인 중',
    },
    {
      detail: overviewLoaded && anomalies ? `총 ${anomalies.totals?.total ?? 0}건` : '소스 확인 중',
      icon: <ExclamationTriangleIcon />,
      label: '이상 징후',
      tone: anomalyStatusTone(anomalies?.status),
      value: overviewLoaded ? (anomalies?.statusLabel ?? '이상 징후 확인 중') : '이상 징후 수집 중',
    },
    {
      detail: statusLoaded ? `확인 결과 ${collectedEvidence}건` : '확인 결과 상태 확인 중',
      icon: <ClipboardCheckIcon />,
      label: 'RCA 확인 결과',
      tone: collectedEvidence > 0 ? 'info' : 'warning',
      value: rcaStatusLabel,
    },
    {
      detail: executionReady ? '실행 계획 생성 가능' : '승인 전 분석 단계',
      icon: <BoltIcon />,
      label: '조치 후보',
      tone: actionCandidateTone(
        actionCandidates?.candidates?.[0]?.riskLevel,
        actionCandidates?.status,
      ),
      value: actionCandidates?.statusLabel ?? '조치 후보 확인 중',
    },
    {
      detail: '대화와 감사 기록 보존',
      icon: <HistoryIcon />,
      label: '감사·대화',
      tone: statusLoaded ? 'info' : 'warning',
      value: statusLoaded
        ? `감사 ${status?.spec.records.auditRecords?.length ?? 0}건`
        : '감사 상태 확인 중',
    },
    {
      detail: statusLoaded
        ? executionReady
          ? '승인 실행기 연결'
          : '실행 경로 확인 필요'
        : 'mutation 상태 확인 중',
      icon: <ShieldAltIcon />,
      label: '안전 정책',
      tone: statusLoaded ? (executionReady ? 'info' : 'warning') : 'warning',
      value: statusLoaded
        ? runtimeModeLabel(status?.spec.safetyContract?.mode)
        : '안전 정책 확인 중',
    },
  ] as const;

  return (
    <section className="komsco-ai-page__operator-flow" aria-label="AIOps operator flow">
      <div className="komsco-ai-page__operator-flow-head">
        <span className="komsco-ai-page__section-kicker">Operator flow</span>
        <h2>운영 흐름</h2>
      </div>
      <div className="komsco-ai-page__operator-flow-grid">
        {flowItems.map((item) => (
          <div className={`komsco-ai-page__operator-flow-item is-${item.tone}`} key={item.label}>
            <span className="komsco-ai-page__operator-flow-icon">{item.icon}</span>
            <span className="komsco-ai-page__operator-flow-label">{item.label}</span>
            <strong>{item.value}</strong>
            <small>{item.detail}</small>
          </div>
        ))}
      </div>
    </section>
  );
};

const findingTargetParts = (
  finding: AiopsAnomalyFinding,
): { kind: string; name: string; namespace: string } => {
  const resource = finding.resource ?? {};
  return {
    kind: resource.kind || finding.category || 'Resource',
    name: resource.name || finding.title,
    namespace: finding.namespace || resource.namespace || 'cluster-scoped',
  };
};

const normalizeFindingDisplayText = (text: string, finding: AiopsAnomalyFinding): string => {
  const target = findingTargetParts(finding);
  return text
    .replace(/increase\(\[redacted-token\]\[1h\]\)=([^,\s]+)/g, '최근 1시간 재시작 증가=$1')
    .replace(/\[redacted-token\]/g, target.name || '대상 리소스');
};

const isCrashLoopFinding = (finding: AiopsAnomalyFinding): boolean => {
  const haystack = [
    finding.type,
    finding.reason,
    finding.title,
    finding.message,
    finding.evidence,
    finding.statusLabel,
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();

  return haystack.includes('crashloop') || finding.type === 'pod_crashloop';
};

export const actionCandidateMatchesFinding = (
  candidate: AiopsActionCandidate,
  finding: AiopsAnomalyFinding,
): boolean => {
  if (candidate.sourceFindingId && candidate.sourceFindingId === finding.id) {
    return true;
  }

  const target = candidate.target ?? {};
  const findingTarget = findingTargetParts(finding);
  return (
    target.namespace === findingTarget.namespace &&
    target.name === findingTarget.name &&
    (!target.kind || !findingTarget.kind || target.kind === findingTarget.kind)
  );
};

const findingEvidenceText = (finding: AiopsAnomalyFinding, fallback = '확인 결과 수집 중'): string =>
  normalizeFindingDisplayText(
    safeEvidenceText(finding.evidence || finding.message, fallback),
    finding,
  );

const findingNextCheckText = (
  finding: AiopsAnomalyFinding,
  fallback = '관련 Pod 상태, 이벤트, 로그 가능 여부 확인',
): string => normalizeFindingDisplayText(safeEvidenceText(finding.nextCheck, fallback), finding);

const buildFindingDemoPrompt = (
  finding: AiopsAnomalyFinding,
  candidate?: AiopsActionCandidate,
): string => {
  const target = anomalyResourceLabel(finding);
  const candidateLine = candidate
    ? `연결된 조치 후보: ${candidate.title} / ${candidate.statusLabel || '승인 전 확인 필요'}`
    : '연결된 조치 후보: 아직 특정 후보와 강하게 묶이지 않았으니 확인 필요로 표시';

  return [
    '다음 OpenShift 이상 징후를 RCA 분석하고, 승인 필요한 조치 후보까지 정리해줘.',
    '',
    `시나리오: CrashLoopBackOff 원인 분석`,
    `findingId: ${finding.id}`,
    `대상: ${target}`,
    `심각도: ${finding.severity}`,
    `원인 후보: ${finding.candidateCause || finding.reason || '추가 확인 필요'}`,
    `현재 확인 결과: ${findingEvidenceText(finding)}`,
    `다음 확인: ${findingNextCheckText(finding)}`,
    candidateLine,
    '',
    '답변 형식:',
    '1. 확인 결과',
    '2. 가능한 원인 후보',
    '3. 추가 확인 필요 항목',
    '4. 먼저 확인할 조회 항목과 순서',
    '5. 실행 계획이 필요하면 승인 조건과 되돌림 기준',
    '',
    '주의: 로그 원문은 민감정보 가능성이 있으니 원문 노출 없이 필요 여부와 확인 방법만 정리해줘. 실제 변경은 계획, 승인, 검증 조건을 거쳐야 한다.',
  ].join('\n');
};

export const buildFindingDemoDraft = (
  finding: AiopsAnomalyFinding,
  candidate?: AiopsActionCandidate,
): AssistantDraftPromptRequest => {
  const target = findingTargetParts(finding);
  return {
    id: `${finding.id}-${Date.now()}`,
    pageContext: {
      candidateId: candidate?.id,
      candidateStatusLabel: candidate?.statusLabel,
      findingId: finding.id,
      findingTitle: finding.title,
      scenarioId: isCrashLoopFinding(finding) ? 'crashloop' : finding.type,
      selectedAt: new Date().toISOString(),
      source: 'aiops-dashboard-anomaly-board',
      target,
    },
    prompt: buildFindingDemoPrompt(finding, candidate),
    taskMode: 'troubleshooting',
  };
};

export const buildActionCandidatePrompt = (
  candidate: AiopsActionCandidate,
): AssistantDraftPromptRequest => {
  const target = candidate.target ?? {};
  const kind = target.kind || 'Deployment';
  const namespace = target.namespace || '';
  const name = target.name || '';
  const targetLabel = actionCandidateTargetLabel(candidate);
  const command =
    kind.toLowerCase() === 'pod'
      ? `Pod \`${namespace}/${name}\` evict 실행 계획을 생성해줘.`
      : `Deployment \`${namespace}/${name}\` rollout restart 실행 계획을 생성해줘.`;

  return {
    id: `${candidate.id}-${Date.now()}`,
    pageContext: {
      aiopsExecutionMode: 'execute',
      candidateId: candidate.id,
      candidateStatusLabel: candidate.statusLabel,
      selectedAt: new Date().toISOString(),
      source: 'aiops-dashboard-action-candidate-board',
      target,
    },
    prompt: [
      command,
      '',
      `조치 후보: ${candidate.title}`,
      `대상: ${targetLabel}`,
      `위험도: ${candidate.riskLabel || candidate.riskLevel || '확인 필요'}`,
      `확인 결과: ${candidate.evidence || '확인 결과 필요'}`,
      `선행 확인: ${candidate.prerequisiteChecks?.[0] || '대상 리소스 상태 확인'}`,
      `예상 영향: ${candidate.expectedImpact || '영향 범위 확인 필요'}`,
      '',
      '실행은 바로 하지 말고, 먼저 Action Plan을 만들고 승인 버튼을 기다려.',
    ].join('\n'),
    taskMode: 'troubleshooting',
  };
};

export const AnomalySummaryBoard: React.FC<{
  activeFindingId?: string;
  onAnalyzeFinding?: (finding: AiopsAnomalyFinding) => void;
  overview: AiopsOverview | null;
}> = ({ activeFindingId, onAnalyzeFinding, overview }) => {
  const anomalies = overview?.spec.anomalies?.spec;
  const status = anomalies?.status ?? (overview ? 'unknown' : 'loading');
  const tone = anomalyStatusTone(status);
  const findings = anomalies?.findings ?? [];
  const topFindings = findings.slice(0, 3);
  const totals = anomalies?.totals ?? {};
  const dataSources = anomalies?.dataSources ?? [];
  const failedSources = dataSources.filter((source) => source.status !== 'available');
  const normalSignals = anomalies?.normalSignals ?? [];
  const sourceText =
    dataSources.length > 0
      ? `소스 ${dataSources.filter((source) => source.status === 'available').length}/${dataSources.length}`
      : '소스 확인 중';

  if (!overview) {
    return (
      <section
        className="komsco-ai-page__anomaly-board is-warning"
        aria-label="Cywell AI anomaly summary"
      >
        <div className="komsco-ai-page__anomaly-head">
          <div>
            <span>Cywell AI 이상 징후</span>
            <strong>overview 수집 중</strong>
          </div>
          <code>조회 중</code>
        </div>
        <p>회사 OCP의 Alert, Pod, Operator, Event, 재시작 지표를 읽는 중입니다.</p>
      </section>
    );
  }

  return (
    <section
      className={`komsco-ai-page__anomaly-board is-${tone}`}
      aria-label="Cywell AI anomaly summary"
      data-anomaly-status={status}
      data-anomaly-total={totals.total ?? 0}
    >
      <div className="komsco-ai-page__anomaly-head">
        <div>
          <span>Cywell AI 이상 징후 자동 정리</span>
          <strong>{anomalies?.statusLabel ?? '이상 징후 상태 확인 중'}</strong>
        </div>
        <div className="komsco-ai-page__anomaly-badges">
          <code>{sourceText}</code>
          <code>{runtimeModeLabel(overview.spec.anomalies?.spec?.safety?.mode ?? '분석')}</code>
        </div>
      </div>

      <div className="komsco-ai-page__anomaly-totals" aria-label="Anomaly severity totals">
        <span className="is-danger">위험 {totals.danger ?? 0}</span>
        <span className="is-warning">확인 필요 {totals.attention ?? 0}</span>
        <span>주의 {totals.warning ?? 0}</span>
        <span>총 {totals.total ?? findings.length}</span>
      </div>

      {topFindings.length > 0 ? (
        <div
          className="komsco-ai-page__anomaly-list"
          data-visible-anomaly-count={topFindings.length}
        >
          {topFindings.map((finding) => {
            const findingTone = anomalySeverityTone(finding.severity);
            const crashLoopDemo = isCrashLoopFinding(finding);
            const active = activeFindingId === finding.id;
            return (
              <article
                className={`komsco-ai-page__anomaly-item is-${findingTone}${active ? ' is-active-demo' : ''}`}
                data-aiops-finding-id={finding.id}
                data-aiops-scenario={crashLoopDemo ? 'crashloop' : finding.type}
                key={finding.id}
              >
                <div className="komsco-ai-page__anomaly-item-head">
                  <span>{finding.severity}</span>
                  <strong>{finding.title}</strong>
                  <code>P{finding.priority}</code>
                </div>
                <dl>
                  <dt>대상</dt>
                  <dd>{anomalyResourceLabel(finding)}</dd>
                  <dt>원인 후보</dt>
                  <dd>{finding.candidateCause || finding.reason || '추가 확인 필요'}</dd>
                  <dt>확인 결과</dt>
                  <dd>{findingEvidenceText(finding)}</dd>
                  <dt>다음 확인</dt>
                  <dd>{findingNextCheckText(finding, '관련 리소스 상태와 이벤트 확인')}</dd>
                </dl>
                <div className="komsco-ai-page__anomaly-actions">
                  {crashLoopDemo && <span className="komsco-ai-page__demo-badge">0.1.3 demo</span>}
                  {active && (
                    <span className="komsco-ai-page__demo-badge is-active">질문에 연결됨</span>
                  )}
                  {crashLoopDemo && (
                    <Button
                      data-aiops-demo-action="seed-chat-prompt"
                      isInline
                      onClick={() => onAnalyzeFinding?.(finding)}
                      variant="link"
                    >
                      챗봇으로 RCA 질문 생성
                    </Button>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <div className="komsco-ai-page__anomaly-normal" data-visible-anomaly-count="0">
          {status === 'normal' ? <CheckCircleIcon /> : <ExclamationTriangleIcon />}
          <div>
            <strong>
              {status === 'normal'
                ? '현재 수집 범위에서 주요 이상 징후 없음'
                : '아직 정상으로 단정할 수 없음'}
            </strong>
            <span>
              {(failedSources.length > 0
                ? failedSources.map((source) => `${source.label}: ${source.status}`).join(' / ')
                : normalSignals.join(' / ')) || '데이터 소스 상태 확인 중'}
            </span>
          </div>
        </div>
      )}
    </section>
  );
};

export const ActionCandidateBoard: React.FC<{
  activeCandidateId?: string;
  actionBusyId?: string;
  actionError?: string;
  actionNotice?: string;
  onCandidateAction?: (
    candidate: AiopsActionCandidate,
    lifecycle: ActionCandidateLifecycleState,
  ) => void;
  onPlanCandidate?: (candidate: AiopsActionCandidate) => void;
  overview: AiopsOverview | null;
  status: AiopsRuntimeStatus | null;
}> = ({
  activeCandidateId,
  actionBusyId = '',
  actionError = '',
  actionNotice = '',
  onCandidateAction,
  onPlanCandidate,
  overview,
  status: runtimeStatus,
}) => {
  const actionCandidates = overview?.spec.actionCandidates?.spec;
  const candidates = actionCandidates?.candidates ?? [];
  const rankedCandidates = rankActionCandidatesForDisplay(candidates);
  const visibleCandidates = rankedCandidates.slice(0, ACTION_CANDIDATE_DISPLAY_LIMIT);
  const collapsedDuplicateCount = Math.max(0, candidates.length - rankedCandidates.length);
  const hiddenCandidateCount = Math.max(0, rankedCandidates.length - visibleCandidates.length);
  const totals = actionCandidates?.totals ?? {};
  const candidateStatus = actionCandidates?.status ?? (overview ? 'unknown' : 'loading');
  const tone = actionCandidateTone(visibleCandidates[0]?.riskLevel, candidateStatus);
  const executionReady = Boolean(
    runtimeStatus?.spec.capabilities.mutationsEnabled &&
    runtimeStatus.spec.capabilities.actionExecutorConfigured,
  );
  const forbiddenVerbs = actionCandidates?.safety?.forbiddenMutationVerbs ?? [
    'apply',
    'delete',
    'patch',
    'scale',
    'exec',
  ];
  const mode = actionCandidates?.safety?.mode ?? (executionReady ? 'controlled_execution' : '분석');
  const modeLabel = runtimeModeLabel(mode);

  if (!overview) {
    return (
      <section
        className="komsco-ai-page__action-candidate-board is-warning"
        aria-label="AIOps action candidates"
      >
        <div className="komsco-ai-page__action-candidate-head">
          <div>
            <span>AIOps 조치 후보</span>
            <strong>overview 수집 중</strong>
          </div>
          <code>상태 확인 중</code>
        </div>
        <p>이상 징후를 읽은 뒤 운영자가 검토할 상위 조치 후보를 정리합니다.</p>
      </section>
    );
  }

  return (
    <section
      className={`komsco-ai-page__action-candidate-board is-${tone}`}
      aria-label="AIOps action candidates"
      data-action-candidate-status={candidateStatus}
      data-action-candidate-total={totals.total ?? candidates.length}
      data-action-candidate-execution={executionReady ? 'approval-gated' : 'not-ready'}
      data-action-candidate-mode={mode}
    >
      <div className="komsco-ai-page__action-candidate-head">
        <div>
          <span>Cywell AI 조치 후보</span>
          <strong>
            {visibleCandidates.length > 0
              ? `상위 조치 후보 ${visibleCandidates.length}건`
              : (actionCandidates?.statusLabel ?? '조치 후보 상태 확인 중')}
          </strong>
        </div>
        <div className="komsco-ai-page__action-candidate-badges">
          <code>{executionReady ? '승인 실행 연결' : '분석 후보'}</code>
          <code>{modeLabel}</code>
          <code>전체 후보 {totals.total ?? candidates.length}건</code>
        </div>
      </div>

      <div className="komsco-ai-page__action-candidate-policy">
        <ShieldAltIcon />
        <span>
          {executionReady
            ? '상위 후보만 먼저 보여주고, 계획 생성/승인/실행은 단계별 기록으로 남깁니다.'
            : `실행 경로 확인 전입니다. 차단 동작: ${forbiddenVerbs.join(', ')}`}
        </span>
      </div>
      {(collapsedDuplicateCount > 0 || hiddenCandidateCount > 0) && (
        <div className="komsco-ai-page__action-candidate-note">
          중복 후보 {collapsedDuplicateCount}건
          {hiddenCandidateCount > 0 ? `, 낮은 우선순위 후보 ${hiddenCandidateCount}건` : ''}은 기본
          화면에서 접었습니다.
        </div>
      )}
      {actionError && (
        <div className="komsco-ai-page__action-candidate-feedback is-error">{actionError}</div>
      )}
      {actionNotice && (
        <div className="komsco-ai-page__action-candidate-feedback is-success">{actionNotice}</div>
      )}

      {visibleCandidates.length > 0 ? (
        <div
          className="komsco-ai-page__action-candidate-list"
          data-visible-action-candidate-count={visibleCandidates.length}
        >
          {visibleCandidates.map((candidate) => {
            const lifecycle = actionCandidateLifecycle(candidate, runtimeStatus);
            const actionKey = `${lifecycle.action}:${candidate.id}`;
            const busy = actionBusyId === actionKey;
            const active = activeCandidateId === candidate.id;
            return (
              <article
                className={`komsco-ai-page__action-candidate${active ? ' is-active-demo' : ''}`}
                key={candidate.id}
              >
                <div className="komsco-ai-page__action-candidate-title">
                  <span>{candidate.riskLabel || candidate.riskLevel || '위험도 확인'}</span>
                  <strong>{actionCandidateDisplayTitle(candidate)}</strong>
                  <code>P{candidate.priority ?? '-'}</code>
                </div>
                <dl>
                  <dt>대상</dt>
                  <dd>{actionCandidateTargetLabel(candidate)}</dd>
                  <dt>상태</dt>
                  <dd>{lifecycle.phaseLabel}</dd>
                  <dt>조치 방향</dt>
                  <dd>{candidate.recommendationSteps?.[0] || '확인 결과 검토 후 승인 계획 생성'}</dd>
                  <dt>선행 확인</dt>
                  <dd>{candidate.prerequisiteChecks?.[0] || '관련 리소스 상태와 이벤트 확인'}</dd>
                  <dt>예상 영향</dt>
                  <dd>{candidate.expectedImpact || '승인 전 영향 범위 확인 필요'}</dd>
                  <dt>실행 조건</dt>
                  <dd>
                    {candidate.approvalRequired ? '승인 전 실행 불가' : '승인 정책 확인 필요'}
                  </dd>
                  <dt>검증</dt>
                  <dd>{candidate.verificationChecks?.[0] || '조치 후 상태 재확인 필요'}</dd>
                  <dt>현재 단계</dt>
                  <dd>{lifecycle.proof}</dd>
                </dl>
                <div className="komsco-ai-page__anomaly-actions">
                  {active && (
                    <span className="komsco-ai-page__demo-badge is-active">질문에 연결됨</span>
                  )}
                  <Button
                    isDisabled={busy || Boolean(lifecycle.disabledReason)}
                    isLoading={busy}
                    onClick={() => onCandidateAction?.(candidate, lifecycle)}
                    title={
                      lifecycle.disabledReason || 'Gateway 실행 흐름에서 다음 단계를 진행합니다.'
                    }
                    variant={lifecycle.action === 'execute-approval' ? 'danger' : 'primary'}
                  >
                    {lifecycle.label}
                  </Button>
                  <Button
                    isInline
                    onClick={() => onPlanCandidate?.(candidate)}
                    title="이 후보를 챗봇 질문으로 보내 확인 결과 설명을 다시 확인합니다."
                    variant="link"
                  >
                    확인 결과 다시 묻기
                  </Button>
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <div
          className="komsco-ai-page__action-candidate-empty"
          data-visible-action-candidate-count="0"
        >
          <CheckCircleIcon />
          <div>
            <strong>
              {candidateStatus === 'normal'
                ? '현재 제안할 조치 후보 없음'
                : '조치 후보를 만들 만큼 확인 결과가 충분하지 않음'}
            </strong>
            <span>
              {actionCandidates?.statusLabel ??
                '이상 징후 데이터와 필수 소스 상태를 먼저 확인합니다.'}
            </span>
          </div>
        </div>
      )}
    </section>
  );
};
