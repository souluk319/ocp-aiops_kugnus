import type { AiopsRuntimeStatus, EvidenceStatusItem } from '../services/aiGateway';
import { evidenceCount, safeEvidenceText } from '../utils/evidenceDisplay';
import type {
  EvidenceFooter,
  EvidenceFooterMissing,
  EvidenceFooterQueryStep,
  EvidenceFooterRef,
} from './assistant.types';

const asRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};

const asRecordArray = (value: unknown): Record<string, unknown>[] =>
  Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> =>
        Boolean(item && typeof item === 'object' && !Array.isArray(item)),
      )
    : [];

const normalizeEvidenceRef = (value: Record<string, unknown>): EvidenceFooterRef => ({
  contentDigest: safeEvidenceText(value.contentDigest),
  evidenceId: safeEvidenceText(value.evidenceId),
  sourceType: safeEvidenceText(value.sourceType),
  status: safeEvidenceText(value.status),
  summary: safeEvidenceText(value.summary || value.eventName || 'evidence'),
  type: safeEvidenceText(value.type, 'evidence'),
});

const normalizeMissingEvidence = (value: Record<string, unknown>): EvidenceFooterMissing => ({
  contentDigest: safeEvidenceText(value.contentDigest),
  evidenceId: safeEvidenceText(value.evidenceId),
  reason: safeEvidenceText(value.reason || 'additional evidence required'),
  type: safeEvidenceText(value.type, 'evidence'),
});

const normalizeEvidenceQueryStep = (
  value: Record<string, unknown>,
): EvidenceFooterQueryStep => ({
  adapter: safeEvidenceText(value.adapter),
  evidenceType: safeEvidenceText(value.evidenceType || value.evidence_type, 'evidence'),
  reason: safeEvidenceText(value.reason || '근거 수집 단계'),
  status: safeEvidenceText(value.status || 'planned'),
  step: safeEvidenceText(value.step),
  tool: safeEvidenceText(value.tool || value.official_tool, 'tool'),
});

const evidenceStatusCounts = (items: EvidenceStatusItem[] | undefined) => ({
  collected: (items ?? [])
    .filter((item) => item.status === 'collected')
    .reduce((total, item) => total + item.count, 0),
  missing: (items ?? [])
    .filter((item) => item.status === 'missing')
    .reduce((total, item) => total + Math.max(item.count, 1), 0),
});

export const buildEvidenceFooter = (
  context: unknown,
  evidenceStatus?: EvidenceStatusItem[],
  status?: string,
): EvidenceFooter | undefined => {
  const contextRecord = asRecord(context);
  if (Object.keys(contextRecord).length === 0) {
    return undefined;
  }

  const metadata = asRecord(contextRecord.metadata);
  const evidence = asRecord(contextRecord.evidence);
  const summary = asRecord(evidence.summary);
  const analysisPlan = asRecord(contextRecord.analysisPlan);
  const answerExperience = asRecord(contextRecord.answerExperience);
  const collectedRefs = asRecordArray(evidence.collectedRefs).map(normalizeEvidenceRef);
  const failedRefs = asRecordArray(evidence.failedRefs).map(normalizeEvidenceRef);
  const missing = asRecordArray(evidence.missing).map(normalizeMissingEvidence);
  const queryPlanSource = asRecordArray(answerExperience.queryPlan).length
    ? asRecordArray(answerExperience.queryPlan)
    : asRecordArray(analysisPlan.queryPlan).length
      ? asRecordArray(analysisPlan.queryPlan)
      : asRecordArray(analysisPlan.evidenceCollectionSteps);
  const queryPlan = queryPlanSource.map(normalizeEvidenceQueryStep);
  const statusCounts = evidenceStatusCounts(evidenceStatus);

  return {
    collectedCount: evidenceCount(
      summary.collectedCount,
      statusCounts.collected,
      collectedRefs.length,
    ),
    collectedRefs,
    contextId: safeEvidenceText(metadata.contextId),
    digest: safeEvidenceText(metadata.digest),
    failedCount: evidenceCount(summary.failedCount, 0, failedRefs.length),
    failedRefs,
    missing,
    missingCount: evidenceCount(summary.missingCount, statusCounts.missing, missing.length),
    phase: safeEvidenceText(metadata.phase),
    queryPlan,
    status: safeEvidenceText(status),
  };
};

export const buildEvidenceCopyText = (footer: EvidenceFooter | undefined): string => {
  if (!footer) {
    return '';
  }

  const lines = [
    '',
    '[근거 요약]',
    `- 수집 근거: ${footer.collectedCount}건`,
    `- 추가 확인: ${footer.missingCount}건`,
  ];

  footer.collectedRefs.slice(0, 3).forEach((ref) => {
    lines.push(`- ${evidenceTypeLabel(ref.type)}: ${ref.summary || '근거 수집 완료'}`);
  });

  footer.queryPlan.slice(0, 5).forEach((step) => {
    lines.push(
      `- 조회 계획: ${evidenceTypeLabel(step.evidenceType || step.tool)} ${step.reason || '근거 수집 단계'}`,
    );
  });

  return lines.join('\n');
};

export const rcaRailEvidenceCounts = (status: AiopsRuntimeStatus | null | undefined) => {
  const safetyContract = status?.spec.safetyContract;
  const statusCounts = evidenceStatusCounts(safetyContract?.evidenceStatus);
  const contextRecord = asRecord(safetyContract?.rcaContextStatus?.latestContext);
  const evidence = asRecord(contextRecord.evidence);
  const summary = asRecord(evidence.summary);
  const collectedRefs = asRecordArray(evidence.collectedRefs);
  const missing = asRecordArray(evidence.missing);

  return {
    collected: Math.max(
      statusCounts.collected,
      evidenceCount(summary.collectedCount, statusCounts.collected, collectedRefs.length),
    ),
    missing: Math.max(
      statusCounts.missing,
      evidenceCount(summary.missingCount, statusCounts.missing, missing.length),
    ),
  };
};

export const evidenceTypeLabel = (type?: string): string => {
  const normalized = String(type || '')
    .trim()
    .toLowerCase();
  if (normalized === 'node') {
    return '노드';
  }
  if (normalized === 'alert') {
    return '경고';
  }
  if (normalized === 'metric') {
    return '메트릭';
  }
  if (normalized === 'pod_status' || normalized === 'pod') {
    return 'Pod';
  }
  if (normalized === 'snapshot') {
    return '스냅샷';
  }
  if (normalized === 'event') {
    return '이벤트';
  }
  if (normalized === 'runbook') {
    return '런북';
  }
  if (normalized === 'openshift_api') {
    return 'OpenShift API';
  }
  if (normalized === 'openshift') {
    return 'OpenShift';
  }
  if (!normalized) {
    return '근거';
  }
  return type || '근거';
};

export const evidenceStepStatusLabel = (status?: string): string => {
  const normalized = String(status || '')
    .trim()
    .toLowerCase();
  if (normalized === 'collected' || normalized === 'success' || normalized === 'succeeded') {
    return '수집됨';
  }
  if (normalized === 'not_attempted' || normalized === 'planned' || normalized === 'pending') {
    return '대기';
  }
  if (normalized === 'failed' || normalized === 'error') {
    return '확인 필요';
  }
  return status || '대기';
};

export const rcaStatusLabel = (status?: string): string => {
  const normalized = String(status || '')
    .trim()
    .toLowerCase();
  if (normalized === 'available' || normalized === 'success' || normalized === 'ready') {
    return '연결됨';
  }
  if (normalized === 'failed' || normalized === 'error') {
    return '확인 필요';
  }
  return status || '대기';
};

export const compactEvidenceTypeSummary = (refs: EvidenceFooterRef[]): string => {
  const labels = [...new Set(refs.map((ref) => evidenceTypeLabel(ref.type)).filter(Boolean))];
  if (labels.length === 0) {
    return '수집 근거 없음';
  }

  return labels.slice(0, 4).join(', ');
};
