import type { AiopsActionCandidate } from '../services/aiGateway';

const ACTIONABLE_MESSAGE_RE =
  /(Action\s*Plan|조치|승인|실행|검증|롤백|RCA|원인\s*분석|원인\s*후보|위험|경고|이슈|장애|실패|대기|재시작|CrashLoopBackOff|ImagePullBackOff|OOMKilled|PodNotReady|BackOff|Failed|Readiness|Liveness|probe)/i;

const NON_ACTION_LOOKUP_RE =
  /(몇\s*개|개수|수가\s*제일|가장\s*많|있었|있어\?|조회할\s*수\s*있|어디|뭐야|무엇|목록|리스트|namespace.*확인|네임스페이스.*확인)/i;

const CLEANUP_CLARIFICATION_RE =
  /정리 대상 범위 확인|범위가 아직 넓습니다|이 범위\(.+\)로 정리 검토를 진행할까요|범위를 확인하면/i;

const CLEANUP_REVIEW_RE = /테스트 Pod 정리 검토|정리 검토 후보|삭제 검토 후보/i;

const ISSUE_TOKENS = [
  'crashloopbackoff',
  'imagepullbackoff',
  'oomkilled',
  'podnotready',
  'backoff',
  'failed',
  'readiness',
  'liveness',
  'probe',
  'pending',
  'error',
  '재시작',
  '이미지',
  '실패',
  '대기',
  '준비',
  '경고',
  '위험',
  '프로브',
];

export const candidateActionType = (candidate: AiopsActionCandidate): string => {
  const sourceType = String(candidate.sourceType || '').trim();
  if (sourceType) {
    return sourceType;
  }
  const sourceFindingId = String(candidate.sourceFindingId || '').trim();
  if (sourceFindingId) {
    return sourceFindingId.replace(/-[a-z0-9]([-a-z0-9]*[a-z0-9])?$/i, '');
  }
  return candidate.title || candidate.id || 'action';
};

export const candidateDedupeKey = (candidate: AiopsActionCandidate): string => {
  const target = candidate.target ?? {};
  const namespace = target.namespace || '';
  const kind = target.kind || '';
  const name = target.name || '';
  return [candidateActionType(candidate), namespace, kind, name]
    .map((value) => String(value || '').trim().toLowerCase())
    .join('|');
};

const candidateSpecificityScore = (candidate: AiopsActionCandidate): number => {
  let score = 0;
  if (candidate.id && !candidate.id.startsWith('chat-')) {
    score += 40;
  }
  if (candidate.evidenceRefs?.length) {
    score += 16;
  }
  if (candidate.evidence) {
    score += 8;
  }
  if (candidate.expectedImpact) {
    score += 6;
  }
  if (candidate.verificationChecks?.length) {
    score += 6;
  }
  if (candidate.prerequisiteChecks?.length) {
    score += 4;
  }
  score += Number(candidate.priority ?? 0) / 100;
  return score;
};

export const dedupeActionCandidates = (
  candidates: AiopsActionCandidate[],
): AiopsActionCandidate[] => {
  const byKey = new Map<string, AiopsActionCandidate>();
  candidates.forEach((candidate) => {
    const key = candidateDedupeKey(candidate);
    const current = byKey.get(key);
    if (!current || candidateSpecificityScore(candidate) > candidateSpecificityScore(current)) {
      byKey.set(key, candidate);
    }
  });
  return Array.from(byKey.values()).sort(
    (a, b) =>
      (b.priority ?? 0) - (a.priority ?? 0) ||
      candidateSpecificityScore(b) - candidateSpecificityScore(a),
  );
};

const candidateText = (candidate: AiopsActionCandidate): string =>
  [
    candidate.id,
    candidate.sourceType,
    candidate.sourceFindingId,
    candidate.title,
    candidate.statusLabel,
    candidate.severity,
    candidate.evidence,
    candidate.expectedImpact,
    candidate.target?.namespace,
    candidate.target?.kind,
    candidate.target?.name,
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();

const candidateSharesIssueToken = (content: string, candidate: AiopsActionCandidate): boolean => {
  const normalizedContent = content.toLowerCase();
  const normalizedCandidate = candidateText(candidate);
  return ISSUE_TOKENS.some(
    (token) => normalizedContent.includes(token) && normalizedCandidate.includes(token),
  );
};

export const messageLooksActionableForCandidates = (content: string): boolean => {
  const normalized = content.trim();
  if (!normalized) {
    return false;
  }
  if (!ACTIONABLE_MESSAGE_RE.test(normalized)) {
    return false;
  }
  if (NON_ACTION_LOOKUP_RE.test(normalized) && !/(Action\s*Plan|조치|승인|실행|RCA|원인)/i.test(normalized)) {
    return false;
  }
  return true;
};

export const matchActionCandidatesForMessage = (
  content: string,
  candidates: AiopsActionCandidate[],
): AiopsActionCandidate[] => {
  if (CLEANUP_CLARIFICATION_RE.test(content)) {
    return [];
  }

  const cleanupReviewAnswer = CLEANUP_REVIEW_RE.test(content);
  if (cleanupReviewAnswer) {
    const cleanupMatches = candidates.filter((candidate) => {
      const sourceType = String(candidate.sourceType || '');
      const targetName = candidate.target?.name;
      const namespace = candidate.target?.namespace;
      return Boolean(
        /cleanup_review/i.test(sourceType) &&
          ((targetName && content.includes(targetName)) ||
            (namespace && content.includes(namespace))),
      );
    });
    return dedupeActionCandidates(cleanupMatches);
  }

  if (!messageLooksActionableForCandidates(content)) {
    return [];
  }

  const matched = candidates.filter((candidate) => {
    const targetName = candidate.target?.name;
    const namespace = candidate.target?.namespace;
    const exactTargetMatch = Boolean(
      (targetName && content.includes(targetName)) ||
        (targetName && targetName.includes(',') && targetName.split(',').some((name) => content.includes(name.trim()))) ||
        (namespace && content.includes(namespace) && candidateSharesIssueToken(content, candidate)),
    );
    return exactTargetMatch || candidateSharesIssueToken(content, candidate);
  });
  return dedupeActionCandidates(matched);
};
