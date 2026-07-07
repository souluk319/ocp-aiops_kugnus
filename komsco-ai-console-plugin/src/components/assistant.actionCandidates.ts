import type { AiopsActionCandidate } from '../services/aiGateway';

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
