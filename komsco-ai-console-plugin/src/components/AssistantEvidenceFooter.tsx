import * as React from 'react';

import {
  compactEvidenceTypeSummary,
  evidenceStepStatusLabel,
  evidenceTypeLabel,
} from './assistant.evidence';
import { extractRagAppendixRefs } from './assistant.render';
import type { EvidenceFooter } from './assistant.types';

type AssistantEvidenceFooterProps = {
  footer?: EvidenceFooter;
  messageContent?: string;
};

const AssistantEvidenceFooter: React.FC<AssistantEvidenceFooterProps> = ({
  footer,
  messageContent = '',
}) => {
  if (!footer) {
    return null;
  }

  const collectedRefs = footer.collectedRefs.slice(0, 3);
  const missing = footer.missing.slice(0, 3);
  const queryPlan = footer.queryPlan.slice(0, 6);
  const ragAppendixRefs = extractRagAppendixRefs(messageContent);
  const evidenceSummary = compactEvidenceTypeSummary(footer.collectedRefs);

  return (
    <div
      className="komsco-ai__evidence-footer"
      data-evidence-context-id={footer.contextId || ''}
      data-evidence-digest={footer.digest || ''}
    >
      <div className="komsco-ai__evidence-footer-head">
        <span className="komsco-ai__evidence-title">근거</span>
        <span className="komsco-ai__evidence-pill komsco-ai__evidence-pill--collected">
          수집 {footer.collectedCount}건
        </span>
        {footer.missingCount > 0 && (
          <span className="komsco-ai__evidence-pill komsco-ai__evidence-pill--missing">
            추가 확인 {footer.missingCount}건
          </span>
        )}
        <span className="komsco-ai__evidence-summary">{evidenceSummary}</span>
      </div>

      {(collectedRefs.length > 0 ||
        missing.length > 0 ||
        queryPlan.length > 0 ||
        ragAppendixRefs.length > 0) && (
        <details className="komsco-ai__evidence-detail">
          <summary>
            <span>근거 상세보기</span>
          </summary>
          {ragAppendixRefs.length > 0 && (
            <div className="komsco-ai__rag-source-list" aria-label="문서 근거">
              <strong>문서 근거</strong>
              {ragAppendixRefs.map((ref, index) => (
                <div className="komsco-ai__rag-source-item" key={`${ref.title}-${index}`}>
                  <span>{ref.title}</span>
                  {ref.sourceUri && <code>{ref.sourceUri}</code>}
                </div>
              ))}
            </div>
          )}

          {collectedRefs.length > 0 && (
            <div className="komsco-ai__evidence-list" aria-label="수집된 답변 근거">
              {collectedRefs.map((ref, index) => (
                <div
                  className="komsco-ai__evidence-ref"
                  key={`${ref.evidenceId || ref.type || 'ref'}-${index}`}
                >
                  <strong>{evidenceTypeLabel(ref.type)}</strong>
                  <span>{ref.summary || ref.sourceType || '근거 수집 완료'}</span>
                </div>
              ))}
            </div>
          )}

          {missing.length > 0 && (
            <div className="komsco-ai__evidence-missing" aria-label="추가 확인 필요 근거">
              {missing.map((item, index) => (
                <span key={`${item.type || 'missing'}-${index}`}>
                  {evidenceTypeLabel(item.type)}: {item.reason || '추가 확인 필요'}
                </span>
              ))}
            </div>
          )}

          <ol className="komsco-ai__evidence-query-plan" aria-label="조회 계획">
            {queryPlan.map((step, index) => (
              <li key={`${step.step || index}-${step.tool || 'tool'}`}>
                <strong>{evidenceTypeLabel(step.evidenceType || step.tool)}</strong>
                <span>{step.reason || '근거 수집 단계'}</span>
                <code>{evidenceStepStatusLabel(step.status)}</code>
              </li>
            ))}
          </ol>
        </details>
      )}
    </div>
  );
};

export default AssistantEvidenceFooter;
