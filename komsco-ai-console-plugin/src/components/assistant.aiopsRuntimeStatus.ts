import { getRecordName } from './assistant.actionRecords';
import type { AiopsRecord, AiopsRuntimeStatus } from '../services/aiGateway';

export type AiopsRuntimeRecordUpdates = Partial<AiopsRuntimeStatus['spec']['records']>;

const mergeAiopsRecordList = (
  current: AiopsRecord[] | undefined,
  incoming: AiopsRecord[] | undefined,
  replaceExisting = true,
): AiopsRecord[] => {
  if (!incoming?.length) {
    return current ?? [];
  }

  const next = [...(current ?? [])];
  incoming.forEach((record) => {
    const recordName = getRecordName(record);
    const existingIndex = recordName
      ? next.findIndex((item) => getRecordName(item) === recordName)
      : -1;
    if (existingIndex >= 0) {
      if (replaceExisting) {
        next[existingIndex] = record;
      }
    } else {
      next.unshift(record);
    }
  });
  return next;
};

export const mergeAiopsRecordUpdates = (
  current: AiopsRuntimeRecordUpdates,
  incoming: AiopsRuntimeRecordUpdates,
  replaceExisting = true,
): AiopsRuntimeRecordUpdates => ({
  ...current,
  actionProposals: mergeAiopsRecordList(
    current.actionProposals,
    incoming.actionProposals,
    replaceExisting,
  ),
  approvalDecisions: mergeAiopsRecordList(
    current.approvalDecisions,
    incoming.approvalDecisions,
    replaceExisting,
  ),
  diagnosticRequests: mergeAiopsRecordList(
    current.diagnosticRequests,
    incoming.diagnosticRequests,
    replaceExisting,
  ),
  executionRecords: mergeAiopsRecordList(
    current.executionRecords,
    incoming.executionRecords,
    replaceExisting,
  ),
  sealedActionPlans: mergeAiopsRecordList(
    current.sealedActionPlans,
    incoming.sealedActionPlans,
    replaceExisting,
  ),
  auditRecords: mergeAiopsRecordList(current.auditRecords, incoming.auditRecords, replaceExisting),
  chatFeedback: mergeAiopsRecordList(current.chatFeedback, incoming.chatFeedback, replaceExisting),
  chatTranscripts: mergeAiopsRecordList(
    current.chatTranscripts,
    incoming.chatTranscripts,
    replaceExisting,
  ),
});

export const mergeAiopsRecordsIntoStatus = (
  status: AiopsRuntimeStatus,
  updates: AiopsRuntimeRecordUpdates,
  replaceExisting = true,
): AiopsRuntimeStatus => {
  const current = status.spec.records;
  return {
    ...status,
    spec: {
      ...status.spec,
      records: {
        ...current,
        ...mergeAiopsRecordUpdates(current, updates, replaceExisting),
      },
    },
  };
};

export const createPendingAiopsStatus = (): AiopsRuntimeStatus => ({
  spec: {
    capabilities: {
      actionExecutorConfigured: false,
      diagnosticsControllerConfigured: false,
      diagnosticsEnabled: false,
      mutationsEnabled: true,
      rag: {
        accessPath: 'gateway-only',
        aclRequired: true,
        backendType: 'pgvector',
        collection: 'komsco-aiops-runbooks',
        directDatabaseAccess: false,
        embeddingModel: 'not_configured',
        endpointConfigured: false,
        reason: 'RAG status is pending until the gateway status call completes.',
        requiredMetadata: [
          'documentId',
          'sourceUri',
          'sourceType',
          'checksum',
          'version',
          'aclGroups',
        ],
        status: 'pending',
        vectorDimensions: 0,
      },
      recordStoreEnabled: false,
      unrestrictedCommandsEnabled: true,
    },
    safetyContract: {
      adapterStatus: [],
      allowedReadOnlyVerbs: ['get', 'list', 'watch'],
      capabilityGates: {},
      evidenceStatus: [],
      forbiddenActions: [
        'create',
        'update',
        'patch',
        'delete',
        'exec',
        'portforward',
        'restart',
        'scale',
        'rollout',
      ],
      mode: 'controlled_execution',
      product: {
        mission: 'Evidence-first OpenShift operations assistant',
        mode: 'evidence_first_execution',
        name: 'AIOps for OCP',
      },
      rcaContextStatus: {
        latestContext: null,
        source: 'chat_stream',
        status: 'waiting_for_first_question',
      },
      toolPlanStatus: {
        latestRuntimePlan: null,
        source: 'deterministic_gateway_planner',
        status: 'waiting_for_first_question',
      },
    },
    records: {
      actionProposals: [],
      approvalDecisions: [],
      diagnosticRequests: [],
      executionRecords: [],
      sealedActionPlans: [],
    },
  },
});
