import type { ToolPlanFooter, ToolPlanMissingEvidence, ToolPlanStep } from './assistant.types';
import type { UiLanguage } from './assistant.types';
import { redactSensitiveText } from '../utils/evidenceDisplay';

export const buildToolPlanFooter = (raw: unknown): ToolPlanFooter | undefined => {
  if (!raw || typeof raw !== 'object') {
    return undefined;
  }

  const plan = raw as Record<string, unknown>;
  const target = (plan.target && typeof plan.target === 'object' ? plan.target : {}) as Record<
    string,
    unknown
  >;
  const executionPolicy = (
    plan.execution_policy && typeof plan.execution_policy === 'object' ? plan.execution_policy : {}
  ) as Record<string, unknown>;
  const metadata = (plan.metadata && typeof plan.metadata === 'object' ? plan.metadata : {}) as Record<
    string,
    unknown
  >;
  const validation = (
    plan.validation && typeof plan.validation === 'object' ? plan.validation : {}
  ) as Record<string, unknown>;

  const isRecord = (value: unknown): value is Record<string, unknown> =>
    Boolean(value) && typeof value === 'object';

  const rawSteps = Array.isArray(plan.tool_plan) ? plan.tool_plan.filter(isRecord) : [];
  const steps: ToolPlanStep[] = rawSteps.map((step) => {
    const stepId =
      typeof step.step === 'number' || typeof step.step === 'string' ? step.step : undefined;
    return {
      adapter: typeof step.adapter === 'string' ? step.adapter : undefined,
      evidenceType: typeof step.evidence_type === 'string' ? step.evidence_type : undefined,
      reason: typeof step.reason === 'string' ? step.reason : undefined,
      step: stepId,
      tool: typeof step.tool === 'string' ? step.tool : undefined,
      verb: typeof step.verb === 'string' ? step.verb : undefined,
    };
  });

  const rawMissing = Array.isArray(plan.missing_evidence)
    ? plan.missing_evidence.filter(isRecord)
    : [];
  const missingEvidence: ToolPlanMissingEvidence[] = rawMissing.map((item) => ({
    reason: typeof item.reason === 'string' ? item.reason : undefined,
    type: typeof item.type === 'string' ? item.type : undefined,
  }));

  if (steps.length === 0) {
    return undefined;
  }

  return {
    executionPolicyMode:
      typeof executionPolicy.mode === 'string' ? executionPolicy.mode : undefined,
    missingEvidence,
    plannerSource: typeof metadata.planner === 'string' ? metadata.planner : undefined,
    rawPlanJson: redactSensitiveText(JSON.stringify(plan, null, 2), '{}'),
    steps,
    targetNamespace: typeof target.namespace === 'string' ? target.namespace : undefined,
    targetResourceKind: typeof target.resourceKind === 'string' ? target.resourceKind : undefined,
    targetResourceName: typeof target.resourceName === 'string' ? target.resourceName : undefined,
    taskType: typeof plan.task_type === 'string' ? plan.task_type : undefined,
    validationOk: typeof validation.ok === 'boolean' ? validation.ok : undefined,
    validationViolations: Array.isArray(validation.violations)
      ? validation.violations.filter((item): item is string => typeof item === 'string')
      : [],
  };
};

export const isReadOnlyExecutionPolicy = (mode?: string): boolean => mode === 'evidence_check';

export const executionPolicyLabel = (mode?: string, language: UiLanguage = 'ko'): string => {
  const isKo = language === 'ko';
  if (mode === 'evidence_check') {
    return isKo ? '읽기 전용' : 'Read-only';
  }
  if (mode === 'unrestricted') {
    return isKo ? '실행 무제한' : 'Unrestricted execution';
  }
  if (mode === 'controlled_execution') {
    return isKo ? '승인 후 실행' : 'Approval-gated execution';
  }
  return mode || (isKo ? '알 수 없음' : 'Unknown');
};

export const toolPlanPlannerLabel = (source?: string, language: UiLanguage = 'ko'): string => {
  const isKo = language === 'ko';
  if (source === 'deterministic_gateway_planner') {
    return isKo ? 'Gateway 안전 플래너' : 'Gateway safety planner';
  }
  if (source === 'model_generated') {
    return isKo ? 'AIOps 모델 플래너' : 'AIOps model planner';
  }
  return source ? source.replace(/[_-]+/g, ' ') : isKo ? 'Tool Plan 플래너' : 'Tool Plan planner';
};

export const toolPlanPlannerSummary = (
  source?: string,
  language: UiLanguage = 'ko',
): string => {
  const isKo = language === 'ko';
  if (source === 'deterministic_gateway_planner' || !source) {
    return isKo
      ? 'Gateway가 정책과 조회 계약으로 만든 결정형 조회 계획입니다.'
      : 'Deterministic query plan created by the Gateway policy and evidence contract.';
  }
  if (source === 'model_generated') {
    return isKo
      ? '모델이 제안한 계획이며 Gateway 검증을 통과한 항목만 표시합니다.'
      : 'Model-proposed plan; only Gateway-validated steps are shown.';
  }
  return isKo
    ? 'Gateway 검증을 거친 조회 계획입니다.'
    : 'Query plan validated by the Gateway.';
};
