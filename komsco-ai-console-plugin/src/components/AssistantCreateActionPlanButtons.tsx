import * as React from 'react';
import { Button } from '@patternfly/react-core';

import type { AiopsActionCandidate } from '../services/aiGateway';

type AssistantCreateActionPlanButtonsProps = {
  busyCandidateId: string;
  candidates: AiopsActionCandidate[];
  onCreatePlan: (candidate: AiopsActionCandidate) => void;
};

const actionCandidateSummaryLabel = (candidate: AiopsActionCandidate): string => {
  if (candidate.executable === false) {
    return '검토 대기 조치 후보';
  }

  return '승인 가능한 조치 후보';
};

const actionCandidateStateLabel = (candidate: AiopsActionCandidate): string => {
  if (candidate.statusLabel) {
    return candidate.statusLabel;
  }

  return candidate.approvalRequired ? '승인 필요' : '실행 가능';
};

const AssistantCreateActionPlanButtons: React.FC<AssistantCreateActionPlanButtonsProps> = ({
  busyCandidateId,
  candidates,
  onCreatePlan,
}) => {
  if (candidates.length === 0) {
    return null;
  }

  return (
    <div className="komsco-ai__create-action-plan">
      {candidates.map((candidate) => {
        const busy = candidate.id === busyCandidateId;
        return (
          <div className="komsco-ai__create-action-plan-row" key={candidate.id}>
            <span className="komsco-ai__create-action-plan-meta">
              <span className="komsco-ai__create-action-plan-eyebrow">AI Plan 준비됨</span>
              <span className="komsco-ai__create-action-plan-target">
                {actionCandidateSummaryLabel(candidate)}
              </span>
              <span className="komsco-ai__create-action-plan-state">
                {actionCandidateStateLabel(candidate)}
              </span>
            </span>
            <Button
              className="komsco-ai__action-button komsco-ai__create-action-plan-button"
              isDisabled={busy}
              isLoading={busy}
              onClick={() => onCreatePlan(candidate)}
              size="sm"
              variant="secondary"
              aria-label="Action Plan 생성"
            >
              {busy ? '생성 중' : '계획 생성'}
            </Button>
          </div>
        );
      })}
    </div>
  );
};

export default AssistantCreateActionPlanButtons;
