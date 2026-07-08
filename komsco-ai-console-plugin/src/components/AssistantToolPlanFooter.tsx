import * as React from 'react';

import { CoolCopyIcon } from './coolicons';
import { evidenceTypeLabel } from './assistant.evidence';
import {
  executionPolicyLabel,
  isReadOnlyExecutionPolicy,
  toolPlanPlannerLabel,
  toolPlanPlannerSummary,
} from './assistant.toolPlan';
import type { AiopsExecutionMode, ToolPlanFooter, UiLanguage } from './assistant.types';

type AssistantToolPlanFooterProps = {
  executionMode: AiopsExecutionMode;
  language: UiLanguage;
  toolPlan?: ToolPlanFooter;
};

const translateToolPlanText = (value: string | undefined, language: UiLanguage): string | undefined => {
  if (!value || language === 'ko') {
    return value;
  }

  const exact: Record<string, string> = {
    '승인 또는 실행 전에 기존 proposal/sealed plan 존재 여부 확인':
      'Check whether an existing proposal or sealed plan exists before approval or execution',
    'evidence-check 기본 정책과 mutation gate 상태 확인':
      'Check the default evidence policy and mutation gate state',
    '추가 확인 필요':
      'Needs more evidence',
    '조회 단계':
      'Query step',
    '계획 검증 실패':
      'Plan validation failed',
  };
  if (exact[value]) {
    return exact[value];
  }

  return value
    .replace(/승인/g, 'approval')
    .replace(/실행/g, 'execution')
    .replace(/기존/g, 'existing')
    .replace(/존재 여부 확인/g, 'existence check')
    .replace(/상태 확인/g, 'state check')
    .replace(/추가 확인/g, 'follow-up check');
};

const AssistantToolPlanFooter: React.FC<AssistantToolPlanFooterProps> = ({
  executionMode,
  language,
  toolPlan,
}) => {
  if (!toolPlan || toolPlan.steps.length === 0) {
    return null;
  }

  const isKo = language === 'ko';
  const steps = toolPlan.steps.slice(0, 6);
  const missingEvidence = toolPlan.missingEvidence.slice(0, 3);
  const readOnly = isReadOnlyExecutionPolicy(toolPlan.executionPolicyMode);
  const showExecutionPolicy = !readOnly || executionMode === 'read-only';
  const targetLabel = [toolPlan.targetResourceKind, toolPlan.targetResourceName]
    .filter(Boolean)
    .join(' ');
  const head = (
    <span className="komsco-ai__toolplan-footer-head">
      <span className="komsco-ai__evidence-title">{isKo ? '조회 계획' : 'Query plan'}</span>
      <span className="komsco-ai__evidence-pill komsco-ai__evidence-pill--collected">
        {toolPlan.taskType}
      </span>
      {showExecutionPolicy && (
        <span
          className={`komsco-ai__evidence-pill ${
            readOnly
              ? 'komsco-ai__evidence-pill--collected'
              : 'komsco-ai__evidence-pill--policy-warning'
          }`}
        >
          {executionPolicyLabel(toolPlan.executionPolicyMode, language)}
        </span>
      )}
      {toolPlan.validationOk === false && (
        <span className="komsco-ai__evidence-pill komsco-ai__evidence-pill--missing">
          {isKo ? '계획 검증 실패' : 'Plan validation failed'}
        </span>
      )}
    </span>
  );

  return (
    <div className="komsco-ai__toolplan-footer">
      <details className="komsco-ai__evidence-detail komsco-ai__evidence-detail--inline">
        <summary className="komsco-ai__footer-inline-summary">
          {head}
          <span className="komsco-ai__footer-detail-toggle">
            {isKo ? '상세' : 'Details'}
          </span>
        </summary>
        <div className="komsco-ai__toolplan-source">
          <strong>
            {toolPlan.plannerLabel || toolPlanPlannerLabel(toolPlan.plannerSource, language)}
          </strong>
          <span>
            {toolPlan.plannerSummary || toolPlanPlannerSummary(toolPlan.plannerSource, language)}
          </span>
        </div>
        {targetLabel && (
          <div className="komsco-ai__toolplan-target">
            {isKo ? '대상' : 'Target'}: {targetLabel}
            {toolPlan.targetNamespace ? ` (${toolPlan.targetNamespace})` : ''}
          </div>
        )}
        <ol
          className="komsco-ai__evidence-query-plan"
          aria-label={isKo ? '조회 계획 단계' : 'Query plan steps'}
        >
          {steps.map((step, index) => (
            <li key={`${step.step || index}-${step.tool || 'tool'}`}>
              <strong>{evidenceTypeLabel(step.evidenceType || step.tool, language)}</strong>
              <span>
                {translateToolPlanText(step.reason, language) || (isKo ? '조회 단계' : 'Query step')}
              </span>
              <code>{step.verb || step.tool}</code>
            </li>
          ))}
        </ol>
        {missingEvidence.length > 0 && (
          <div
            className="komsco-ai__evidence-missing"
            aria-label={isKo ? '추가 확인 필요 항목' : 'Evidence still needed'}
          >
            {missingEvidence.map((item, index) => (
              <span key={`${item.type || 'missing'}-${index}`}>
                {evidenceTypeLabel(item.type, language)}:{' '}
                {translateToolPlanText(item.reason, language) ||
                  (isKo ? '추가 확인 필요' : 'Needs more evidence')}
              </span>
            ))}
          </div>
        )}
        {toolPlan.validationViolations.length > 0 && (
          <div
            className="komsco-ai__toolplan-violations"
            aria-label={isKo ? '계획 검증 문제' : 'Plan validation issues'}
          >
            {toolPlan.validationViolations.map((violation, index) => (
              <span key={`violation-${index}`}>{violation}</span>
            ))}
          </div>
        )}
        {toolPlan.rawPlanJson && (
          <details className="komsco-ai__toolplan-json">
            <summary>
              <span>{isKo ? '원본 기록(JSON)' : 'Raw record JSON'}</span>
            </summary>
            <div className="komsco-ai__toolplan-json-head">
              <span>redacted tool plan</span>
              <button
                aria-label={isKo ? 'Tool Plan JSON 복사' : 'Copy Tool Plan JSON'}
                onClick={() => {
                  if (navigator.clipboard) {
                    void navigator.clipboard.writeText(toolPlan.rawPlanJson || '');
                  }
                }}
                type="button"
              >
                <CoolCopyIcon />
                {isKo ? '복사' : 'Copy'}
              </button>
            </div>
            <pre>{toolPlan.rawPlanJson}</pre>
          </details>
        )}
      </details>
    </div>
  );
};

export default AssistantToolPlanFooter;
