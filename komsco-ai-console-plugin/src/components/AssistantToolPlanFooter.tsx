import * as React from 'react';

import { CoolCopyIcon } from './coolicons';
import { evidenceTypeLabel } from './assistant.evidence';
import {
  executionPolicyLabel,
  isReadOnlyExecutionPolicy,
  toolPlanPlannerLabel,
  toolPlanPlannerSummary,
} from './assistant.toolPlan';
import type { ToolPlanFooter } from './assistant.types';

type AssistantToolPlanFooterProps = {
  toolPlan?: ToolPlanFooter;
};

const AssistantToolPlanFooter: React.FC<AssistantToolPlanFooterProps> = ({ toolPlan }) => {
  if (!toolPlan || toolPlan.steps.length === 0) {
    return null;
  }

  const steps = toolPlan.steps.slice(0, 6);
  const missingEvidence = toolPlan.missingEvidence.slice(0, 3);
  const readOnly = isReadOnlyExecutionPolicy(toolPlan.executionPolicyMode);
  const targetLabel = [toolPlan.targetResourceKind, toolPlan.targetResourceName]
    .filter(Boolean)
    .join(' ');

  return (
    <div className="komsco-ai__toolplan-footer">
      <div className="komsco-ai__toolplan-footer-head">
        <span className="komsco-ai__evidence-title">조회 계획</span>
        <span className="komsco-ai__evidence-pill komsco-ai__evidence-pill--collected">
          {toolPlan.taskType}
        </span>
        <span
          className={`komsco-ai__evidence-pill ${
            readOnly
              ? 'komsco-ai__evidence-pill--collected'
              : 'komsco-ai__evidence-pill--policy-warning'
          }`}
        >
          {executionPolicyLabel(toolPlan.executionPolicyMode)}
        </span>
        {toolPlan.validationOk === false && (
          <span className="komsco-ai__evidence-pill komsco-ai__evidence-pill--missing">
            계획 검증 실패
          </span>
        )}
      </div>

      <details className="komsco-ai__evidence-detail">
        <summary>
          <span>조회 계획 상세보기</span>
        </summary>
        <div className="komsco-ai__toolplan-source">
          <strong>{toolPlan.plannerLabel || toolPlanPlannerLabel(toolPlan.plannerSource)}</strong>
          <span>{toolPlan.plannerSummary || toolPlanPlannerSummary(toolPlan.plannerSource)}</span>
        </div>
        {targetLabel && (
          <div className="komsco-ai__toolplan-target">
            대상: {targetLabel}
            {toolPlan.targetNamespace ? ` (${toolPlan.targetNamespace})` : ''}
          </div>
        )}
        <ol className="komsco-ai__evidence-query-plan" aria-label="조회 계획 단계">
          {steps.map((step, index) => (
            <li key={`${step.step || index}-${step.tool || 'tool'}`}>
              <strong>{evidenceTypeLabel(step.evidenceType || step.tool)}</strong>
              <span>{step.reason || '조회 단계'}</span>
              <code>{step.verb || step.tool}</code>
            </li>
          ))}
        </ol>
        {missingEvidence.length > 0 && (
          <div className="komsco-ai__evidence-missing" aria-label="추가 확인 필요 근거">
            {missingEvidence.map((item, index) => (
              <span key={`${item.type || 'missing'}-${index}`}>
                {evidenceTypeLabel(item.type)}: {item.reason || '추가 확인 필요'}
              </span>
            ))}
          </div>
        )}
        {toolPlan.validationViolations.length > 0 && (
          <div className="komsco-ai__toolplan-violations" aria-label="계획 검증 문제">
            {toolPlan.validationViolations.map((violation, index) => (
              <span key={`violation-${index}`}>{violation}</span>
            ))}
          </div>
        )}
        {toolPlan.rawPlanJson && (
          <details className="komsco-ai__toolplan-json">
            <summary>
              <span>감사용 JSON</span>
            </summary>
            <div className="komsco-ai__toolplan-json-head">
              <span>redacted tool plan</span>
              <button
                aria-label="Tool Plan JSON 복사"
                onClick={() => {
                  if (navigator.clipboard) {
                    void navigator.clipboard.writeText(toolPlan.rawPlanJson || '');
                  }
                }}
                type="button"
              >
                <CoolCopyIcon />
                복사
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
