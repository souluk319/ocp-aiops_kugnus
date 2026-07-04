import * as React from 'react';
import { Button } from '@patternfly/react-core';

import type { AiopsActionCandidate } from '../services/aiGateway';

type AssistantCreateActionPlanButtonsProps = {
  busyCandidateId: string;
  candidates: AiopsActionCandidate[];
  onCreatePlan: (candidate: AiopsActionCandidate) => void;
};

const actionCandidateButtonLabel = (candidate: AiopsActionCandidate): string => {
  const kind = candidate.target?.kind ? `${candidate.target.kind} ` : '';
  const name = candidate.target?.name ?? candidate.title;
  return `조치 계획 생성: ${kind}${name}`;
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
          <Button
            className="komsco-ai__action-button"
            isDisabled={busy}
            isLoading={busy}
            key={candidate.id}
            onClick={() => onCreatePlan(candidate)}
            size="sm"
            variant="secondary"
          >
            {busy ? '처리 중' : actionCandidateButtonLabel(candidate)}
          </Button>
        );
      })}
    </div>
  );
};

export default AssistantCreateActionPlanButtons;
