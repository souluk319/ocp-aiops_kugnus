import * as React from 'react';

import {
  compactEvidenceTypeSummary,
  evidenceStepStatusLabel,
  evidenceTypeLabel,
} from './assistant.evidence';
import { extractRagAppendixRefs } from './assistant.render';
import type { EvidenceFooter, UiLanguage } from './assistant.types';

type AssistantEvidenceFooterProps = {
  footer?: EvidenceFooter;
  language: UiLanguage;
  messageContent?: string;
};

const translateEvidenceDetailText = (
  value: string | undefined,
  language: UiLanguage,
): string | undefined => {
  if (!value || language === 'ko') {
    return value;
  }

  const exact: Record<string, string> = {
    '승인 또는 실행 전에 기존 proposal/sealed plan 존재 여부 확인':
      'Check whether an existing proposal or sealed plan exists before approval or execution',
    'evidence-check 기본 정책과 mutation gate 상태 확인':
      'Check the default evidence policy and mutation gate state',
    '근거 수집 단계': 'Evidence collection step',
    '추가 확인 필요': 'Needs more evidence',
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
    .replace(/근거 수집/g, 'evidence collection')
    .replace(/추가 확인/g, 'follow-up check');
};

const AssistantEvidenceFooter: React.FC<AssistantEvidenceFooterProps> = ({
  footer,
  language,
  messageContent = '',
}) => {
  if (!footer) {
    return null;
  }

  const isKo = language === 'ko';
  const collectedRefs = footer.collectedRefs.slice(0, 3);
  const missing = footer.missing.slice(0, 3);
  const queryPlan = footer.queryPlan.slice(0, 6);
  const ragAppendixRefs = extractRagAppendixRefs(messageContent);
  const evidenceSummary = compactEvidenceTypeSummary(footer.collectedRefs, language);

  return (
    <div
      className="komsco-ai__evidence-footer"
      data-evidence-context-id={footer.contextId || ''}
      data-evidence-digest={footer.digest || ''}
    >
      <div className="komsco-ai__evidence-footer-head">
        <span className="komsco-ai__evidence-title">{isKo ? '근거' : 'Evidence'}</span>
        <span className="komsco-ai__evidence-pill komsco-ai__evidence-pill--collected">
          {isKo ? `수집 ${footer.collectedCount}건` : `Collected ${footer.collectedCount}`}
        </span>
        {footer.missingCount > 0 && (
          <span className="komsco-ai__evidence-pill komsco-ai__evidence-pill--missing">
            {isKo ? `추가 확인 ${footer.missingCount}건` : `Missing ${footer.missingCount}`}
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
            <span>{isKo ? '근거 상세보기' : 'Evidence details'}</span>
          </summary>
          {ragAppendixRefs.length > 0 && (
            <div
              className="komsco-ai__rag-source-list"
              aria-label={isKo ? '문서 근거' : 'Document evidence'}
            >
              <strong>{isKo ? '문서 근거' : 'Document evidence'}</strong>
              {ragAppendixRefs.map((ref, index) => (
                <div className="komsco-ai__rag-source-item" key={`${ref.title}-${index}`}>
                  <span>{ref.title}</span>
                  {ref.sourceUri && <code>{ref.sourceUri}</code>}
                </div>
              ))}
            </div>
          )}

          {collectedRefs.length > 0 && (
            <div
              className="komsco-ai__evidence-list"
              aria-label={isKo ? '수집된 답변 근거' : 'Collected answer evidence'}
            >
              {collectedRefs.map((ref, index) => (
                <div
                  className="komsco-ai__evidence-ref"
                  key={`${ref.evidenceId || ref.type || 'ref'}-${index}`}
                >
                  <strong>{evidenceTypeLabel(ref.type, language)}</strong>
                  <span>
                    {ref.summary || ref.sourceType || (isKo ? '근거 수집 완료' : 'Evidence collected')}
                  </span>
                </div>
              ))}
            </div>
          )}

          {missing.length > 0 && (
            <div
              className="komsco-ai__evidence-missing"
              aria-label={isKo ? '추가 확인 필요 근거' : 'Evidence still needed'}
            >
              {missing.map((item, index) => (
                <span key={`${item.type || 'missing'}-${index}`}>
                  {evidenceTypeLabel(item.type, language)}:{' '}
                  {translateEvidenceDetailText(item.reason, language) ||
                    (isKo ? '추가 확인 필요' : 'Needs more evidence')}
                </span>
              ))}
            </div>
          )}

          <ol
            className="komsco-ai__evidence-query-plan"
            aria-label={isKo ? '조회 계획' : 'Query plan'}
          >
            {queryPlan.map((step, index) => (
              <li key={`${step.step || index}-${step.tool || 'tool'}`}>
                <strong>{evidenceTypeLabel(step.evidenceType || step.tool, language)}</strong>
                <span>
                  {translateEvidenceDetailText(step.reason, language) ||
                    (isKo ? '근거 수집 단계' : 'Evidence collection step')}
                </span>
                <code>{evidenceStepStatusLabel(step.status, language)}</code>
              </li>
            ))}
          </ol>
        </details>
      )}
    </div>
  );
};

export default AssistantEvidenceFooter;
