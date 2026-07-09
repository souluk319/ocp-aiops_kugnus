import { ACTION_STAGE_RANK } from './assistant.actionRecords';
import type { AiopsActionCandidate } from '../services/aiGateway';
import type { ConversationActionRef } from './assistant.types';

export const targetKeyFromParts = (namespace?: string, name?: string): string =>
  namespace ? `${namespace}/${name ?? ''}` : (name ?? '');

export const conversationActionRefFromCandidate = (
  candidate: AiopsActionCandidate,
  messageAnchor?: string,
): ConversationActionRef => {
  const targetKey = targetKeyFromParts(candidate.target?.namespace, candidate.target?.name);
  const toolName = candidate.title;

  return {
    candidateId: candidate.id,
    id: `candidate|${candidate.id}|${targetKey}|${toolName}`.toLowerCase(),
    label: '1단계 · 조치 계획 생성',
    messageAnchor,
    stage: 'proposal',
    targetKey: targetKey || candidate.title,
    toolName,
    updatedAt: Date.now(),
  };
};

export const pendingActionCandidatesForRefs = (
  candidates: AiopsActionCandidate[],
  refs: ConversationActionRef[],
): AiopsActionCandidate[] => {
  const createdCandidateIds = new Set(
    refs
      .map((ref) => ref.candidateId)
      .filter((candidateId): candidateId is string => Boolean(candidateId)),
  );
  if (createdCandidateIds.size === 0) {
    return candidates;
  }
  return candidates.filter((candidate) => !createdCandidateIds.has(candidate.id));
};

export const groupActionRefsByCandidateId = (
  refs: ConversationActionRef[],
): Record<string, ConversationActionRef[]> =>
  refs.reduce<Record<string, ConversationActionRef[]>>((groups, ref) => {
    if (!ref.candidateId) {
      return groups;
    }
    groups[ref.candidateId] = [...(groups[ref.candidateId] ?? []), ref];
    return groups;
  }, {});

export const mergeConversationActionRefs = (
  refs: ConversationActionRef[],
  ref: ConversationActionRef,
): ConversationActionRef[] => {
  const next = [...refs];
  const existingIndex = next.findIndex(
    (item) =>
      item.id === ref.id ||
      (item.targetKey === ref.targetKey &&
        item.toolName === ref.toolName &&
        item.messageAnchor === ref.messageAnchor &&
        (item.planDigest === ref.planDigest || !item.planDigest || !ref.planDigest)),
  );

  if (existingIndex >= 0) {
    const existing = next[existingIndex];
    const existingRank = ACTION_STAGE_RANK[existing.stage] ?? 0;
    const incomingRank = ACTION_STAGE_RANK[ref.stage] ?? 0;
    if (existingRank > incomingRank) {
      next[existingIndex] = {
        ...existing,
        messageAnchor: ref.messageAnchor ?? existing.messageAnchor,
        updatedAt: Date.now(),
      };
      return next;
    }
    next[existingIndex] = {
      ...existing,
      ...ref,
      candidateId: ref.candidateId ?? existing.candidateId,
      messageAnchor: ref.messageAnchor ?? existing.messageAnchor,
      updatedAt: Date.now(),
    };
    return next;
  }

  return [{ ...ref, updatedAt: Date.now() }, ...next].slice(0, 12);
};

const actionRefTimestamp = (ref: ConversationActionRef): number =>
  ref.updatedAt || new Date(String(ref.createdAt ?? 0)).getTime() || 0;

export const sortConversationActionRefsForDisplay = (
  refs: ConversationActionRef[],
): ConversationActionRef[] =>
  [...refs].sort((a, b) => {
    const stageDelta = (ACTION_STAGE_RANK[b.stage] ?? 0) - (ACTION_STAGE_RANK[a.stage] ?? 0);
    if (stageDelta !== 0) {
      return stageDelta;
    }
    return actionRefTimestamp(b) - actionRefTimestamp(a);
  });
