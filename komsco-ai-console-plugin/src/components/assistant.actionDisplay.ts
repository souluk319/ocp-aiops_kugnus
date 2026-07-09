import {
  ACTION_STAGE_RANK,
  actionRecordCreatedAt,
  actionRecordDedupeKey,
  getActionRecordStage,
  getActionRecordToolName,
  getApprovalPlanDigest,
  getExecutionOutcomeSummary,
  getPlanDigest,
  getRecordName,
  getRecordSpecMap,
  getRecordTargetLabel,
} from './assistant.actionRecords';
import { getAiopsRecordAction } from './assistant.actionState';
import { groupActionRefsByCandidateId } from './assistant.sessionActions';
import type { AiopsActionCandidate, AiopsRuntimeStatus } from '../services/aiGateway';
import type {
  AiopsExecutionMode,
  AiopsRecordView,
  ConversationActionRef,
} from './assistant.types';

export const getAnyPlanDigest = (record: AiopsRecordView): string => {
  const spec = getRecordSpecMap(record);
  return (
    getPlanDigest(record) ||
    getApprovalPlanDigest(record) ||
    (typeof spec.planDigest === 'string' ? spec.planDigest : '')
  );
};

export const highestLifecycleRecordForPlanDigest = (
  status: AiopsRuntimeStatus | null,
  planDigest: string,
): AiopsRecordView | undefined => {
  if (!status || !planDigest) {
    return undefined;
  }
  const records = status.spec.records;
  return (
    records.executionRecords.find((record) => getAnyPlanDigest(record) === planDigest) ??
    records.approvalDecisions.find((record) => getAnyPlanDigest(record) === planDigest) ??
    records.sealedActionPlans.find((record) => getAnyPlanDigest(record) === planDigest) ??
    records.actionProposals.find((record) => getAnyPlanDigest(record) === planDigest)
  );
};

const actionRecordMatchesRef = (
  record: AiopsRecordView,
  ref: ConversationActionRef,
): boolean => {
  if (ref.recordName && getRecordName(record) === ref.recordName) {
    return true;
  }
  if (ref.planDigest && getAnyPlanDigest(record) === ref.planDigest) {
    return true;
  }
  return (
    ref.targetKey === getRecordTargetLabel(record) &&
    (!ref.toolName || ref.toolName === getActionRecordToolName(record))
  );
};

export const actionRecordInlineKey = (record: AiopsRecordView): string =>
  [
    getRecordName(record) || 'record',
    getAnyPlanDigest(record) || 'digest',
    getRecordTargetLabel(record),
    getActionRecordToolName(record),
    getActionRecordStage(record),
  ].join('|');

export const groupActionRecordsByCandidateId = (
  records: AiopsRecordView[],
  refs: ConversationActionRef[],
): Record<string, AiopsRecordView[]> => {
  const refsByCandidateId = groupActionRefsByCandidateId(refs);

  return Object.entries(refsByCandidateId).reduce<Record<string, AiopsRecordView[]>>(
    (groups, [candidateId, candidateRefs]) => {
      const seen = new Set<string>();
      const matched = records.filter((record) => {
        if (!candidateRefs.some((ref) => actionRecordMatchesRef(record, ref))) {
          return false;
        }
        const key = actionRecordInlineKey(record);
        if (seen.has(key)) {
          return false;
        }
        seen.add(key);
        return true;
      });
      if (matched.length > 0) {
        groups[candidateId] = matched;
      }
      return groups;
    },
    {},
  );
};

const actionRecordDisplayRank = (
  record: AiopsRecordView,
  aiopsStatus: AiopsRuntimeStatus | null,
): number => {
  if (getExecutionOutcomeSummary(record, aiopsStatus)) {
    return 5;
  }
  return ACTION_STAGE_RANK[getActionRecordStage(record)];
};

const collapseActionRecordsForDisplay = (
  records: AiopsRecordView[],
  aiopsStatus: AiopsRuntimeStatus | null,
  executionMode: AiopsExecutionMode,
): AiopsRecordView[] => {
  const eligible = records
    .filter(
      (record) =>
        Boolean(getAiopsRecordAction(record, aiopsStatus, executionMode)) ||
        Boolean(getExecutionOutcomeSummary(record, aiopsStatus)),
    )
    .sort((a, b) => {
      const rankDelta =
        actionRecordDisplayRank(b, aiopsStatus) - actionRecordDisplayRank(a, aiopsStatus);
      if (rankDelta !== 0) {
        return rankDelta;
      }
      return actionRecordCreatedAt(b) - actionRecordCreatedAt(a);
    });
  const seen = new Set<string>();

  return eligible.filter((record) => {
    const key = actionRecordDedupeKey(record);
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
};

type LatestAnswerActionRecordsInput = {
  readonly actionRefs: ConversationActionRef[];
  readonly aiopsStatus: AiopsRuntimeStatus | null;
  readonly executionMode: AiopsExecutionMode;
  readonly messageAnchor?: string;
  readonly messageContent: string;
};

export const latestAnswerActionRecords = ({
  actionRefs,
  aiopsStatus,
  executionMode,
  messageAnchor,
  messageContent,
}: LatestAnswerActionRecordsInput): AiopsRecordView[] => {
  const records = aiopsStatus?.spec.records;
  if (!records) {
    return [];
  }

  const anchorRefs = messageAnchor
    ? actionRefs.filter((ref) => ref.messageAnchor === messageAnchor)
    : [];
  const scopedActionRefs =
    anchorRefs.length > 0 ? anchorRefs : actionRefs.length === 1 ? actionRefs : [];
  const mentionedRecordNames = new Set(
    Array.from(messageContent.matchAll(/\b(?:proposal|plan|approval|execution)-[a-z0-9-]+/gi))
      .map((match) => match[0].toLowerCase()),
  );

  if (scopedActionRefs.length === 0 && mentionedRecordNames.size === 0) {
    return [];
  }

  const matchedRecords = [
    ...records.executionRecords,
    ...records.approvalDecisions,
    ...records.sealedActionPlans,
    ...records.actionProposals,
  ].filter((record) => {
      const recordName = getRecordName(record).toLowerCase();
      if (mentionedRecordNames.has(recordName)) {
        return true;
      }

      const matchesAnchorRef = scopedActionRefs.some((ref) => {
        const refCreatedAt = ref.createdAt ? new Date(ref.createdAt).getTime() || 0 : 0;
        const recordCreatedAt = actionRecordCreatedAt(record);
        if (ref.recordName && getRecordName(record) === ref.recordName) {
          return true;
        }
        if (refCreatedAt > 0 && recordCreatedAt > 0 && recordCreatedAt < refCreatedAt) {
          return false;
        }
        if (ref.planDigest && getAnyPlanDigest(record) === ref.planDigest) {
          return true;
        }
        if (
          (ACTION_STAGE_RANK[getActionRecordStage(record)] ?? 0) <
          (ACTION_STAGE_RANK[ref.stage] ?? 0)
        ) {
          return false;
        }
        return (
          ref.targetKey === getRecordTargetLabel(record) &&
          (!ref.toolName || ref.toolName === getActionRecordToolName(record))
        );
      });
      if (matchesAnchorRef) {
        return true;
      }

      return false;
    });

  return collapseActionRecordsForDisplay(matchedRecords, aiopsStatus, executionMode).slice(0, 3);
};

export const actionRecordsForMatchedCandidates = (
  aiopsStatus: AiopsRuntimeStatus | null,
  executionMode: AiopsExecutionMode,
  candidates: AiopsActionCandidate[],
): AiopsRecordView[] => {
  // Do not attach old global action records to a new answer just because the
  // target name matches. The lifecycle should appear only after this answer's
  // CTA creates a session action ref.
  void aiopsStatus;
  void executionMode;
  void candidates;
  return [];
};
