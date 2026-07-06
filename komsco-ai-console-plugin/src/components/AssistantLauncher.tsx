import * as React from 'react';
import { Card, CardBody } from '@patternfly/react-core';
import * as ReactDOM from 'react-dom';
import AssistantAnswerActions from './AssistantActionRecords';
import AssistantComposer from './AssistantComposer';
import AssistantCreateActionPlanButtons from './AssistantCreateActionPlanButtons';
import AssistantEvidenceFooter from './AssistantEvidenceFooter';
import AssistantEmptyState from './AssistantEmptyState';
import AssistantHeader from './AssistantHeader';
import AssistantHistoryPanel from './AssistantHistoryPanel';
import AssistantImageLightbox from './AssistantImageLightbox';
import AssistantInsightRail from './AssistantInsightRail';
import AssistantMessageHeader from './AssistantMessageHeader';
import AssistantResizeHandles from './AssistantResizeHandles';
import AssistantSurfacePortal from './AssistantSurfacePortal';
import { renderFormattedContent } from './AssistantMessageContent';
import AssistantToolPlanFooter from './AssistantToolPlanFooter';
import ProgressTimeline, {
  formatToolTitle,
  normalizeToolName,
  rcaContextPhaseLabel,
} from './AssistantProgressTimeline';
import {
  CoolCopyIcon,
  CoolPencilIcon,
  CoolThumbsDownIcon,
  CoolThumbsUpIcon,
} from './coolicons';
import {
  ACCEPTED_IMAGE_MIME_TYPES,
  ACCEPTED_RAG_DOCUMENT_EXTENSIONS,
  ACCEPTED_RAG_DOCUMENT_MIME_TYPES,
  ANSWER_STREAM_STEP_ID,
  ASSISTANT_TASK_MODES,
  ASSISTANT_TYPEWRITER_CHARS,
  ASSISTANT_TYPEWRITER_INTERVAL_MS,
  CLUSTER_SUMMARY_REFRESH_MS,
  DEFAULT_AIOPS_EXECUTION_MODE,
  FAILED_TOOL_STATUSES,
  GATEWAY_PREP_STEP_ID,
  GATEWAY_PREP_TOOLS,
  HISTORY_DRAWER_WIDTH,
  MAX_IMAGE_ATTACHMENT_BYTES,
  MAX_IMAGE_ATTACHMENT_TOTAL_BYTES,
  MAX_IMAGE_ATTACHMENTS,
  MAX_RAG_DOCUMENT_UPLOAD_BYTES,
  MAX_RECENT_CONTEXT_MESSAGES,
  MAX_STORED_CONVERSATIONS,
  MIN_STOP_BUTTON_VISIBLE_MS,
  MULTIPART_RAG_DOCUMENT_EXTENSIONS,
  MULTIPART_RAG_DOCUMENT_MIME_TYPES,
  RCA_CONTEXT_STEP_ID,
  RCA_PLAN_STEP_ID,
  RESPONSE_WAIT_STEP_ID,
  RUN_LOOP_STEP_ID,
  SCROLL_BOTTOM_THRESHOLD_PX,
  STORED_MESSAGE_FEEDBACK_KEY,
} from './assistant.constants';
import { formatFileSize } from './assistant.attachments';
import { TASK_MODE_EMPTY_COPY, UI_COPY } from './assistant.copy';
import {
  buildEvidenceCopyText,
  buildEvidenceFooter,
} from './assistant.evidence';
import {
  ACTION_STAGE_RANK,
  actionAnchorForMessageIndex,
  actionRecordCreatedAt,
  actionRecordDedupeKey,
  conversationActionRefFromRecord,
  findPlanByDigest,
  getActionRecordStage,
  getActionRecordToolName,
  getApprovalId,
  getApprovalPlanDigest,
  getExecutionOutcomeSummary,
  getPlanDigest,
  getRecordName,
  getRecordTargetLabel,
} from './assistant.actionRecords';
import {
  canUseActionExecution,
  executionModeAllowsActions,
  getAiopsRecordAction,
  getActionExecutionDisabledReason,
} from './assistant.actionState';
import { getClusterHost } from './assistant.insightRailHelpers';
import {
  createRunId,
  formatHistoryTime,
  getConversationTitle,
  languageLocale,
  readStoredActiveConversation,
  readStoredConversationHistory,
  readStoredUiLanguage,
  writeStoredActiveConversation,
  writeStoredConversationHistory,
  writeStoredUiLanguage,
} from './assistant.storage';
import {
  buildToolPlanFooter,
} from './assistant.toolPlan';
import {
  stripDefaultEvidenceAppendix,
} from './assistant.render';
import type {
  AiopsExecutionMode,
  AiopsRecordAction,
  AiopsRecordView,
  AssistantLauncherProps,
  AssistantTaskMode,
  ConversationActionRef,
  ConversationHistoryItem,
  EvidenceFooter,
  HistoryPanelView,
  LightspeedStatusUpdate,
  Message,
  PanelResizeDirection,
  ProgressStatus,
  ProgressStep,
  RunStatusEvent,
  StoredActiveConversation,
  ToolPlanFooter,
  ToolStreamEvent,
  UiLanguage,
} from './assistant.types';
import {
  type AiopsActionCandidate,
  type AiopsRuntimeStatus,
  type AuthSubject,
  type ChatContextMessage,
  type ChatFeedbackPayload,
  type ClusterSummary,
  type ImageAttachment,
  type RagUploadedDocument,
  approveActionPlan,
  createActionCandidatePlan,
  createActionPlan,
  executeApprovedAction,
  fetchActionCandidates,
  fetchAiopsStatus,
  fetchClusterSummary,
  fetchConsoleUserSubject,
  fetchUploadedRagDocuments,
  rejectActionPlan,
  submitChatFeedback,
  streamChat,
  uploadRagDocument,
  uploadRagDocumentFile,
} from '../services/aiGateway';
import { redactSensitiveText } from '../utils/evidenceDisplay';
import aiopsIcon from '../assets/aiops_icon.svg';
import './assistant.css';

const draftExecutionMode = (pageContext?: Record<string, unknown>): AiopsExecutionMode | null => {
  const value = String(pageContext?.aiopsExecutionMode ?? '')
    .trim()
    .toLowerCase();
  if (
    value === 'read-only' ||
    value === 'read_only' ||
    value === 'evidence-check' ||
    value === 'evidence_check'
  ) {
    return 'read-only';
  }
  if (value === 'execute' || value === 'unrestricted') {
    return value;
  }
  return null;
};

const aiopsActionErrorMessage = (error: unknown): string => {
  const raw =
    error instanceof Error
      ? error.message
      : typeof error === 'string'
        ? error
        : JSON.stringify(error ?? '');
  const text = raw.trim();
  const lower = text.toLowerCase();

  if (/digest|expectedplandigest|mismatch|does not match/.test(lower)) {
    return '조치 계획 검증값이 현재 기록과 맞지 않습니다. 최신 상태로 다시 조회한 뒤 계획을 다시 만들어 주세요.';
  }
  if (/expired|ttl|stale/.test(lower)) {
    return '조치 계획 또는 승인 토큰이 만료되었습니다. 같은 대상에 대해 새 계획을 만들어야 합니다.';
  }
  if (/forbidden|403|rbac|access|permission|ssar|denied/.test(lower)) {
    return '현재 사용자 권한으로는 이 조치를 실행할 수 없습니다. 대상 리소스 권한과 승인자를 확인해 주세요.';
  }
  if (/not found|404|target.*missing|target.*unavailable/.test(lower)) {
    return '대상 리소스를 찾지 못했습니다. 네임스페이스와 리소스 이름이 최신인지 확인해 주세요.';
  }
  if (/disabled|capability|executor|mutation.*disabled|mutations.*disabled/.test(lower)) {
    return '게이트웨이 실행 기능이 꺼져 있어 실제 변경을 보낼 수 없습니다. 실행 기능과 Action Executor 설정을 확인해 주세요.';
  }
  if (/separation of duties|same.*approver|requester and approver|conflict|409/.test(lower)) {
    return '승인 정책과 충돌했습니다. 위험도가 있는 조치는 요청자 본인이 승인할 수 없거나 최신 계획과 승인 조건이 맞지 않습니다.';
  }
  if (/failed|error|exception|timeout/.test(lower)) {
    return '조치 요청 처리 중 오류가 발생했습니다. 잠시 후 다시 시도하거나 실행 기록에서 원문 오류를 확인해 주세요.';
  }

  return text || 'AIOps 조치 요청을 완료하지 못했습니다.';
};

const flushReactSync = (callback: () => void) => {
  const flushSync = (ReactDOM as unknown as { flushSync?: (syncCallback: () => void) => void })
    .flushSync;

  if (flushSync) {
    flushSync(callback);
    return;
  }

  callback();
};
const createPendingAiopsStatus = (): AiopsRuntimeStatus => ({
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
        name: 'AIOps Copilot',
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

const RESOURCE_KIND_BY_ROUTE_SEGMENT: Record<string, string> = {
  buildconfigs: 'BuildConfig',
  configmaps: 'ConfigMap',
  cronjobs: 'CronJob',
  daemonsets: 'DaemonSet',
  deployments: 'Deployment',
  deploymentconfigs: 'DeploymentConfig',
  events: 'Event',
  horizontalpodautoscalers: 'HorizontalPodAutoscaler',
  hpas: 'HorizontalPodAutoscaler',
  ingresses: 'Ingress',
  jobs: 'Job',
  namespaces: 'Namespace',
  nodes: 'Node',
  pods: 'Pod',
  projects: 'Project',
  replicasets: 'ReplicaSet',
  replicationcontrollers: 'ReplicationController',
  routes: 'Route',
  secrets: 'Secret',
  services: 'Service',
  statefulsets: 'StatefulSet',
};

const decodePathSegment = (segment: string | undefined): string | undefined => {
  if (!segment) {
    return undefined;
  }

  try {
    return decodeURIComponent(segment);
  } catch {
    return segment;
  }
};

const buildConsolePageContext = (): Record<string, unknown> => {
  const { href, pathname } = window.location;
  const segments = pathname.split('/').filter(Boolean);
  const context: Record<string, unknown> = {
    href,
    pathname,
  };

  const route = decodePathSegment(segments[0]);
  if (route) {
    context.route = route;
  }

  const nsIndex = segments.indexOf('ns');
  if (nsIndex >= 0) {
    const namespace = decodePathSegment(segments[nsIndex + 1]);
    if (namespace) {
      context.namespace = namespace;
    }
  }

  if (segments[0] === 'k8s' && segments[1] === 'cluster') {
    context.clusterScope = true;
  }

  let resourceSegmentIndex = -1;
  if (nsIndex >= 0) {
    resourceSegmentIndex = nsIndex + 2;
  } else if (segments[0] === 'k8s' && segments[1] === 'cluster') {
    resourceSegmentIndex = 2;
  }
  const resourceList = decodePathSegment(segments[resourceSegmentIndex]);

  if (resourceList) {
    context.resourceList = resourceList;

    const resourceKind = RESOURCE_KIND_BY_ROUTE_SEGMENT[resourceList.toLowerCase()];
    if (resourceKind) {
      context.resourceKind = resourceKind;
    }

    const resourceName = decodePathSegment(segments[resourceSegmentIndex + 1]);
    if (resourceKind && resourceName) {
      context.resourceName = resourceName;
    }
  }

  if (route === 'catalog') {
    context.perspective = 'developer';
    context.resourceKind = 'Catalog';
  }

  if (route === 'topology') {
    context.perspective = 'developer';
  }

  if (route === 'monitoring') {
    context.perspective = 'administrator';
  }

  return context;
};

const isRagDocumentFile = (file: File): boolean => {
  const loweredName = file.name.toLowerCase();
  return (
    ACCEPTED_RAG_DOCUMENT_MIME_TYPES.has(file.type) ||
    file.type.startsWith('text/') ||
    ACCEPTED_RAG_DOCUMENT_EXTENSIONS.some((extension) => loweredName.endsWith(extension))
  );
};

const shouldUploadRagDocumentAsFile = (file: File): boolean => {
  const loweredName = file.name.toLowerCase();
  return (
    MULTIPART_RAG_DOCUMENT_MIME_TYPES.has(file.type) ||
    MULTIPART_RAG_DOCUMENT_EXTENSIONS.some((extension) => loweredName.endsWith(extension))
  );
};

const readRagDocumentContent = async (file: File): Promise<string> => {
  try {
    return await file.text();
  } catch {
    throw new Error(`${file.name} 문서를 읽을 수 없습니다.`);
  }
};

const readImageAttachment = (file: File): Promise<ImageAttachment> =>
  new Promise((resolve, reject) => {
    const reader = new FileReader();

    reader.onerror = () => reject(new Error(`${file.name} 파일을 읽을 수 없습니다.`));
    reader.onload = () => {
      const result = typeof reader.result === 'string' ? reader.result : '';
      const [, data = ''] = result.split(',');

      if (!data) {
        reject(new Error(`${file.name} 파일 데이터가 비어 있습니다.`));
        return;
      }

      resolve({
        data,
        id: `img-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
        mimeType: file.type,
        name: file.name,
        size: file.size,
      });
    };
    reader.readAsDataURL(file);
  });

const stringifyDetail = (value: unknown): string => {
  if (value === undefined || value === null) {
    return '';
  }

  if (typeof value === 'string') {
    return value;
  }

  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
};

const getToolDetail = (event: ToolStreamEvent): string => {
  if (event.detail) {
    return event.detail;
  }

  if (event.type === 'tool_call') {
    return stringifyDetail(event.args);
  }

  return stringifyDetail(event.result);
};

const getToolSummary = (event: ToolStreamEvent): string => {
  if (event.summary) {
    return event.summary;
  }

  if (event.type === 'tool_call') {
    return event.serverName ? `${event.serverName} 도구 호출` : '도구 호출';
  }

  return event.status ? `상태: ${event.status}` : '도구 실행 완료';
};

const findLastAssistantIndex = (messages: Message[]): number => {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index].role === 'assistant') {
      return index;
    }
  }

  return -1;
};

const setLastAssistantContentIfEmpty = (messages: Message[], content: string): Message[] => {
  const assistantIndex = findLastAssistantIndex(messages);
  if (assistantIndex < 0 || messages[assistantIndex].content.trim()) {
    return messages;
  }

  const next = [...messages];
  next[assistantIndex] = {
    ...next[assistantIndex],
    content,
    evidenceFooter: undefined,
    timestamp: next[assistantIndex].timestamp ?? Date.now(),
  };

  return next;
};

const attachEvidenceFooterToLastAssistant = (
  messages: Message[],
  evidenceFooter: EvidenceFooter | undefined,
): Message[] => {
  if (!evidenceFooter) {
    return messages;
  }

  const assistantIndex = findLastAssistantIndex(messages);
  if (assistantIndex < 0) {
    return messages;
  }

  const next = [...messages];
  next[assistantIndex] = {
    ...next[assistantIndex],
    evidenceFooter,
  };

  return next;
};

const attachToolPlanToLastAssistant = (
  messages: Message[],
  toolPlan: ToolPlanFooter | undefined,
): Message[] => {
  if (!toolPlan) {
    return messages;
  }

  const assistantIndex = findLastAssistantIndex(messages);
  if (assistantIndex < 0) {
    return messages;
  }

  const next = [...messages];
  next[assistantIndex] = {
    ...next[assistantIndex],
    toolPlan,
  };

  return next;
};

const markLastAssistantFallback = (
  messages: Message[],
  gatewayContextDigest?: string,
): Message[] => {
  const assistantIndex = findLastAssistantIndex(messages);
  if (assistantIndex < 0) {
    return messages;
  }

  const next = [...messages];
  next[assistantIndex] = {
    ...next[assistantIndex],
    answerSource: 'gateway_fallback',
    fallbackAnswer: true,
    gatewayContextDigest: gatewayContextDigest || next[assistantIndex].gatewayContextDigest,
  };

  return next;
};

const markLastAssistantSource = (
  messages: Message[],
  answerSource: NonNullable<Message['answerSource']>,
  gatewayContextDigest?: string,
): Message[] => {
  const assistantIndex = findLastAssistantIndex(messages);
  if (assistantIndex < 0) {
    return messages;
  }

  const next = [...messages];
  next[assistantIndex] = {
    ...next[assistantIndex],
    answerSource,
    gatewayContextDigest: gatewayContextDigest || next[assistantIndex].gatewayContextDigest,
  };

  return next;
};

const markLastAssistantAnswerContract = (
  messages: Message[],
  answerContract?: string,
): Message[] => {
  if (!answerContract) {
    return messages;
  }

  const assistantIndex = findLastAssistantIndex(messages);
  if (assistantIndex < 0) {
    return messages;
  }

  const next = [...messages];
  next[assistantIndex] = {
    ...next[assistantIndex],
    answerContract,
  };

  return next;
};

const buildRecentContextMessages = (messages: Message[]): ChatContextMessage[] =>
  messages
    .filter((message) => message.content.trim())
    .slice(-MAX_RECENT_CONTEXT_MESSAGES)
    .map((message) => ({
      role: message.role,
      content: message.content.slice(0, 4000),
    }));

const formatMessageTime = (timestamp: number | undefined, language: UiLanguage): string => {
  if (!timestamp) {
    return '';
  }

  return new Intl.DateTimeFormat(languageLocale(language), {
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(timestamp));
};

const getAssistantConnectionState = (
  summary: ClusterSummary | null,
  summaryLoading: boolean,
  summaryError: string,
  status: AiopsRuntimeStatus | null,
  statusError: string,
): { label: string; tone: 'connected' | 'danger' | 'pending' } => {
  if (summaryError || statusError) {
    return {
      label: 'Gateway 또는 cluster 상태 확인 필요',
      tone: 'danger',
    };
  }

  if (summary && status) {
    return {
      label: `${summary.apiUrl || 'console proxy'} · Gateway 연결됨`,
      tone: 'connected',
    };
  }

  if (summary || status) {
    return {
      label: `${summary?.apiUrl || 'cluster'} · 연결 일부 확인됨`,
      tone: 'pending',
    };
  }

  return {
    label: summaryLoading ? '연결 확인 중' : 'Gateway 연결 대기',
    tone: 'pending',
  };
};

const mergeUploadedDocuments = (
  preferred: RagUploadedDocument[],
  fallback: RagUploadedDocument[],
): RagUploadedDocument[] => {
  const merged = new Map<string, RagUploadedDocument>();

  [...preferred, ...fallback].forEach((document) => {
    if (!merged.has(document.documentId)) {
      merged.set(document.documentId, document);
    }
  });

  return Array.from(merged.values());
};

const matchActionCandidatesForMessage = (
  content: string,
  candidates: AiopsActionCandidate[],
): AiopsActionCandidate[] => {
  const matched = candidates.filter((candidate) => {
    const name = candidate.target?.name;
    return Boolean(name) && content.includes(name!);
  });

  // Different findings (e.g. pod_crashloop and pod_restart_spike) can point at
  // the exact same target, each producing its own candidate id — dedupe by
  // target so the same remediation isn't offered as two separate buttons.
  const seenTargets = new Set<string>();
  return matched.filter((candidate) => {
    const target = candidate.target;
    const targetKey = `${target?.namespace}/${target?.kind}/${target?.name}`;
    if (seenTargets.has(targetKey)) {
      return false;
    }
    seenTargets.add(targetKey);
    return true;
  });
};

// Matches the "namespace/name" shape getRecordTargetLabel derives from a
// record's target, so a candidate's target and a record's target can be
// compared as the same session-tracked key.
const targetKeyFromParts = (namespace?: string, name?: string): string =>
  namespace ? `${namespace}/${name ?? ''}` : (name ?? '');

const conversationActionRefFromCandidate = (
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

const latestAnswerActionRecords = (
  aiopsStatus: AiopsRuntimeStatus | null,
  executionMode: AiopsExecutionMode,
  messageContent: string,
  messageAnchor: string | undefined,
  actionRefs: ConversationActionRef[],
): AiopsRecordView[] => {
  const records = aiopsStatus?.spec.records;
  if (!records) {
    return [];
  }

  const anchorRefs = messageAnchor
    ? actionRefs.filter((ref) => ref.messageAnchor === messageAnchor)
    : [];
  const mentionedRecordNames = new Set(
    Array.from(messageContent.matchAll(/\b(?:proposal|plan|approval|execution)-[a-z0-9-]+/gi))
      .map((match) => match[0].toLowerCase()),
  );

  if (anchorRefs.length === 0 && mentionedRecordNames.size === 0) {
    return [];
  }

  return collapseActionRecordsForDisplay(
    [...records.approvalDecisions, ...records.sealedActionPlans, ...records.actionProposals],
    aiopsStatus,
    executionMode,
  )
    .filter((record) => {
      const recordName = getRecordName(record).toLowerCase();
      if (mentionedRecordNames.has(recordName)) {
        return true;
      }

      return anchorRefs.some((ref) => {
        if (ref.recordName && getRecordName(record) === ref.recordName) {
          return true;
        }
        if (
          ref.planDigest &&
          (getPlanDigest(record) === ref.planDigest || getApprovalPlanDigest(record) === ref.planDigest)
        ) {
          return true;
        }
        return (
          ref.targetKey === getRecordTargetLabel(record) &&
          (!ref.toolName || ref.toolName === getActionRecordToolName(record))
        );
      });
    })
    .slice(0, 3);
};

type MessageFeedbackChoice = 'up' | 'down';

type MessageActionFooterProps = {
  copied: boolean;
  copiedLabel: string;
  copyLabel: string;
  feedback?: MessageFeedbackChoice;
  language: UiLanguage;
  onCopy: () => void;
  onEditForResend?: () => void;
  onFeedback?: (feedback: MessageFeedbackChoice) => void;
  role: Message['role'];
};

const messageActionLabels = (language: UiLanguage) =>
  language === 'en'
    ? {
        copy: 'Copy',
        copied: 'Copied',
        dislike: 'Bad response',
        edit: 'Edit and resend',
        feedbackCommentPlaceholder: 'Add a short note for the test log',
        feedbackCommentSaved: 'Saved',
        feedbackCommentSubmit: 'Save',
        like: 'Good response',
      }
    : {
        copy: '복사',
        copied: '복사됨',
        dislike: '좋지 않은 답변',
        edit: '수정해서 다시 보내기',
        feedbackCommentPlaceholder: '테스트 기록에 남길 의견을 짧게 입력',
        feedbackCommentSaved: '저장됨',
        feedbackCommentSubmit: '저장',
        like: '좋은 답변',
      };

const readStoredMessageFeedback = (): ChatFeedbackPayload[] => {
  if (typeof window === 'undefined') {
    return [];
  }

  try {
    const parsed = JSON.parse(window.localStorage.getItem(STORED_MESSAGE_FEEDBACK_KEY) || '[]');
    return Array.isArray(parsed) ? (parsed as ChatFeedbackPayload[]) : [];
  } catch {
    return [];
  }
};

const writeStoredMessageFeedback = (payload: ChatFeedbackPayload): void => {
  if (typeof window === 'undefined') {
    return;
  }

  const existing = readStoredMessageFeedback();
  const next = [
    payload,
    ...existing.filter((item) => item.messageId !== payload.messageId),
  ].slice(0, 200);
  window.localStorage.setItem(STORED_MESSAGE_FEEDBACK_KEY, JSON.stringify(next));
};

const removeStoredMessageFeedback = (messageId: string): void => {
  if (typeof window === 'undefined') {
    return;
  }

  const next = readStoredMessageFeedback().filter((item) => item.messageId !== messageId);
  window.localStorage.setItem(STORED_MESSAGE_FEEDBACK_KEY, JSON.stringify(next));
};

const MessageActionButton: React.FC<{
  active?: boolean;
  children: React.ReactNode;
  label: string;
  onClick: () => void;
  pressed?: boolean;
}> = ({ active = false, children, label, onClick, pressed }) => (
  <button
    aria-label={label}
    aria-pressed={pressed}
    className="komsco-ai__message-action-button"
    data-active={active ? 'true' : undefined}
    onClick={onClick}
    title={label}
    type="button"
  >
    {children}
  </button>
);

const MessageActionFooter: React.FC<MessageActionFooterProps> = ({
  copied,
  copiedLabel,
  copyLabel,
  feedback,
  language,
  onCopy,
  onEditForResend,
  onFeedback,
  role,
}) => {
  const labels = messageActionLabels(language);
  const copyButtonLabel = copied ? copiedLabel || labels.copied : copyLabel || labels.copy;

  if (role === 'user') {
    return (
      <div className="komsco-ai__message-actions" data-message-actions="user">
        {onEditForResend && (
          <MessageActionButton label={labels.edit} onClick={onEditForResend}>
            <CoolPencilIcon />
          </MessageActionButton>
        )}
        <MessageActionButton active={copied} label={copyButtonLabel} onClick={onCopy}>
          <CoolCopyIcon />
        </MessageActionButton>
      </div>
    );
  }

  if (role !== 'assistant') {
    return null;
  }

  return (
    <div className="komsco-ai__message-actions" data-message-actions="assistant">
      <MessageActionButton active={copied} label={copyButtonLabel} onClick={onCopy}>
        <CoolCopyIcon />
      </MessageActionButton>
      {onFeedback && (
        <>
          <MessageActionButton
            active={feedback === 'up'}
            label={labels.like}
            onClick={() => onFeedback('up')}
            pressed={feedback === 'up'}
          >
            <CoolThumbsUpIcon />
          </MessageActionButton>
          <MessageActionButton
            active={feedback === 'down'}
            label={labels.dislike}
            onClick={() => onFeedback('down')}
            pressed={feedback === 'down'}
          >
            <CoolThumbsDownIcon />
          </MessageActionButton>
        </>
      )}
    </div>
  );
};

const MessageFeedbackComment: React.FC<{
  comment?: string;
  feedback: MessageFeedbackChoice;
  language: UiLanguage;
  onSubmit: (comment: string) => void;
}> = ({ comment = '', feedback, language, onSubmit }) => {
  const labels = messageActionLabels(language);
  const [draft, setDraft] = React.useState(comment);

  React.useEffect(() => {
    setDraft(comment);
  }, [comment, feedback]);

  const trimmedDraft = draft.trim();
  const savedComment = comment.trim();
  const dirty = trimmedDraft !== savedComment;
  const prompt =
    language === 'en'
      ? feedback === 'down'
        ? 'What should be improved?'
        : 'What worked well?'
      : feedback === 'down'
        ? '무엇을 개선할까요?'
        : '무엇이 좋았나요?';

  return (
    <form
      className="komsco-ai__feedback-comment"
      onSubmit={(event) => {
        event.preventDefault();
        if (!dirty) {
          return;
        }
        onSubmit(trimmedDraft);
      }}
    >
      <label>
        <span>{prompt}</span>
        <input
          maxLength={1000}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={labels.feedbackCommentPlaceholder}
          value={draft}
        />
      </label>
      <button disabled={!dirty} type="submit">
        {dirty ? labels.feedbackCommentSubmit : labels.feedbackCommentSaved}
      </button>
    </form>
  );
};

const writeClipboardText = async (text: string): Promise<boolean> => {
  if (!text) {
    return false;
  }

  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // Fall through to the textarea copy path for local console/browser contexts.
    }
  }

  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.setAttribute('readonly', 'true');
  textarea.style.position = 'fixed';
  textarea.style.inset = '0 auto auto 0';
  textarea.style.opacity = '0';
  document.body.appendChild(textarea);
  textarea.select();
  try {
    return document.execCommand('copy');
  } finally {
    document.body.removeChild(textarea);
  }
};

const mergeStoredActiveConversationIntoHistory = (
  history: ConversationHistoryItem[],
  activeConversation: StoredActiveConversation | undefined,
  language: UiLanguage,
): ConversationHistoryItem[] => {
  if (!activeConversation?.messages.length) {
    return history;
  }

  const existing = history.find((conversation) => conversation.id === activeConversation.activeSessionId);
  const activeHistoryItem: ConversationHistoryItem = {
    id: activeConversation.activeSessionId,
    title: existing?.title || getConversationTitle(activeConversation.messages, language),
    updatedAt: Date.now(),
    conversationId: activeConversation.conversationId,
    messages: activeConversation.messages,
    actionRefs: activeConversation.actionRefs,
    actionTargetKeys: activeConversation.actionTargetKeys,
  };

  return [
    activeHistoryItem,
    ...history.filter((conversation) => conversation.id !== activeConversation.activeSessionId),
  ].slice(0, MAX_STORED_CONVERSATIONS);
};

const AssistantLauncher: React.FC<AssistantLauncherProps> = ({
  defaultOpen = false,
  draftPrompt,
  embedded = false,
  lockOpen = false,
  onRunComplete,
}) => {
  const [open, setOpen] = React.useState(defaultOpen || embedded || lockOpen);
  const [fullScreen, setFullScreen] = React.useState(false);
  const [input, setInput] = React.useState('');
  const [draftPageContext, setDraftPageContext] = React.useState<
    Record<string, unknown> | undefined
  >();
  const [pendingAttachments, setPendingAttachments] = React.useState<ImageAttachment[]>([]);
  const [attachmentError, setAttachmentError] = React.useState('');
  const [clusterSummary, setClusterSummary] = React.useState<ClusterSummary | null>(null);
  const [clusterSummaryError, setClusterSummaryError] = React.useState('');
  const [clusterSummaryLoading, setClusterSummaryLoading] = React.useState(false);
  const [authSubject, setAuthSubject] = React.useState<AuthSubject | null>(null);
  const [authSubjectError, setAuthSubjectError] = React.useState('');
  const [aiopsStatus, setAiopsStatus] = React.useState<AiopsRuntimeStatus | null>(null);
  // Guards against an out-of-order response (e.g. the 10s poller firing right
  // before a post-action refresh) silently overwriting fresher status with
  // stale data — only the response to the most recently issued request wins.
  const aiopsStatusRequestSeqRef = React.useRef(0);
  const [actionCandidates, setActionCandidates] = React.useState<AiopsActionCandidate[]>([]);
  const [busyActionCandidateId, setBusyActionCandidateId] = React.useState('');
  const busyActionCandidateIdRef = React.useRef('');
  const [autoProposeActions, setAutoProposeActions] = React.useState(false);
  const actionCandidatesRef = React.useRef<AiopsActionCandidate[]>([]);
  const autoProposeActionsAllowedRef = React.useRef(false);
  React.useEffect(() => {
    actionCandidatesRef.current = actionCandidates;
  }, [actionCandidates]);
  const [aiopsStatusError, setAiopsStatusError] = React.useState('');
  const [aiopsActionBusyId, setAiopsActionBusyId] = React.useState('');
  const aiopsActionBusyIdRef = React.useRef('');
  const [aiopsActionError, setAiopsActionError] = React.useState('');
  const [aiopsActionNotice, setAiopsActionNotice] = React.useState('');
  const [executionMode, setExecutionMode] = React.useState<AiopsExecutionMode>(
    DEFAULT_AIOPS_EXECUTION_MODE,
  );
  React.useEffect(() => {
    autoProposeActionsAllowedRef.current = executionMode === 'execute' && autoProposeActions;
  }, [executionMode, autoProposeActions]);
  const [dragActive, setDragActive] = React.useState(false);
  const initialActiveConversation = React.useMemo(readStoredActiveConversation, []);
  const initialUiLanguage = React.useMemo(readStoredUiLanguage, []);
  const initialConversationHistory = React.useMemo(
    () =>
      mergeStoredActiveConversationIntoHistory(
        readStoredConversationHistory(),
        initialActiveConversation,
        initialUiLanguage,
      ),
    [initialActiveConversation, initialUiLanguage],
  );
  const [messages, setMessages] = React.useState<Message[]>([]);
  const [conversationId, setConversationId] = React.useState<string | undefined>(undefined);
  const [activeSessionId, setActiveSessionId] = React.useState(createRunId);
  const [conversationHistory, setConversationHistory] = React.useState<ConversationHistoryItem[]>(
    initialConversationHistory,
  );
  const suppressNextHistoryAutosaveRef = React.useRef(false);
  const [historySidebarOpen, setHistorySidebarOpen] = React.useState(false);
  const [historyPanelView, setHistoryPanelView] = React.useState<HistoryPanelView>('chats');
  const [sessionActionTargetKeys, setSessionActionTargetKeys] = React.useState<Set<string>>(
    () => new Set(),
  );
  const [sessionActionRefs, setSessionActionRefs] = React.useState<ConversationActionRef[]>([]);
  const [uploadedDocuments, setUploadedDocuments] = React.useState<RagUploadedDocument[]>([]);
  const [uploadedDocumentsError, setUploadedDocumentsError] = React.useState('');
  const [uploadedDocumentsLoading, setUploadedDocumentsLoading] = React.useState(false);
  const [quickPromptMenuOpen, setQuickPromptMenuOpen] = React.useState(false);
  const [taskModeMenuOpen, setTaskModeMenuOpen] = React.useState(false);
  const [openHistoryMenuId, setOpenHistoryMenuId] = React.useState<string | null>(null);
  const [historyMenuAnchor, setHistoryMenuAnchor] = React.useState<{
    right: number;
    top: number;
  } | null>(null);
  const [renamingHistoryId, setRenamingHistoryId] = React.useState<string | null>(null);
  const [renamingHistoryTitle, setRenamingHistoryTitle] = React.useState('');
  const [assistantTaskMode, setAssistantTaskMode] = React.useState<AssistantTaskMode>('ask');
  const [panelResizeUnlocked, setPanelResizeUnlocked] = React.useState(false);
  const [panelSize, setPanelSize] = React.useState<{ height?: number; width?: number }>({});
  const [panelOffset, setPanelOffset] = React.useState({ x: 0, y: 0 });
  const [panelDragActive, setPanelDragActive] = React.useState(false);
  const [historyDrawerBounds, setHistoryDrawerBounds] = React.useState<{
    height?: number;
    left?: number;
    top?: number;
  }>({});
  const [stickToBottom, setStickToBottom] = React.useState(true);
  const [showScrollToBottom, setShowScrollToBottom] = React.useState(false);
  const [uiLanguage, setUiLanguage] = React.useState<UiLanguage>(initialUiLanguage);
  const [loading, setLoading] = React.useState(false);
  const [copiedMessageIndex, setCopiedMessageIndex] = React.useState<number | null>(null);
  const [previewAttachment, setPreviewAttachment] = React.useState<ImageAttachment | null>(null);
  const [, setProgressTick] = React.useState(0);
  const surfaceRef = React.useRef<HTMLDivElement | null>(null);
  const fabButtonRef = React.useRef<HTMLButtonElement | null>(null);
  const bodyRef = React.useRef<HTMLDivElement | null>(null);
  const bodyEndRef = React.useRef<HTMLDivElement | null>(null);
  const fileInputRef = React.useRef<HTMLInputElement | null>(null);
  const consumedDraftPromptIdRef = React.useRef('');
  const quickPromptMenuRef = React.useRef<HTMLDivElement | null>(null);
  const taskModeMenuRef = React.useRef<HTMLDivElement | null>(null);
  const historyMenuRef = React.useRef<HTMLDivElement | null>(null);
  const historyMenuPanelRef = React.useRef<HTMLDivElement | null>(null);
  const assistantTextQueueRef = React.useRef('');
  const messagesRef = React.useRef<Message[]>(messages);
  const assistantTypewriterTimerRef = React.useRef<number | undefined>();
  const assistantTextDrainResolversRef = React.useRef<Array<() => void>>([]);
  const chatAbortControllerRef = React.useRef<AbortController | null>(null);
  const stopRequestedRef = React.useRef(false);
  const panelDragFrameRef = React.useRef<number | undefined>();
  const panelDragNextOffsetRef = React.useRef<{ x: number; y: number } | null>(null);
  const actionExecutionAvailable = canUseActionExecution(aiopsStatus);
  const actionExecutionDisabledReason = getActionExecutionDisabledReason(aiopsStatus);
  const assistantConnection = getAssistantConnectionState(
    clusterSummary,
    clusterSummaryLoading,
    clusterSummaryError,
    aiopsStatus,
    aiopsStatusError,
  );
  const copy = UI_COPY[uiLanguage];
  const selectedTaskMode =
    ASSISTANT_TASK_MODES.find((item) => item.value === assistantTaskMode) ||
    ASSISTANT_TASK_MODES[0];
  const emptyStateCopy =
    TASK_MODE_EMPTY_COPY[assistantTaskMode]?.[uiLanguage] ?? TASK_MODE_EMPTY_COPY.ask[uiLanguage];

  const openAssistant = React.useCallback(() => {
    setOpen(true);
  }, []);

  React.useEffect(() => {
    const button = fabButtonRef.current;
    if (!button || embedded) {
      return undefined;
    }

    button.addEventListener('click', openAssistant);

    return () => {
      button.removeEventListener('click', openAssistant);
    };
  }, [embedded, openAssistant]);

  React.useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  React.useEffect(() => {
    writeStoredActiveConversation({
      activeSessionId,
      actionRefs: sessionActionRefs,
      actionTargetKeys: Array.from(sessionActionTargetKeys),
      conversationId,
      messages,
    });
  }, [activeSessionId, conversationId, messages, sessionActionRefs, sessionActionTargetKeys]);

  React.useEffect(
    () => () => {
      if (panelDragFrameRef.current !== undefined) {
        window.cancelAnimationFrame(panelDragFrameRef.current);
        panelDragFrameRef.current = undefined;
      }
      panelDragNextOffsetRef.current = null;
    },
    [],
  );

  React.useEffect(() => {
    writeStoredConversationHistory(conversationHistory);
  }, [conversationHistory]);

  React.useEffect(() => {
    writeStoredUiLanguage(uiLanguage);
  }, [uiLanguage]);

  React.useEffect(() => {
    if (!draftPrompt || consumedDraftPromptIdRef.current === draftPrompt.id) {
      return;
    }

    consumedDraftPromptIdRef.current = draftPrompt.id;
    setInput(draftPrompt.prompt);
    setDraftPageContext(draftPrompt.pageContext);
    setAssistantTaskMode(draftPrompt.taskMode ?? 'troubleshooting');
    const requestedExecutionMode = draftExecutionMode(draftPrompt.pageContext);
    if (requestedExecutionMode) {
      setExecutionMode(requestedExecutionMode);
    }
    setQuickPromptMenuOpen(false);
    setTaskModeMenuOpen(false);
    setOpen(true);
    window.setTimeout(() => {
      surfaceRef.current?.querySelector<HTMLTextAreaElement>('textarea')?.focus();
    }, 0);
  }, [draftPrompt]);

  const surfaceStyle = React.useMemo<React.CSSProperties>(() => {
    if (fullScreen) {
      return {};
    }

    const style = {} as React.CSSProperties & Record<string, string>;
    if (panelSize.height) {
      style.height = `${panelSize.height}px`;
    }
    if (panelSize.width) {
      style.width = `${panelSize.width}px`;
    }
    if (panelOffset.x || panelOffset.y) {
      style.transform = `translate(${panelOffset.x}px, ${panelOffset.y}px)`;
    }
    if (
      historySidebarOpen &&
      historyDrawerBounds.height &&
      historyDrawerBounds.left !== undefined &&
      historyDrawerBounds.top !== undefined
    ) {
      style['--komsco-history-height'] = `${historyDrawerBounds.height}px`;
      style['--komsco-history-left'] = `${historyDrawerBounds.left}px`;
      style['--komsco-history-top'] = `${historyDrawerBounds.top}px`;
    }
    return style;
  }, [
    fullScreen,
    historyDrawerBounds.height,
    historyDrawerBounds.left,
    historyDrawerBounds.top,
    historySidebarOpen,
    panelOffset.x,
    panelOffset.y,
    panelSize.height,
    panelSize.width,
  ]);
  const historySidebarStyle = React.useMemo<React.CSSProperties>(() => {
    if (
      fullScreen ||
      !historySidebarOpen ||
      !historyDrawerBounds.height ||
      historyDrawerBounds.left === undefined ||
      historyDrawerBounds.top === undefined
    ) {
      return {};
    }

    const style = {} as React.CSSProperties & Record<string, string>;
    style['--komsco-history-height'] = `${historyDrawerBounds.height}px`;
    style['--komsco-history-left'] = `${historyDrawerBounds.left}px`;
    style['--komsco-history-top'] = `${historyDrawerBounds.top}px`;
    return style;
  }, [
    fullScreen,
    historyDrawerBounds.height,
    historyDrawerBounds.left,
    historyDrawerBounds.top,
    historySidebarOpen,
  ]);

  const captureCurrentPanelSize = React.useCallback(() => {
    const surface = surfaceRef.current;
    if (!surface || fullScreen) {
      return;
    }

    const rect = surface.getBoundingClientRect();
    setPanelSize({
      height: Math.round(rect.height),
      width: Math.round(rect.width),
    });
  }, [fullScreen]);

  const togglePanelResizeLock = React.useCallback(() => {
    if (!panelResizeUnlocked) {
      captureCurrentPanelSize();
    }

    setPanelResizeUnlocked((value) => !value);
  }, [captureCurrentPanelSize, panelResizeUnlocked]);

  const startPanelDrag = React.useCallback(
    (event: React.MouseEvent<HTMLElement>) => {
      if (!panelResizeUnlocked || fullScreen || event.button !== 0) {
        return;
      }

      const target = event.target as HTMLElement | null;
      if (
        target?.closest(
          'button, a, input, textarea, select, [role="button"], .komsco-ai__header-status',
        )
      ) {
        return;
      }

      const surface = surfaceRef.current;
      if (!surface) {
        return;
      }

      event.preventDefault();
      event.stopPropagation();

      const rect = surface.getBoundingClientRect();
      const startX = event.clientX;
      const startY = event.clientY;
      const startOffset = panelOffset;
      const baseLeft = rect.left - startOffset.x;
      const baseTop = rect.top - startOffset.y;
      const minLeft = 8;
      const maxLeft = Math.max(minLeft, window.innerWidth - Math.min(rect.width, 180));
      const minTop = 8;
      const maxTop = Math.max(minTop, window.innerHeight - 120);
      const clamp = (value: number, min: number, max: number) =>
        Math.min(Math.max(value, min), max);
      const previousUserSelect = document.body.style.userSelect;
      const previousCursor = document.body.style.cursor;

      setPanelDragActive(true);
      document.body.style.userSelect = 'none';
      document.body.style.cursor = 'grabbing';

      const applyPanelOffset = (nextOffset: { x: number; y: number }) => {
        panelDragNextOffsetRef.current = nextOffset;
        if (panelDragFrameRef.current !== undefined) {
          return;
        }

        panelDragFrameRef.current = window.requestAnimationFrame(() => {
          panelDragFrameRef.current = undefined;
          const pendingOffset = panelDragNextOffsetRef.current;
          panelDragNextOffsetRef.current = null;
          if (!pendingOffset) {
            return;
          }

          setPanelOffset({
            x: Number(pendingOffset.x.toFixed(1)),
            y: Number(pendingOffset.y.toFixed(1)),
          });
        });
      };

      const handleMouseMove = (moveEvent: MouseEvent) => {
        const rawX = startOffset.x + moveEvent.clientX - startX;
        const rawY = startOffset.y + moveEvent.clientY - startY;
        applyPanelOffset({
          x: clamp(rawX, minLeft - baseLeft, maxLeft - baseLeft),
          y: clamp(rawY, minTop - baseTop, maxTop - baseTop),
        });
      };

      const stopPanelDrag = () => {
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', stopPanelDrag);
        if (panelDragFrameRef.current !== undefined) {
          window.cancelAnimationFrame(panelDragFrameRef.current);
          panelDragFrameRef.current = undefined;
        }
        const finalOffset = panelDragNextOffsetRef.current;
        panelDragNextOffsetRef.current = null;
        if (finalOffset) {
          setPanelOffset({
            x: Number(finalOffset.x.toFixed(1)),
            y: Number(finalOffset.y.toFixed(1)),
          });
        }
        document.body.style.userSelect = previousUserSelect;
        document.body.style.cursor = previousCursor;
        setPanelDragActive(false);
      };

      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', stopPanelDrag);
    },
    [fullScreen, panelOffset, panelResizeUnlocked],
  );

  const updateHistoryDrawerBounds = React.useCallback(() => {
    const surface = surfaceRef.current;
    if (!surface || !historySidebarOpen || fullScreen) {
      return;
    }

    const rect = surface.getBoundingClientRect();
    const next = {
      height: Math.round(rect.height),
      left: Math.max(8, Math.round(rect.left - HISTORY_DRAWER_WIDTH)),
      top: Math.round(rect.top),
    };

    setHistoryDrawerBounds((prev) =>
      prev.height === next.height && prev.left === next.left && prev.top === next.top ? prev : next,
    );
  }, [fullScreen, historySidebarOpen]);

  const startPanelResize = React.useCallback(
    (event: React.MouseEvent<HTMLElement>, direction: PanelResizeDirection) => {
      if (!panelResizeUnlocked || fullScreen) {
        return;
      }

      const surface = event.currentTarget.closest('.komsco-ai__surface') as HTMLElement | null;
      if (!surface) {
        return;
      }

      event.preventDefault();
      event.stopPropagation();

      const initialRect = surface.getBoundingClientRect();
      const parentRect = surface.parentElement?.getBoundingClientRect();
      const startX = event.clientX;
      const startY = event.clientY;
      const startOffset = panelOffset;
      const minHeight = 420;
      const viewportPadding = 8;
      const maxHeight = Math.max(minHeight, window.innerHeight - viewportPadding * 2);
      const minWidth = Math.min(460, Math.max(320, window.innerWidth - 32));
      const maxWidth = Math.max(
        minWidth,
        embedded
          ? Math.min(parentRect?.width || window.innerWidth - 32, window.innerWidth - 32)
          : window.innerWidth - viewportPadding * 2,
      );
      const clamp = (value: number, min: number, max: number) =>
        Math.min(Math.max(value, min), max);
      const previousUserSelect = document.body.style.userSelect;
      const previousCursor = document.body.style.cursor;
      const resizeCursor = direction.includes('n') && direction.includes('e')
        ? 'nesw-resize'
        : direction.includes('s') && direction.includes('w')
          ? 'nesw-resize'
          : direction.includes('n') && direction.includes('w')
            ? 'nwse-resize'
            : direction.includes('s') && direction.includes('e')
              ? 'nwse-resize'
              : direction.includes('n') || direction.includes('s')
                ? 'ns-resize'
                : 'ew-resize';

      document.body.style.userSelect = 'none';
      document.body.style.cursor = resizeCursor;

      const handleMouseMove = (moveEvent: MouseEvent) => {
        const deltaX = moveEvent.clientX - startX;
        const deltaY = moveEvent.clientY - startY;
        const widthMaxForDirection = direction.includes('e')
          ? Math.min(maxWidth, window.innerWidth - initialRect.left - viewportPadding)
          : direction.includes('w')
            ? Math.min(maxWidth, initialRect.right - viewportPadding)
            : maxWidth;
        const heightMaxForDirection = direction.includes('s')
          ? Math.min(maxHeight, window.innerHeight - initialRect.top - viewportPadding)
          : direction.includes('n')
            ? Math.min(maxHeight, initialRect.bottom - viewportPadding)
            : maxHeight;
        const nextHeight = direction.includes('n')
          ? clamp(initialRect.height - deltaY, minHeight, heightMaxForDirection)
          : direction.includes('s')
            ? clamp(initialRect.height + deltaY, minHeight, heightMaxForDirection)
            : initialRect.height;
        const nextWidth = direction.includes('w')
          ? clamp(initialRect.width - deltaX, minWidth, widthMaxForDirection)
          : direction.includes('e')
            ? clamp(initialRect.width + deltaX, minWidth, widthMaxForDirection)
            : initialRect.width;
        const nextOffset = {
          x:
            !embedded && direction.includes('e')
              ? startOffset.x + nextWidth - initialRect.width
              : startOffset.x,
          y:
            !embedded && direction.includes('s')
              ? startOffset.y + nextHeight - initialRect.height
              : startOffset.y,
        };

        setPanelSize({
          height: Math.round(nextHeight),
          width: Math.round(nextWidth),
        });
        if (!embedded && (direction.includes('e') || direction.includes('s'))) {
          setPanelOffset({
            x: Number(nextOffset.x.toFixed(1)),
            y: Number(nextOffset.y.toFixed(1)),
          });
        }
      };

      const stopPanelResize = () => {
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', stopPanelResize);
        document.body.style.userSelect = previousUserSelect;
        document.body.style.cursor = previousCursor;
      };

      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', stopPanelResize);
    },
    [embedded, fullScreen, panelOffset, panelResizeUnlocked],
  );

  React.useLayoutEffect(() => {
    if (!historySidebarOpen || fullScreen) {
      setHistoryDrawerBounds({});
      return undefined;
    }

    updateHistoryDrawerBounds();
    window.addEventListener('resize', updateHistoryDrawerBounds);
    window.addEventListener('scroll', updateHistoryDrawerBounds, true);

    const observer =
      typeof ResizeObserver === 'undefined'
        ? undefined
        : new ResizeObserver(updateHistoryDrawerBounds);
    if (surfaceRef.current) {
      observer?.observe(surfaceRef.current);
    }

    return () => {
      window.removeEventListener('resize', updateHistoryDrawerBounds);
      window.removeEventListener('scroll', updateHistoryDrawerBounds, true);
      observer?.disconnect();
    };
  }, [fullScreen, historySidebarOpen, updateHistoryDrawerBounds]);

  React.useEffect(() => {
    if (!quickPromptMenuOpen && !taskModeMenuOpen && !openHistoryMenuId) {
      return undefined;
    }

    const handleDocumentMouseDown = (event: MouseEvent) => {
      const target = event.target as Node | null;
      if (
        target &&
        (quickPromptMenuRef.current?.contains(target) ||
          taskModeMenuRef.current?.contains(target) ||
          historyMenuRef.current?.contains(target) ||
          historyMenuPanelRef.current?.contains(target))
      ) {
        return;
      }

      setQuickPromptMenuOpen(false);
      setTaskModeMenuOpen(false);
      setOpenHistoryMenuId(null);
    };

    const handleDocumentKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') {
        return;
      }

      setQuickPromptMenuOpen(false);
      setTaskModeMenuOpen(false);
      setOpenHistoryMenuId(null);
    };

    document.addEventListener('mousedown', handleDocumentMouseDown);
    document.addEventListener('keydown', handleDocumentKeyDown);

    return () => {
      document.removeEventListener('mousedown', handleDocumentMouseDown);
      document.removeEventListener('keydown', handleDocumentKeyDown);
    };
  }, [openHistoryMenuId, quickPromptMenuOpen, taskModeMenuOpen]);

  const handleExecutionModeChange = React.useCallback((mode: AiopsExecutionMode) => {
    setAiopsActionError('');
    setExecutionMode(mode);
  }, []);

  const getLatestAssistantMessageAnchor = React.useCallback((): string | undefined => {
    const index = findLastAssistantIndex(messagesRef.current);
    return index >= 0 ? actionAnchorForMessageIndex(index) : undefined;
  }, []);

  const upsertSessionActionRef = React.useCallback((ref: ConversationActionRef) => {
    setSessionActionRefs((prev) => {
      const next = [...prev];
      const existingIndex = next.findIndex(
        (item) =>
          item.id === ref.id ||
          (item.targetKey === ref.targetKey &&
            item.toolName === ref.toolName &&
            (item.planDigest === ref.planDigest || !item.planDigest || !ref.planDigest)),
      );

      if (existingIndex >= 0) {
        next[existingIndex] = {
          ...next[existingIndex],
          ...ref,
          messageAnchor: ref.messageAnchor ?? next[existingIndex].messageAnchor,
          updatedAt: Date.now(),
        };
        return next;
      }

      return [{ ...ref, updatedAt: Date.now() }, ...next].slice(0, 12);
    });
  }, []);

  const saveCurrentConversation = React.useCallback(
    (options: {
      preserveUpdatedAt?: boolean;
      promote?: boolean;
      snapshotConversationId?: string;
      snapshotMessages?: Message[];
    } = {}) => {
      const snapshotMessages = options.snapshotMessages ?? messages;
      const snapshotConversationId = options.snapshotConversationId ?? conversationId;

      if (snapshotMessages.length === 0) {
        return;
      }

      setConversationHistory((prev) => {
        const existing = prev.find((conversation) => conversation.id === activeSessionId);
        const item: ConversationHistoryItem = {
          id: activeSessionId,
          title: getConversationTitle(snapshotMessages, uiLanguage),
          updatedAt:
            options.preserveUpdatedAt && existing ? existing.updatedAt : Date.now(),
          conversationId: snapshotConversationId,
          messages: snapshotMessages,
          actionRefs: sessionActionRefs,
          actionTargetKeys: Array.from(sessionActionTargetKeys),
        };

        if (existing && options.promote === false) {
          return prev.map((conversation) =>
            conversation.id === activeSessionId ? item : conversation,
          );
        }

        return [item, ...prev.filter((conversation) => conversation.id !== activeSessionId)].slice(
          0,
          MAX_STORED_CONVERSATIONS,
        );
      });
    },
    [activeSessionId, conversationId, messages, sessionActionRefs, sessionActionTargetKeys, uiLanguage],
  );

  React.useEffect(() => {
    if (!loading) {
      if (suppressNextHistoryAutosaveRef.current) {
        suppressNextHistoryAutosaveRef.current = false;
        return;
      }
      saveCurrentConversation();
    }
  }, [loading, saveCurrentConversation]);

  const startNewConversation = React.useCallback(() => {
    if (loading && chatAbortControllerRef.current) {
      stopRequestedRef.current = true;
      chatAbortControllerRef.current.abort();
      chatAbortControllerRef.current = null;
      assistantTextQueueRef.current = '';
      setLoading(false);
    }

    saveCurrentConversation();
    setActiveSessionId(createRunId());
    setConversationId(undefined);
    setMessages([]);
    setSessionActionTargetKeys(new Set());
    setSessionActionRefs([]);
    setInput('');
    setPendingAttachments([]);
    setAttachmentError('');
    setAiopsActionError('');
    setAiopsActionNotice('');
    setQuickPromptMenuOpen(false);
    setTaskModeMenuOpen(false);
  }, [loading, saveCurrentConversation]);

  const loadConversation = React.useCallback(
    (conversation: ConversationHistoryItem) => {
      if (loading) {
        return;
      }

      saveCurrentConversation({ preserveUpdatedAt: true, promote: false });
      suppressNextHistoryAutosaveRef.current = true;
      setActiveSessionId(conversation.id);
      setConversationId(conversation.conversationId);
      setMessages(conversation.messages);
      setSessionActionTargetKeys(
        new Set([
          ...(conversation.actionTargetKeys ?? []),
          ...(conversation.actionRefs ?? []).map((actionRef) => actionRef.targetKey),
        ]),
      );
      setSessionActionRefs(conversation.actionRefs ?? []);
      setInput('');
      setPendingAttachments([]);
      setAttachmentError('');
      setQuickPromptMenuOpen(false);
      setTaskModeMenuOpen(false);
    },
    [loading, saveCurrentConversation],
  );

  const scrollToActionAnchor = React.useCallback((messageAnchor?: string) => {
    if (!messageAnchor) {
      return;
    }

    window.setTimeout(() => {
      const surface = surfaceRef.current;
      const target = Array.from(
        surface?.querySelectorAll<HTMLElement>('[data-action-anchor]') ?? [],
      ).find((element) => element.getAttribute('data-action-anchor') === messageAnchor);

      if (!target) {
        return;
      }

      target.scrollIntoView({ block: 'center', behavior: 'smooth' });
      target.classList.add('komsco-ai__message--action-highlight');
      window.setTimeout(() => {
        target.classList.remove('komsco-ai__message--action-highlight');
      }, 1800);
    }, 120);
  }, []);

  const handleHistoryActionRefSelect = React.useCallback(
    (conversation: ConversationHistoryItem, actionRef: ConversationActionRef) => {
      if (loading) {
        return;
      }

      setOpenHistoryMenuId(null);
      setHistoryPanelView('chats');

      if (conversation.id !== activeSessionId) {
        loadConversation(conversation);
      }

      scrollToActionAnchor(actionRef.messageAnchor);
    },
    [activeSessionId, loadConversation, loading, scrollToActionAnchor],
  );

  const deleteConversation = React.useCallback(
    (conversationHistoryId: string) => {
      setConversationHistory((prev) =>
        prev.filter((conversation) => conversation.id !== conversationHistoryId),
      );
      if (conversationHistoryId === activeSessionId) {
        startNewConversation();
      }
    },
    [activeSessionId, startNewConversation],
  );

  const renameConversation = React.useCallback((conversationHistoryId: string, title: string) => {
    const trimmed = title.trim();
    if (!trimmed) {
      return;
    }
    setConversationHistory((prev) =>
      prev.map((conversation) =>
        conversation.id === conversationHistoryId
          ? { ...conversation, title: trimmed }
          : conversation,
      ),
    );
  }, []);

  const scrollToBottom = React.useCallback((behavior: ScrollBehavior = 'smooth') => {
    const body = bodyRef.current;
    if (body) {
      body.scrollTo({ top: body.scrollHeight, behavior });
    }
    bodyEndRef.current?.scrollIntoView({ block: 'end', behavior });
  }, []);

  const handleConversationScroll = React.useCallback((event: React.UIEvent<HTMLDivElement>) => {
    const target = event.currentTarget;
    const distanceToBottom = target.scrollHeight - target.scrollTop - target.clientHeight;
    const nearBottom = distanceToBottom <= SCROLL_BOTTOM_THRESHOLD_PX;

    setStickToBottom(nearBottom);
    setShowScrollToBottom(!nearBottom);
  }, []);

  React.useEffect(() => {
    if (stickToBottom) {
      scrollToBottom('auto');
      setShowScrollToBottom(false);
    } else {
      setShowScrollToBottom(true);
    }
  }, [loading, messages, scrollToBottom, stickToBottom]);

  React.useEffect(() => {
    if (!loading) {
      return undefined;
    }

    const timer = window.setInterval(() => {
      setProgressTick((value) => value + 1);
    }, 1000);

    return () => window.clearInterval(timer);
  }, [loading]);

  React.useEffect(() => {
    if (!previewAttachment) {
      return undefined;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setPreviewAttachment(null);
      }
    };

    window.addEventListener('keydown', handleKeyDown);

    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [previewAttachment]);

  React.useEffect(() => {
    if (!open) {
      return undefined;
    }

    let disposed = false;

    const loadSummary = async () => {
      setClusterSummaryLoading(true);
      const seq = ++aiopsStatusRequestSeqRef.current;
      const [summaryResult, statusResult, consoleUserResult] = await Promise.allSettled([
        fetchClusterSummary(),
        fetchAiopsStatus(),
        fetchConsoleUserSubject(),
      ]);
      if (disposed) {
        return;
      }
      const isLatestStatusRequest = seq === aiopsStatusRequestSeqRef.current;

      if (summaryResult.status === 'fulfilled') {
        setClusterSummary(summaryResult.value);
        setClusterSummaryError('');
      } else {
        setClusterSummaryError(
          summaryResult.reason instanceof Error
            ? summaryResult.reason.message
            : 'Cluster summary request failed.',
        );
      }

      if (isLatestStatusRequest) {
        if (statusResult.status === 'fulfilled') {
          setAiopsStatus(statusResult.value);
          setAiopsStatusError('');
          const subject = statusResult.value.spec.subject;
          if (subject) {
            setAuthSubject(subject);
            setAuthSubjectError('');
          } else if (consoleUserResult.status === 'fulfilled') {
            setAuthSubject(consoleUserResult.value);
            setAuthSubjectError('');
          } else {
            setAuthSubject(null);
            setAuthSubjectError('Subject not returned by status endpoint.');
          }
        } else {
          setAiopsStatusError(
            statusResult.reason instanceof Error
              ? statusResult.reason.message
              : 'AIOps status request failed.',
          );
          if (consoleUserResult.status === 'fulfilled') {
            setAuthSubject(consoleUserResult.value);
            setAuthSubjectError('');
          } else {
            setAuthSubject(null);
            setAuthSubjectError(
              statusResult.reason instanceof Error
                ? statusResult.reason.message
                : 'Auth subject request failed.',
            );
          }
        }
      }

      setClusterSummaryLoading(false);
    };

    void loadSummary();
    const timer = window.setInterval(() => {
      void loadSummary();
    }, CLUSTER_SUMMARY_REFRESH_MS);

    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, [open]);

  React.useEffect(() => {
    if (!open) {
      return undefined;
    }

    let disposed = false;

    const loadActionCandidates = async () => {
      try {
        const summary = await fetchActionCandidates();
        if (!disposed) {
          setActionCandidates(summary.spec?.candidates ?? []);
        }
      } catch {
        // Best-effort: the "조치 계획 생성" button simply won't appear if this fails.
      }
    };

    void loadActionCandidates();
    const timer = window.setInterval(() => {
      void loadActionCandidates();
    }, CLUSTER_SUMMARY_REFRESH_MS);

    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, [open]);

  React.useEffect(() => {
    if (!open || !historySidebarOpen || historyPanelView !== 'uploads') {
      return undefined;
    }

    let disposed = false;

    const loadUploadedDocuments = async () => {
      setUploadedDocumentsLoading(true);
      try {
        const payload = await fetchUploadedRagDocuments();
        if (disposed) {
          return;
        }
        const uploadStatus = payload.spec.status;
        const serverDocuments = payload.spec.documents ?? [];
        setUploadedDocuments((prev) => mergeUploadedDocuments(serverDocuments, prev));
        setUploadedDocumentsError(
          uploadStatus === 'collected' || uploadStatus === 'empty'
            ? ''
            : (payload.spec.reason ?? copy.uploadedDocsError),
        );
      } catch (error) {
        if (!disposed) {
          setUploadedDocumentsError(
            error instanceof Error ? error.message : copy.uploadedDocsError,
          );
        }
      } finally {
        if (!disposed) {
          setUploadedDocumentsLoading(false);
        }
      }
    };

    void loadUploadedDocuments();
    return () => {
      disposed = true;
    };
  }, [copy.uploadedDocsError, historyPanelView, historySidebarOpen, open]);

  const refreshAiopsRuntimeStatus = React.useCallback(async () => {
    const seq = ++aiopsStatusRequestSeqRef.current;
    try {
      const status = await fetchAiopsStatus();
      if (seq !== aiopsStatusRequestSeqRef.current) {
        return;
      }

      setAiopsStatus(status);
      setAiopsStatusError('');
    } catch (error) {
      if (seq !== aiopsStatusRequestSeqRef.current) {
        return;
      }
      setAiopsStatusError(error instanceof Error ? error.message : 'AIOps status request failed.');
    }
  }, []);

  const updateLightspeedStatus = React.useCallback((updates: LightspeedStatusUpdate) => {
    setAiopsStatus((prev) => {
      const base = prev ?? createPendingAiopsStatus();
      const safetyContract =
        base.spec.safetyContract ?? createPendingAiopsStatus().spec.safetyContract!;
      const currentStatus = safetyContract.lightspeedStatus ?? {};

      return {
        ...base,
        spec: {
          ...base.spec,
          safetyContract: {
            ...safetyContract,
            lightspeedStatus: {
              ...currentStatus,
              ...updates,
            },
          },
        },
      };
    });
  }, []);

  const handleAiopsAction = React.useCallback(
    async (record: AiopsRecordView, action: AiopsRecordAction) => {
      if (action.disabledReason) {
        setAiopsActionError(action.disabledReason);
        setAiopsActionNotice('');
        return;
      }
      if (!executionModeAllowsActions(executionMode)) {
        setAiopsActionError(
          '읽기 전용 모드에서는 승인·실행을 만들지 않습니다. 실행하려면 실행 가능 또는 실행 무제한을 선택하세요.',
        );
        return;
      }

      const actionId = `${action.step}:${getRecordName(record)}`;

      if (aiopsActionBusyIdRef.current) {
        return;
      }
      aiopsActionBusyIdRef.current = actionId;
      setAiopsActionBusyId(actionId);
      setAiopsActionError('');
      setAiopsActionNotice('');

      try {
        if (action.step === 'create-plan') {
          const proposalId = getRecordName(record);
          if (!proposalId) {
            throw new Error('Action proposal id is missing.');
          }
          const plan = await createActionPlan(proposalId);
          setAiopsActionNotice('Action plan을 생성했습니다.');
          const targetKey = getRecordTargetLabel(record);
          setSessionActionTargetKeys((prev) => new Set(prev).add(targetKey));
          upsertSessionActionRef(
            conversationActionRefFromRecord(
              plan,
              executionMode,
              getLatestAssistantMessageAnchor(),
            ),
          );
        }

        if (action.step === 'approve-plan') {
          const planId = getRecordName(record);
          const planDigest = getPlanDigest(record);
          if (!planId || !planDigest) {
            throw new Error('Action plan id 또는 digest가 없습니다.');
          }
          const approval = await approveActionPlan(planId, planDigest);
          setAiopsActionNotice('Action plan을 승인했습니다.');
          upsertSessionActionRef(
            conversationActionRefFromRecord(
              approval,
              executionMode,
              getLatestAssistantMessageAnchor(),
            ),
          );
        }

        if (action.step === 'approve-execute-plan') {
          const planId = getRecordName(record);
          const planDigest = getPlanDigest(record);
          if (!planId || !planDigest) {
            throw new Error('Action plan id 또는 digest가 없습니다.');
          }
          const approval = await approveActionPlan(planId, planDigest, 'lab-auto-unrestricted');
          const approvalId = getRecordName(approval);
          if (!approvalId) {
            throw new Error('자동 승인 id가 없습니다.');
          }
          const execution = await executeApprovedAction(approvalId, planId, planDigest);
          setAiopsActionNotice('실행 무제한 모드로 자동 승인 후 실행했습니다.');
          upsertSessionActionRef(
            conversationActionRefFromRecord(
              execution,
              executionMode,
              getLatestAssistantMessageAnchor(),
            ),
          );
        }

        if (action.step === 'reject-plan') {
          const planId = getRecordName(record);
          const planDigest = getPlanDigest(record);
          if (!planId || !planDigest) {
            throw new Error('Action plan id 또는 digest가 없습니다.');
          }
          const rejection = await rejectActionPlan(planId, planDigest);
          setAiopsActionNotice('Action plan을 거절 기록했습니다.');
          upsertSessionActionRef(
            conversationActionRefFromRecord(
              rejection,
              executionMode,
              getLatestAssistantMessageAnchor(),
            ),
          );
        }

        if (action.step === 'execute-approval') {
          const approvalId = getApprovalId(record);
          const planDigest = getApprovalPlanDigest(record);
          const plan = findPlanByDigest(
            aiopsStatus?.spec.records.sealedActionPlans ?? [],
            planDigest,
          );
          const planId = plan ? getRecordName(plan) : '';
          if (!approvalId || !planId || !planDigest) {
            throw new Error('Approval 또는 연결된 action plan 정보가 없습니다.');
          }
          const execution = await executeApprovedAction(approvalId, planId, planDigest);
          setAiopsActionNotice('승인된 조치를 실행했습니다.');
          upsertSessionActionRef(
            conversationActionRefFromRecord(
              execution,
              executionMode,
              getLatestAssistantMessageAnchor(),
            ),
          );
        }

        await refreshAiopsRuntimeStatus();
      } catch (error) {
        setAiopsActionError(aiopsActionErrorMessage(error));
      } finally {
        aiopsActionBusyIdRef.current = '';
        setAiopsActionBusyId('');
      }
    },
    [aiopsStatus, executionMode, getLatestAssistantMessageAnchor, refreshAiopsRuntimeStatus, upsertSessionActionRef],
  );

  const handleCreateActionPlanFromChat = React.useCallback(
    async (candidate: AiopsActionCandidate) => {
      if (busyActionCandidateIdRef.current) {
        return;
      }
      busyActionCandidateIdRef.current = candidate.id;
      setBusyActionCandidateId(candidate.id);
      setAiopsActionError('');
      setAiopsActionNotice('');

      try {
        const result = await createActionCandidatePlan(candidate);
        setAiopsActionNotice('조치 계획을 생성했습니다.');
        const targetKey = targetKeyFromParts(candidate.target?.namespace, candidate.target?.name);
        setSessionActionTargetKeys((prev) => new Set(prev).add(targetKey));
        upsertSessionActionRef(
          result.spec?.plan
            ? conversationActionRefFromRecord(
                result.spec.plan,
                executionMode,
                getLatestAssistantMessageAnchor(),
              )
            : conversationActionRefFromCandidate(candidate, getLatestAssistantMessageAnchor()),
        );
        await refreshAiopsRuntimeStatus();
      } catch (error) {
        setAiopsActionError(aiopsActionErrorMessage(error));
      } finally {
        busyActionCandidateIdRef.current = '';
        setBusyActionCandidateId('');
      }
    },
    [executionMode, getLatestAssistantMessageAnchor, refreshAiopsRuntimeStatus, upsertSessionActionRef],
  );

  const appendAssistantText = React.useCallback((content: string) => {
    setMessages((prev) => {
      const assistantIndex = findLastAssistantIndex(prev);
      if (assistantIndex < 0) {
        return [...prev, { role: 'assistant', content, timestamp: Date.now() }];
      }

      const next = [...prev];
      next[assistantIndex] = {
        ...next[assistantIndex],
        content: next[assistantIndex].content + content,
        timestamp: next[assistantIndex].timestamp ?? Date.now(),
      };

      return next;
    });
  }, []);

  const clearAssistantTypewriterTimer = React.useCallback(() => {
    if (assistantTypewriterTimerRef.current === undefined) {
      return;
    }

    window.clearTimeout(assistantTypewriterTimerRef.current);
    assistantTypewriterTimerRef.current = undefined;
  }, []);

  const flushAssistantTextQueueNow = React.useCallback(() => {
    clearAssistantTypewriterTimer();

    const queuedText = assistantTextQueueRef.current;
    if (!queuedText) {
      return;
    }

    assistantTextQueueRef.current = '';
    appendAssistantText(queuedText);
    const resolvers = assistantTextDrainResolversRef.current;
    assistantTextDrainResolversRef.current = [];
    resolvers.forEach((resolve) => resolve());
  }, [appendAssistantText, clearAssistantTypewriterTimer]);

  const scheduleAssistantTextDrain = React.useCallback(() => {
    if (assistantTypewriterTimerRef.current !== undefined) {
      return;
    }

    const drain = () => {
      const queuedText = assistantTextQueueRef.current;
      if (!queuedText) {
        assistantTypewriterTimerRef.current = undefined;
        const resolvers = assistantTextDrainResolversRef.current;
        assistantTextDrainResolversRef.current = [];
        resolvers.forEach((resolve) => resolve());
        return;
      }

      const chunk = queuedText.slice(0, ASSISTANT_TYPEWRITER_CHARS);
      assistantTextQueueRef.current = queuedText.slice(chunk.length);
      appendAssistantText(chunk);
      assistantTypewriterTimerRef.current = window.setTimeout(
        drain,
        ASSISTANT_TYPEWRITER_INTERVAL_MS,
      );
    };

    assistantTypewriterTimerRef.current = window.setTimeout(drain, 0);
  }, [appendAssistantText]);

  const enqueueAssistantText = React.useCallback(
    (content: string) => {
      assistantTextQueueRef.current += content;
      scheduleAssistantTextDrain();
    },
    [scheduleAssistantTextDrain],
  );

  const waitForAssistantTextQueue = React.useCallback(async () => {
    if (!assistantTextQueueRef.current && assistantTypewriterTimerRef.current === undefined) {
      return;
    }

    await new Promise<void>((resolve) => {
      assistantTextDrainResolversRef.current.push(resolve);
      scheduleAssistantTextDrain();
    });
  }, [scheduleAssistantTextDrain]);

  React.useEffect(
    () => () => {
      clearAssistantTypewriterTimer();
      const resolvers = assistantTextDrainResolversRef.current;
      assistantTextDrainResolversRef.current = [];
      resolvers.forEach((resolve) => resolve());
    },
    [clearAssistantTypewriterTimer],
  );

  const copyMessage = React.useCallback((message: Message, index: number) => {
    const redactedContent = redactSensitiveText(
      stripDefaultEvidenceAppendix(message.content).trim(),
    );
    const text = `${redactedContent}${buildEvidenceCopyText(message.evidenceFooter)}`.trim();
    if (!text) {
      return;
    }

    void writeClipboardText(text).then((copied) => {
      if (!copied) {
        return;
      }
      setCopiedMessageIndex(index);
      window.setTimeout(() => {
        setCopiedMessageIndex((current) => (current === index ? null : current));
      }, 1400);
    });
  }, []);

  const editMessageForResend = React.useCallback((message: Message) => {
    const draft = stripDefaultEvidenceAppendix(message.content).trim();
    if (!draft) {
      return;
    }
    setInput(draft);
    setPendingAttachments(message.attachments ?? []);
    window.setTimeout(() => {
      surfaceRef.current?.querySelector<HTMLTextAreaElement>('textarea')?.focus();
    }, 0);
  }, []);

  const persistMessageFeedback = React.useCallback(
    (
      index: number,
      message: Message,
      feedback: MessageFeedbackChoice,
      optionalComment?: string,
    ) => {
      const messageId = `${activeSessionId}:${index}:${message.timestamp ?? 'pending'}`;
      const submittedAt = new Date().toISOString();
      const payload: ChatFeedbackPayload = {
        answerContract: message.answerContract,
        answerSource: message.answerSource,
        conversationId: conversationId ?? activeSessionId,
        feedbackId: `feedback-${messageId.replace(/[^a-zA-Z0-9-]+/g, '-')}`,
        intent: message.toolPlan?.taskType,
        messageId,
        mode: executionMode,
        optionalComment: optionalComment?.trim() || undefined,
        rating: feedback,
        route: window.location.pathname,
        timestamp: submittedAt,
      };

      writeStoredMessageFeedback(payload);
      void submitChatFeedback(payload).catch((error) => {
        // Feedback is already kept locally; gateway persistence is best-effort during local tests.
        // eslint-disable-next-line no-console
        console.warn('AIOps feedback persistence failed', error);
      });
    },
    [activeSessionId, conversationId, executionMode],
  );

  const toggleMessageFeedback = React.useCallback(
    (index: number, feedback: MessageFeedbackChoice) => {
      const currentMessage = messagesRef.current[index];
      const messageId = `${activeSessionId}:${index}:${currentMessage?.timestamp ?? 'pending'}`;
      const clearingFeedback =
        currentMessage?.role === 'assistant' && currentMessage.feedback === feedback;

      setMessages((prev) => {
        const message = prev[index];
        if (!message || message.role !== 'assistant') {
          return prev;
        }
        const next = [...prev];
        const nextMessage = { ...message };
        if (nextMessage.feedback === feedback) {
          delete nextMessage.feedback;
          delete nextMessage.feedbackAt;
          delete nextMessage.feedbackComment;
        } else {
          const previousFeedback = nextMessage.feedback;
          nextMessage.feedback = feedback;
          nextMessage.feedbackAt = Date.now();
          if (previousFeedback && previousFeedback !== feedback) {
            delete nextMessage.feedbackComment;
          }
        }
        next[index] = nextMessage;
        return next;
      });

      if (!currentMessage || currentMessage.role !== 'assistant') {
        return;
      }

      if (clearingFeedback) {
        removeStoredMessageFeedback(messageId);
        return;
      }

      persistMessageFeedback(
        index,
        currentMessage,
        feedback,
        currentMessage.feedback && currentMessage.feedback !== feedback
          ? undefined
          : currentMessage.feedbackComment,
      );
    },
    [activeSessionId, persistMessageFeedback],
  );

  const submitMessageFeedbackComment = React.useCallback(
    (index: number, comment: string) => {
      const currentMessage = messagesRef.current[index];
      if (!currentMessage || currentMessage.role !== 'assistant' || !currentMessage.feedback) {
        return;
      }

      const normalizedComment = comment.trim();
      setMessages((prev) => {
        const message = prev[index];
        if (!message || message.role !== 'assistant') {
          return prev;
        }
        const next = [...prev];
        next[index] = {
          ...message,
          feedbackComment: normalizedComment || undefined,
        };
        return next;
      });

      persistMessageFeedback(index, currentMessage, currentMessage.feedback, normalizedComment);
    },
    [persistMessageFeedback],
  );

  const upsertProgressStep = React.useCallback((step: ProgressStep) => {
    setMessages((prev) => {
      const assistantIndex = findLastAssistantIndex(prev);
      if (assistantIndex < 0) {
        return prev;
      }

      const next = [...prev];
      const message = next[assistantIndex];
      const progressSteps = [...(message.progressSteps ?? [])];
      const existingIndex = progressSteps.findIndex((item) => item.id === step.id);

      if (existingIndex >= 0) {
        progressSteps[existingIndex] = {
          ...progressSteps[existingIndex],
          ...step,
          startedAt: progressSteps[existingIndex].startedAt,
        };
      } else {
        progressSteps.push(step);
      }

      next[assistantIndex] = {
        ...message,
        progressSteps,
      };

      return next;
    });
  }, []);

  const markRunningProgressFailed = React.useCallback((summary: string) => {
    setMessages((prev) => {
      const assistantIndex = findLastAssistantIndex(prev);
      if (assistantIndex < 0) {
        return prev;
      }

      const next = [...prev];
      const message = next[assistantIndex];

      next[assistantIndex] = {
        ...message,
        progressSteps: message.progressSteps?.map((step) => {
          if (step.status !== 'running') {
            return step;
          }

          const endedAt = Date.now();

          return {
            ...step,
            detail: step.detail || summary,
            elapsedMs: endedAt - step.startedAt,
            endedAt,
            status: 'failed',
            summary,
          };
        }),
      };

      return next;
    });
  }, []);

  const finalizeRunningProgressSteps = React.useCallback((summary = '응답 완료') => {
    setMessages((prev) => {
      const assistantIndex = findLastAssistantIndex(prev);
      if (assistantIndex < 0) {
        return prev;
      }

      const next = [...prev];
      const message = next[assistantIndex];

      next[assistantIndex] = {
        ...message,
        progressSteps: message.progressSteps?.map((step) => {
          if (step.status !== 'running') {
            return step;
          }

          const endedAt = Date.now();

          return {
            ...step,
            detail: step.detail || summary,
            elapsedMs: endedAt - step.startedAt,
            endedAt,
            status: 'completed',
            summary,
          };
        }),
      };

      return next;
    });
  }, []);

  const addImageFiles = React.useCallback(
    async (files: File[]) => {
      const imageFiles = files.filter((file) => ACCEPTED_IMAGE_MIME_TYPES.has(file.type));
      const documentFiles = files.filter(
        (file) => !ACCEPTED_IMAGE_MIME_TYPES.has(file.type) && isRagDocumentFile(file),
      );

      if (imageFiles.length === 0 && documentFiles.length === 0) {
        setAttachmentError(
          '지원 형식: PNG/JPEG/WebP/GIF 이미지 또는 PDF/DOCX/PPTX/XLSX/TXT/MD/JSON/YAML/log 문서입니다.',
        );
        return;
      }

      const unsupportedCount = files.length - imageFiles.length - documentFiles.length;
      if (unsupportedCount > 0) {
        setAttachmentError('일부 파일은 지원 형식이 아니라 제외했습니다.');
      }

      if (imageFiles.length > 0) {
        const nextCount = pendingAttachments.length + imageFiles.length;
        if (nextCount > MAX_IMAGE_ATTACHMENTS) {
          setAttachmentError(`이미지는 최대 ${MAX_IMAGE_ATTACHMENTS}개까지 첨부할 수 있습니다.`);
          return;
        }

        const tooLarge = imageFiles.find((file) => file.size > MAX_IMAGE_ATTACHMENT_BYTES);
        if (tooLarge) {
          setAttachmentError(
            `${tooLarge.name} 파일이 너무 큽니다. 이미지당 최대 ${formatFileSize(
              MAX_IMAGE_ATTACHMENT_BYTES,
            )}까지 가능합니다.`,
          );
          return;
        }

        const currentTotal = pendingAttachments.reduce((total, item) => total + item.size, 0);
        const nextTotal = imageFiles.reduce((total, file) => total + file.size, currentTotal);
        if (nextTotal > MAX_IMAGE_ATTACHMENT_TOTAL_BYTES) {
          setAttachmentError(
            `첨부 이미지 합계는 최대 ${formatFileSize(MAX_IMAGE_ATTACHMENT_TOTAL_BYTES)}까지 가능합니다.`,
          );
          return;
        }
      }

      const tooLargeDocument = documentFiles.find(
        (file) => file.size > MAX_RAG_DOCUMENT_UPLOAD_BYTES,
      );
      if (tooLargeDocument) {
        setAttachmentError(
          `${tooLargeDocument.name} 문서가 너무 큽니다. 문서당 최대 ${formatFileSize(
            MAX_RAG_DOCUMENT_UPLOAD_BYTES,
          )}까지 가능합니다.`,
        );
        return;
      }

      try {
        if (imageFiles.length > 0) {
          const attachments = await Promise.all(imageFiles.map(readImageAttachment));
          setPendingAttachments((prev) => [...prev, ...attachments]);
        }

        if (documentFiles.length > 0) {
          const uploaded = await Promise.all(
            documentFiles.map(async (file) => {
              const commonMetadata = {
                labels: { source: 'chat-attachment', version: 'v0.1.5' },
                namespace: 'cywell-aiops',
                runId: activeSessionId,
                sourceType: 'user-upload',
                version: 'v0.1.5',
              };
              const result = shouldUploadRagDocumentAsFile(file)
                ? await uploadRagDocumentFile(file, commonMetadata)
                : await uploadRagDocument({
                    ...commonMetadata,
                    content: await readRagDocumentContent(file),
                    mimeType: file.type || 'text/plain',
                    name: file.name,
                  });
              if (result.spec.status !== 'persisted') {
                throw new Error(
                  result.spec.reason || `${file.name} 문서를 RAG 저장소에 등록하지 못했습니다.`,
                );
              }
              return result.spec.document;
            }),
          );
          setUploadedDocuments((prev) => {
            return mergeUploadedDocuments(uploaded, prev);
          });
          setHistoryPanelView('uploads');
          setHistorySidebarOpen(true);
        }

        setAttachmentError('');
      } catch (error) {
        setAttachmentError(error instanceof Error ? error.message : '파일을 처리하지 못했습니다.');
      }
    },
    [activeSessionId, pendingAttachments],
  );

  const removeAttachment = React.useCallback((id: string) => {
    setPendingAttachments((prev) => prev.filter((item) => item.id !== id));
    setAttachmentError('');
  }, []);

  const handleFileInputChange = React.useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(event.currentTarget.files ?? []);

      void addImageFiles(files);
      event.currentTarget.value = '';
    },
    [addImageFiles],
  );

  const handlePaste = React.useCallback(
    (event: React.ClipboardEvent<HTMLTextAreaElement>) => {
      const files = Array.from(event.clipboardData.files ?? []);
      const hasImage = files.some((file) => ACCEPTED_IMAGE_MIME_TYPES.has(file.type));

      if (!hasImage) {
        return;
      }

      event.preventDefault();
      void addImageFiles(files);
    },
    [addImageFiles],
  );

  const handleDrop = React.useCallback(
    (event: React.DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      setDragActive(false);
      void addImageFiles(Array.from(event.dataTransfer.files ?? []));
    },
    [addImageFiles],
  );

  const send = React.useCallback(
    async (prompt?: string) => {
      const question = (prompt ?? input).trim();
      const attachments = [...pendingAttachments];
      const activeDraftPageContext = draftPageContext;
      const requestExecutionMode = executionMode;

      if ((!question && attachments.length === 0) || loading) {
        return;
      }

      setStickToBottom(true);
      setShowScrollToBottom(false);
      setInput('');
      setPendingAttachments([]);
      setDraftPageContext(undefined);
      setAttachmentError('');
      setQuickPromptMenuOpen(false);
      setTaskModeMenuOpen(false);
      flushReactSync(() => setLoading(true));
      const loadingStartedAt = Date.now();
      flushAssistantTextQueueNow();
      window.setTimeout(() => scrollToBottom('auto'), 0);
      const recentMessages = buildRecentContextMessages(messages);
      const messageTimestamp = Date.now();
      setMessages((prev) => [
        ...prev,
        { role: 'user', attachments, content: question, timestamp: messageTimestamp },
        { role: 'assistant', content: '', progressSteps: [] },
      ]);

      const abortController = new AbortController();
      chatAbortControllerRef.current = abortController;
      stopRequestedRef.current = false;

      try {
        await new Promise((resolve) => window.setTimeout(resolve, 0));
        const runId = createRunId();
        const pageContext = {
          ...buildConsolePageContext(),
          aiopsExecutionMode: requestExecutionMode,
          aiopsDemoCycle: activeDraftPageContext,
          aiopsTaskMode: assistantTaskMode,
          aiopsTaskModeLabel: selectedTaskMode.label,
        };
        const activeStepIdsByName = new Map<string, string>();
        const activeStepStartedAt = new Map<string, number>();
        const gatewayPrepDetails: string[] = [];
        let gatewayPrepStartedAt: number | undefined;
        let responseWaitStartedAt: number | undefined;
        let responseWaitStepId: string | undefined;
        let responseWaitSequence = 0;
        let answerStreamStartedAt: number | undefined;
        let runLoopStartedAt: number | undefined;
        let runCompleted = false;
        let fallbackAnswerSeen = false;
        let clarificationAnswerSeen = false;
        let lightspeedStageSeen = false;
        let stepSequence = 0;

        const upsertGatewayPrepStep = (status: ProgressStatus) => {
          const now = Date.now();
          const startedAt = gatewayPrepStartedAt ?? now;

          gatewayPrepStartedAt = startedAt;
          upsertProgressStep({
            detail: gatewayPrepDetails.join('\n') || '사용자 권한과 요청 본문을 확인합니다.',
            elapsedMs: status === 'running' ? undefined : now - startedAt,
            endedAt: status === 'running' ? undefined : now,
            id: GATEWAY_PREP_STEP_ID,
            name: GATEWAY_PREP_STEP_ID,
            startedAt,
            status,
            summary: '사용자 권한 및 요청 확인',
            title: '요청 준비',
          });
        };

        const startResponseWaitStep = () => {
          if (responseWaitStartedAt) {
            return;
          }

          const now = Date.now();
          const id = `${RESPONSE_WAIT_STEP_ID}-${responseWaitSequence}`;

          responseWaitSequence += 1;
          responseWaitStartedAt = now;
          responseWaitStepId = id;
          upsertProgressStep({
            detail: 'AIOps가 답변 생성을 시작하기를 기다리는 중입니다.',
            id,
            name: RESPONSE_WAIT_STEP_ID,
            startedAt: now,
            status: 'running',
            summary: '모델 응답 대기',
            title: 'AI 응답 대기',
          });
        };

        const finishResponseWaitStep = (summary: string) => {
          if (!responseWaitStartedAt || !responseWaitStepId) {
            return;
          }

          const now = Date.now();
          upsertProgressStep({
            detail: summary,
            elapsedMs: now - responseWaitStartedAt,
            endedAt: now,
            id: responseWaitStepId,
            name: RESPONSE_WAIT_STEP_ID,
            startedAt: responseWaitStartedAt,
            status: 'completed',
            summary,
            title: 'AI 응답 대기',
          });
          responseWaitStartedAt = undefined;
          responseWaitStepId = undefined;
        };

        const startAnswerStreamStep = () => {
          if (answerStreamStartedAt) {
            return;
          }

          const now = Date.now();
          answerStreamStartedAt = now;
          upsertProgressStep({
            detail: '답변 본문을 받아 화면에 표시합니다.',
            id: ANSWER_STREAM_STEP_ID,
            name: ANSWER_STREAM_STEP_ID,
            startedAt: now,
            status: 'running',
            summary: '답변 표시 중',
            title: '답변 표시',
          });
        };

        const finishAnswerStreamStep = () => {
          if (!answerStreamStartedAt) {
            return;
          }

          const now = Date.now();
          upsertProgressStep({
            detail: '답변 본문 표시가 완료되었습니다.',
            elapsedMs: now - answerStreamStartedAt,
            endedAt: now,
            id: ANSWER_STREAM_STEP_ID,
            name: ANSWER_STREAM_STEP_ID,
            startedAt: answerStreamStartedAt,
            status: 'completed',
            summary: '답변 표시 완료',
            title: '답변 표시',
          });
          answerStreamStartedAt = undefined;
        };

        const handleGatewayPrepEvent = (event: ToolStreamEvent) => {
          upsertGatewayPrepStep('running');
          const normalizedName = normalizeToolName(event.name);

          if (event.type === 'tool_result') {
            gatewayPrepDetails.push(`${formatToolTitle(event.name)}: ${getToolSummary(event)}`);
          }

          if (
            event.type === 'tool_result' &&
            ((normalizedName === 'access_check' && attachments.length === 0) ||
              normalizedName === 'attachment_check')
          ) {
            upsertGatewayPrepStep('completed');
            startResponseWaitStep();
          }
        };

        const handleRunStatusEvent = (event: RunStatusEvent) => {
          const now = Date.now();
          const startedAt = runLoopStartedAt ?? now - (event.elapsedMs ?? 0);
          const failed = event.stage === 'failed';
          const completed = event.stage === 'completed';

          runLoopStartedAt = startedAt;
          if (completed) {
            runCompleted = true;
          }

          upsertProgressStep({
            detail: event.message,
            elapsedMs: completed || failed ? now - startedAt : undefined,
            endedAt: completed || failed ? now : undefined,
            id: `${RUN_LOOP_STEP_ID}-${event.runId ?? runId}`,
            name: RUN_LOOP_STEP_ID,
            startedAt,
            status: failed ? 'failed' : completed ? 'completed' : 'running',
            summary: event.message,
            title: '실행 루프',
          });

          if (event.stage === 'lightspeed' || event.stage === 'waiting') {
            startResponseWaitStep();
          }
        };

        const startProgressStep = (event: ToolStreamEvent) => {
          const now = Date.now();
          const id = String(event.id ?? `${event.name}-${stepSequence}`);

          stepSequence += 1;
          activeStepIdsByName.set(event.name, id);
          activeStepStartedAt.set(id, now);
          upsertProgressStep({
            detail: getToolDetail(event),
            id,
            name: event.name,
            serverName: event.serverName,
            startedAt: now,
            status: 'running',
            summary: getToolSummary(event),
            title: formatToolTitle(event.name),
          });
        };

        const finishProgressStep = (event: ToolStreamEvent) => {
          const now = Date.now();
          const id = String(
            event.id ?? activeStepIdsByName.get(event.name) ?? `${event.name}-${stepSequence}`,
          );
          const startedAt = activeStepStartedAt.get(id) ?? now;
          const failed = FAILED_TOOL_STATUSES.has((event.status ?? '').toLowerCase());

          if (!event.id && !activeStepIdsByName.has(event.name)) {
            stepSequence += 1;
          }

          activeStepIdsByName.delete(event.name);
          activeStepStartedAt.delete(id);
          upsertProgressStep({
            detail: getToolDetail(event),
            elapsedMs: now - startedAt,
            endedAt: now,
            id,
            name: event.name,
            serverName: event.serverName,
            startedAt,
            status: failed ? 'failed' : 'completed',
            summary: getToolSummary(event),
            title: formatToolTitle(event.name),
          });
        };

        for await (const event of streamChat(
          {
            attachments,
            conversationId,
            message: question,
            pageContext,
            recentMessages,
            runId,
          },
          { signal: abortController.signal },
        )) {
          if (event.type === 'run_status') {
            handleRunStatusEvent(event);
            if (event.stage === 'lightspeed') {
              lightspeedStageSeen = true;
              updateLightspeedStatus({
                fallbackActive: false,
                lastContextDigest: event.gatewayContextDigest,
                lastStatus: 'started',
                streamProbe: 'started',
              });
              setMessages((prev) => markLastAssistantSource(prev, 'ols', event.gatewayContextDigest));
            }
            if (
              event.stage === 'completed' &&
              !lightspeedStageSeen &&
              !fallbackAnswerSeen &&
              !clarificationAnswerSeen
            ) {
              updateLightspeedStatus({
                fallbackActive: false,
                lastStatus: 'gateway_direct',
                streamProbe: 'not_used',
              });
              setMessages((prev) =>
                markLastAssistantSource(prev, 'gateway_direct', event.gatewayContextDigest),
              );
            }
          }

          if (event.type === 'tool_plan') {
            const now = Date.now();
            upsertProgressStep({
              detail:
                event.status === 'success'
                  ? '질문을 증거 수집 계획으로 분해하고 필요한 확인 순서를 고정했습니다.'
                  : '질문별 증거 수집 계획 검증에 실패했습니다. 답변은 부족한 근거를 명시해야 합니다.',
              elapsedMs: 0,
              endedAt: now,
              id: RCA_PLAN_STEP_ID,
              name: 'runtime_tool_plan',
              startedAt: now,
              status: event.status === 'success' ? 'completed' : 'failed',
              summary: event.status === 'success' ? '증거 수집 계획 생성' : '증거 수집 계획 실패',
              title: '증거 수집 계획',
            });
            setAiopsStatus((prev) => {
              const base = prev ?? createPendingAiopsStatus();
              const safetyContract =
                base.spec.safetyContract ?? createPendingAiopsStatus().spec.safetyContract!;
              return {
                ...base,
                spec: {
                  ...base.spec,
                  safetyContract: {
                    ...safetyContract,
                    toolPlanStatus: {
                      latestRuntimePlan: event.plan,
                      source: 'chat_stream',
                      status: event.status === 'success' ? 'runtime_generated' : 'runtime_failed',
                    },
                  },
                },
              };
            });
            setMessages((prev) =>
              attachToolPlanToLastAssistant(prev, buildToolPlanFooter(event.plan)),
            );
          }

          if (event.type === 'rca_context') {
            const now = Date.now();
            const evidenceFooter = buildEvidenceFooter(
              event.context,
              event.evidenceStatus,
              event.status,
            );
            upsertProgressStep({
              detail:
                event.phase === 'post_answer'
                  ? '최종 답변에 사용한 근거를 연결했습니다.'
                  : '답변 전에 수집 근거와 추가 확인 항목을 정리했습니다.',
              elapsedMs: 0,
              endedAt: now,
              id: `${RCA_CONTEXT_STEP_ID}-${event.phase || 'unknown'}`,
              name: 'rca_context',
              startedAt: now,
              status: event.status === 'success' ? 'completed' : 'failed',
              summary:
                event.status === 'success'
                  ? rcaContextPhaseLabel(event.phase)
                  : '답변 근거 연결 실패',
              title: '답변 근거',
            });
            setMessages((prev) => attachEvidenceFooterToLastAssistant(prev, evidenceFooter));
            setAiopsStatus((prev) => {
              const base = prev ?? createPendingAiopsStatus();
              const safetyContract =
                base.spec.safetyContract ?? createPendingAiopsStatus().spec.safetyContract!;
              return {
                ...base,
                spec: {
                  ...base.spec,
                  safetyContract: {
                    ...safetyContract,
                    evidenceStatus: event.evidenceStatus ?? safetyContract.evidenceStatus,
                    rcaContextStatus: {
                      digest:
                        event.context && typeof event.context === 'object'
                          ? String(
                              (
                                (event.context as Record<string, unknown>).metadata as
                                  | Record<string, unknown>
                                  | undefined
                              )?.digest ?? '',
                            )
                          : '',
                      latestContext: event.context,
                      source: 'chat_stream',
                      status: event.status === 'success' ? 'available' : 'failed',
                    },
                  },
                },
              };
            });
          }

          if (event.type === 'text') {
            if (event.answerContract) {
              setMessages((prev) => markLastAssistantAnswerContract(prev, event.answerContract));
            }
            if (event.fallbackAnswer || event.source === 'gateway_fallback') {
              fallbackAnswerSeen = true;
              setMessages((prev) => markLastAssistantFallback(prev, event.gatewayContextDigest));
              updateLightspeedStatus({
                fallbackActive: true,
                lastContextDigest: event.gatewayContextDigest,
                lastStatus: event.streamProbe ?? 'failed',
                streamProbe: event.streamProbe ?? 'failed',
              });
            } else if (event.source === 'copilot_clarification') {
              clarificationAnswerSeen = true;
              setMessages((prev) =>
                markLastAssistantSource(prev, 'copilot_clarification', event.gatewayContextDigest),
              );
            } else {
              setMessages((prev) =>
                markLastAssistantSource(
                  prev,
                  lightspeedStageSeen ? 'ols' : 'gateway_direct',
                  event.gatewayContextDigest,
                ),
              );
            }
            if (event.content.trim()) {
              finishResponseWaitStep('답변 표시 시작');
              startAnswerStreamStep();
            }
            enqueueAssistantText(event.content);
          }

          if (event.type === 'tool_call') {
            if (GATEWAY_PREP_TOOLS.has(normalizeToolName(event.name))) {
              handleGatewayPrepEvent(event);
              continue;
            }

            finishResponseWaitStep(`${formatToolTitle(event.name)} 시작`);
            startProgressStep(event);
          }

          if (event.type === 'tool_result') {
            if (GATEWAY_PREP_TOOLS.has(normalizeToolName(event.name))) {
              handleGatewayPrepEvent(event);
              continue;
            }

            if (normalizeToolName(event.name) === 'lightspeed_stream' && event.fallbackAnswer) {
              fallbackAnswerSeen = true;
              updateLightspeedStatus({
                fallbackActive: true,
                lastContextDigest: event.gatewayContextDigest,
                lastError: event.detail ?? event.summary ?? '',
                lastStatus: 'failed',
                streamProbe: 'failed',
              });
            }

            finishResponseWaitStep(`${formatToolTitle(event.name)} 완료`);
            finishProgressStep(event);
            startResponseWaitStep();
          }

          if (event.type === 'error') {
            finishResponseWaitStep('오류 응답 수신');
            markRunningProgressFailed(event.message || 'AI response failed.');
            flushAssistantTextQueueNow();
            setMessages((prev) => [
              ...prev,
              {
                role: 'system',
                content: event.message || 'AI response failed.',
                timestamp: Date.now(),
              },
            ]);
          }

          if (event.type === 'end' && event.conversationId) {
            setConversationId(event.conversationId);
          }
        }
        finishResponseWaitStep('스트림 종료');
        await waitForAssistantTextQueue();
        finishAnswerStreamStep();
        finalizeRunningProgressSteps('답변 완료');
        await refreshAiopsRuntimeStatus();
        if (autoProposeActionsAllowedRef.current) {
          let latestAssistantContent = '';
          setMessages((prev) => {
            const assistantIndex = findLastAssistantIndex(prev);
            latestAssistantContent = assistantIndex >= 0 ? prev[assistantIndex].content : '';
            return prev;
          });
          const matched = matchActionCandidatesForMessage(
            latestAssistantContent,
            actionCandidatesRef.current,
          );
          matched.forEach((candidate) => {
            void handleCreateActionPlanFromChat(candidate);
          });
        }
        if (runCompleted) {
          void onRunComplete?.();
        }
      } catch (error) {
        const stopped =
          stopRequestedRef.current || (error instanceof Error && error.name === 'AbortError');

        flushAssistantTextQueueNow();
        if (stopped) {
          markRunningProgressFailed('사용자가 응답 생성을 중지했습니다.');
          setMessages((prev) => setLastAssistantContentIfEmpty(prev, '응답 생성을 중지했습니다.'));
        } else {
          markRunningProgressFailed(error instanceof Error ? error.message : 'AI response failed.');
          setMessages((prev) => [
            ...prev,
            {
              role: 'system',
              content: error instanceof Error ? error.message : 'AI response failed.',
              timestamp: Date.now(),
            },
          ]);
        }
      } finally {
        const loadingElapsedMs = Date.now() - loadingStartedAt;
        if (loadingElapsedMs < MIN_STOP_BUTTON_VISIBLE_MS) {
          await new Promise((resolve) =>
            window.setTimeout(resolve, MIN_STOP_BUTTON_VISIBLE_MS - loadingElapsedMs),
          );
        }
        chatAbortControllerRef.current = null;
        stopRequestedRef.current = false;
        finalizeRunningProgressSteps('응답 흐름 정리 완료');
        setLoading(false);
      }
    },
    [
      enqueueAssistantText,
      assistantTaskMode,
      draftPageContext,
      executionMode,
      finalizeRunningProgressSteps,
      flushAssistantTextQueueNow,
      handleCreateActionPlanFromChat,
      input,
      loading,
      markRunningProgressFailed,
      onRunComplete,
      scrollToBottom,
      conversationId,
      messages,
      pendingAttachments,
      refreshAiopsRuntimeStatus,
      selectedTaskMode.label,
      updateLightspeedStatus,
      upsertProgressStep,
      waitForAssistantTextQueue,
    ],
  );

  const cancelAssistantResponse = React.useCallback(() => {
    if (!loading || !chatAbortControllerRef.current) {
      return;
    }

    stopRequestedRef.current = true;
    chatAbortControllerRef.current.abort();
    flushAssistantTextQueueNow();
    setLoading(false);
  }, [flushAssistantTextQueueNow, loading]);

  const closeAssistant = React.useCallback(() => {
    if (lockOpen) {
      return;
    }

    startNewConversation();
    setHistorySidebarOpen(false);
    setHistoryDrawerBounds({});
    setPanelResizeUnlocked(false);
    setPanelSize({});
    setPanelOffset({ x: 0, y: 0 });
    setPanelDragActive(false);
    setFullScreen(false);
    setOpen(false);
  }, [lockOpen, startNewConversation]);

  const historySidebar = historySidebarOpen ? (
    <AssistantHistoryPanel
      activeSessionId={activeSessionId}
      authSubject={authSubject}
      authSubjectError={authSubjectError}
      clusterSummary={clusterSummary}
      conversationHistory={conversationHistory}
      copy={copy}
      deleteConversation={deleteConversation}
      formatHistoryTime={formatHistoryTime}
      getClusterHost={getClusterHost}
      historyMenuAnchor={historyMenuAnchor}
      historyMenuPanelRef={historyMenuPanelRef}
      historyMenuRef={historyMenuRef}
      historyPanelView={historyPanelView}
      historySidebarStyle={historySidebarStyle}
      productIcon={aiopsIcon}
      loadConversation={loadConversation}
      loading={loading}
      onActionRefSelect={handleHistoryActionRefSelect}
      openHistoryMenuId={openHistoryMenuId}
      renameConversation={renameConversation}
      renamingHistoryId={renamingHistoryId}
      renamingHistoryTitle={renamingHistoryTitle}
      setHistoryMenuAnchor={setHistoryMenuAnchor}
      setHistoryPanelView={setHistoryPanelView}
      setOpenHistoryMenuId={setOpenHistoryMenuId}
      setRenamingHistoryId={setRenamingHistoryId}
      setRenamingHistoryTitle={setRenamingHistoryTitle}
      startNewConversation={startNewConversation}
      uiLanguage={uiLanguage}
      uploadedDocuments={uploadedDocuments}
      uploadedDocumentsError={uploadedDocumentsError}
      uploadedDocumentsLoading={uploadedDocumentsLoading}
    />
  ) : null;
  const assistantVisible = open || embedded || lockOpen;

  const assistantRootClassName = `komsco-ai${embedded ? ' komsco-ai--embedded' : ''}${
    fullScreen ? ' komsco-ai--fullscreen-active' : ''
  }`;
  const assistantSurfacePortalActive = assistantVisible && !embedded;

  return (
    <div className={assistantRootClassName} data-ui-language={uiLanguage}>
      {!open && !embedded && (
        <button
          aria-label="Open AIOps Copilot"
          className="komsco-ai__fab"
          onMouseDown={openAssistant}
          onClick={openAssistant}
          onPointerDown={openAssistant}
          ref={fabButtonRef}
          type="button"
        >
          <img alt="" className="komsco-ai__fab-logo" src={aiopsIcon} />
          <span
            className={`komsco-ai__fab-status komsco-ai__fab-status--${assistantConnection.tone}`}
          />
        </button>
      )}

      {assistantVisible && (
        <AssistantSurfacePortal
          active={assistantSurfacePortalActive}
          wrapperClassName={`${assistantRootClassName} komsco-ai--portal`}
        >
          <div
            aria-label="AIOps Copilot"
            ref={surfaceRef}
            className={`komsco-ai__surface${fullScreen ? ' komsco-ai__surface--fullscreen' : ''}${
              historySidebarOpen ? ' komsco-ai__surface--history-open' : ''
            }${panelResizeUnlocked ? ' komsco-ai__surface--resize-unlocked' : ''}${
              !panelResizeUnlocked ? ' komsco-ai__surface--resize-locked' : ''
            }${loading ? ' komsco-ai__surface--responding' : ''}${
              panelDragActive ? ' komsco-ai__surface--dragging' : ''
            }`}
            style={surfaceStyle}
          >
            {historySidebar}
            <Card
              className={`komsco-ai__panel${fullScreen ? ' komsco-ai__panel--fullscreen' : ''}`}
            >
              <AssistantHeader
                actionExecutionAvailable={actionExecutionAvailable}
                actionExecutionDisabledReason={actionExecutionDisabledReason}
                clusterSummary={clusterSummary}
                clusterSummaryError={clusterSummaryError}
                clusterSummaryLoading={clusterSummaryLoading}
                copy={copy}
                executionMode={executionMode}
                fullScreen={fullScreen}
                lockOpen={lockOpen}
                onClose={closeAssistant}
                onExecutionModeChange={handleExecutionModeChange}
                onMouseDown={startPanelDrag}
                onToggleFullScreen={() => setFullScreen((value) => !value)}
                onToggleLanguage={() => setUiLanguage((value) => (value === 'ko' ? 'en' : 'ko'))}
                onToggleResizeLock={togglePanelResizeLock}
                onToggleSidebar={() => setHistorySidebarOpen((value) => !value)}
                panelResizeUnlocked={panelResizeUnlocked}
                uiLanguage={uiLanguage}
              />

              <div className="komsco-ai__workspace">
                <div className="komsco-ai__chat-column">
                  <CardBody
                    className="komsco-ai__body"
                    aria-live="polite"
                    onScroll={handleConversationScroll}
                    ref={bodyRef}
                  >
                    <div className="komsco-ai__conversation-inner">
                      {messages.length === 0 && (
                        <AssistantEmptyState
                          iconSrc={aiopsIcon}
                          text={emptyStateCopy.text}
                          title={emptyStateCopy.title}
                        />
                      )}

                      {messages.map((message, index) => {
                        const hasProgress = (message.progressSteps?.length ?? 0) > 0;
                        const hasContent = message.content.trim().length > 0;
                        const activeMessage = loading && index === messages.length - 1;
                        const isLatestAssistantMessage =
                          message.role === 'assistant' &&
                          index === findLastAssistantIndex(messages);
                        const messageActionAnchor =
                          message.role === 'assistant' ? actionAnchorForMessageIndex(index) : undefined;
                        const matchedActionCandidates =
                          isLatestAssistantMessage &&
                          hasContent &&
                          executionModeAllowsActions(executionMode)
                            ? matchActionCandidatesForMessage(message.content, actionCandidates)
                            : [];
                        const answerActionRecords =
                          isLatestAssistantMessage && hasContent
                            ? latestAnswerActionRecords(
                                aiopsStatus,
                                executionMode,
                                message.content,
                                messageActionAnchor,
                                sessionActionRefs,
                              )
                            : [];
                        const answerActionRefs =
                          isLatestAssistantMessage && hasContent && messageActionAnchor
                            ? sessionActionRefs
                                .filter((ref) => ref.messageAnchor === messageActionAnchor)
                                .slice(0, 3)
                            : [];
                        const waitingForContent =
                          activeMessage && message.role === 'assistant' && !hasContent;
                        const messageTime = formatMessageTime(message.timestamp, uiLanguage);
                        return (
                          <div
                            className={`komsco-ai__message komsco-ai__message--${message.role}`}
                            data-action-anchor={
                              messageActionAnchor
                            }
                            data-message-index={index}
                            key={`${message.role}-${index}`}
                          >
                            <div className="komsco-ai__message-stack">
                              <AssistantMessageHeader
                                hasContent={hasContent}
                                language={uiLanguage}
                                message={message}
                              />
                              {(hasContent || (!hasProgress && !waitingForContent)) && (
                                <div className="komsco-ai__message-content">
                                  {renderFormattedContent(message, setPreviewAttachment)}
                                </div>
                              )}
                              {message.role === 'assistant' &&
                                hasContent &&
                                (
                                  <AssistantEvidenceFooter
                                    footer={message.evidenceFooter}
                                    messageContent={message.content}
                                  />
                                )}
                              {message.role === 'assistant' &&
                                hasContent &&
                                <AssistantToolPlanFooter toolPlan={message.toolPlan} />}
                              {message.role === 'assistant' &&
                                hasContent &&
                                (
                                  <AssistantCreateActionPlanButtons
	                                    busyCandidateId={busyActionCandidateId}
	                                    candidates={matchedActionCandidates}
	                                    language={uiLanguage}
	                                    onCreatePlan={handleCreateActionPlanFromChat}
	                                  />
                                )}
                              {message.role === 'assistant' &&
                                hasContent &&
                                (
                                  <AssistantAnswerActions
                                    aiopsActionError={aiopsActionError}
                                    aiopsActionNotice={aiopsActionNotice}
                                    aiopsStatus={aiopsStatus}
                                    busyActionId={aiopsActionBusyId}
                                    executionMode={executionMode}
                                    fallbackRefs={answerActionRefs}
                                    onAction={handleAiopsAction}
                                    records={answerActionRecords}
                                    resolveAction={getAiopsRecordAction}
                                  />
                                )}
                              {hasProgress && message.progressSteps && (
                                <ProgressTimeline
                                  active={activeMessage}
                                  language={uiLanguage}
                                  steps={message.progressSteps}
                                />
                              )}
                              {messageTime && (
                                <div className="komsco-ai__message-time">{messageTime}</div>
                              )}
                              {hasContent &&
                                (message.role === 'assistant' || message.role === 'user') && (
                                  <MessageActionFooter
                                    copied={copiedMessageIndex === index}
                                    copiedLabel={copy.answerCopied}
                                    copyLabel={copy.answerCopy}
                                    feedback={message.feedback}
                                    language={uiLanguage}
                                    onCopy={() => copyMessage(message, index)}
                                    onEditForResend={
                                      message.role === 'user'
                                        ? () => editMessageForResend(message)
                                        : undefined
                                    }
                                    onFeedback={
                                      message.role === 'assistant'
                                        ? (feedback) => toggleMessageFeedback(index, feedback)
                                        : undefined
                                    }
                                    role={message.role}
                                  />
                                )}
                              {hasContent && message.role === 'assistant' && message.feedback && (
                                <MessageFeedbackComment
                                  comment={message.feedbackComment}
                                  feedback={message.feedback}
                                  language={uiLanguage}
                                  onSubmit={(comment) => submitMessageFeedbackComment(index, comment)}
                                />
                              )}
                            </div>
                          </div>
                        );
                      })}
                      <div ref={bodyEndRef} />
                    </div>
                  </CardBody>

                  <AssistantComposer
                    assistantTaskMode={assistantTaskMode}
                    attachmentError={attachmentError}
                    autoProposeActions={autoProposeActions}
                    cancelAssistantResponse={cancelAssistantResponse}
                    copy={copy}
                    dragActive={dragActive}
                    executionMode={executionMode}
                    fileInputRef={fileInputRef}
                    input={input}
                    loading={loading}
                    onDragEnter={(event) => {
                      event.preventDefault();
                      setDragActive(true);
                    }}
                    onDragLeave={(event) => {
                      if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
                        setDragActive(false);
                      }
                    }}
                    onDragOver={(event) => event.preventDefault()}
                    onDrop={handleDrop}
                    onFileInputChange={handleFileInputChange}
                    onInputChange={setInput}
                    onPaste={handlePaste}
                    onPreviewAttachment={setPreviewAttachment}
                    onRemoveAttachment={removeAttachment}
                    onScrollToBottom={() => {
                      setStickToBottom(true);
                      setShowScrollToBottom(false);
                      scrollToBottom('auto');
                    }}
                    onSend={send}
                    pendingAttachments={pendingAttachments}
                    quickPromptMenuOpen={quickPromptMenuOpen}
                    quickPromptMenuRef={quickPromptMenuRef}
                    setAssistantTaskMode={setAssistantTaskMode}
                    setAutoProposeActions={setAutoProposeActions}
                    setQuickPromptMenuOpen={setQuickPromptMenuOpen}
                    setTaskModeMenuOpen={setTaskModeMenuOpen}
                    showScrollToBottom={showScrollToBottom}
                    taskModeMenuOpen={taskModeMenuOpen}
                    taskModeMenuRef={taskModeMenuRef}
                    uiLanguage={uiLanguage}
                  />
                </div>
                <AssistantInsightRail
                  aiopsActionBusyId={aiopsActionBusyId}
                  aiopsActionError={aiopsActionError}
                  aiopsActionNotice={aiopsActionNotice}
                  aiopsStatus={aiopsStatus}
                  aiopsStatusError={aiopsStatusError}
                  conversationHistory={conversationHistory}
                  error={clusterSummaryError}
                  executionMode={executionMode}
                  language={uiLanguage}
                  loading={clusterSummaryLoading}
                  messages={messages}
                  onAiopsAction={handleAiopsAction}
                  summary={clusterSummary}
                />
              </div>
            </Card>
            {panelResizeUnlocked && !fullScreen && (
              <AssistantResizeHandles copy={copy} onResizeStart={startPanelResize} />
            )}
          </div>
        </AssistantSurfacePortal>
      )}
      {previewAttachment && (
        <AssistantImageLightbox
          attachment={previewAttachment}
          onClose={() => setPreviewAttachment(null)}
        />
      )}
    </div>
  );
};

export default AssistantLauncher;
