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
  MAX_RECENT_CONTEXT_MESSAGES,
  MIN_STOP_BUTTON_VISIBLE_MS,
  RCA_CONTEXT_STEP_ID,
  RCA_PLAN_STEP_ID,
  RESPONSE_WAIT_STEP_ID,
  RUN_LOOP_STEP_ID,
  SCROLL_BOTTOM_THRESHOLD_PX,
  STORED_MESSAGE_FEEDBACK_KEY,
} from './assistant.constants';
import {
  actionRecordInlineKey,
  actionRecordsForMatchedCandidates,
  groupActionRecordsByCandidateId,
  highestLifecycleRecordForPlanDigest,
  latestAnswerActionRecords,
} from './assistant.actionDisplay';
import { dedupeActionCandidates } from './assistant.actionCandidates';
import { TASK_MODE_EMPTY_COPY, UI_COPY } from './assistant.copy';
import { useAssistantConversations } from './assistant.conversations';
import {
  buildEvidenceCopyText,
  buildEvidenceFooter,
} from './assistant.evidence';
import {
  actionAnchorForMessageIndex,
  conversationActionRefFromRecord,
  findPlanByDigest,
  getApprovalId,
  getApprovalPlanDigest,
  getPlanDigest,
  getRecordName,
  getRecordSpecMap,
  getRecordTargetLabel,
  isReviewOnlyActionRecord,
} from './assistant.actionRecords';
import {
  canUseActionExecution,
  canUseUnrestrictedCommands,
  executionModeAllowsActions,
  getAiopsRecordAction,
  getActionExecutionDisabledReason,
} from './assistant.actionState';
import { getClusterHost } from './assistant.insightRailHelpers';
import {
  createRunId,
  formatHistoryTime,
  languageLocale,
} from './assistant.storage';
import {
  conversationActionRefFromCandidate,
  groupActionRefsByCandidateId,
  mergeConversationActionRefs,
  pendingActionCandidatesForRefs,
  sortConversationActionRefsForDisplay,
  targetKeyFromParts,
} from './assistant.sessionActions';
import {
  buildToolPlanFooter,
} from './assistant.toolPlan';
import { filesFromClipboardData, isAcceptedImageFile } from './assistant.uploadFiles';
import { useAssistantUploads } from './assistant.uploads';
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
  ToolPlanFooter,
  ToolStreamEvent,
  UiLanguage,
} from './assistant.types';
import {
  type AiopsActionCandidate,
  type AiopsRecord,
  type AiopsRuntimeStatus,
  type AuthSubject,
  type ChatContextMessage,
  type ChatFeedbackPayload,
  type ClusterSummary,
  type ImageAttachment,
  approveActionPlan,
  createActionCandidatePlan,
  createActionPlan,
  executeApprovedAction,
  fetchActionCandidates,
  fetchAiopsStatus,
  fetchClusterSummary,
  fetchConsoleUserSubject,
  rejectActionPlan,
  submitChatFeedback,
  streamChat,
} from '../services/aiGateway';
import { redactSensitiveText } from '../utils/evidenceDisplay';
import aiopsIcon from '../assets/aiops_icon.svg';
import './assistant.css';

const conversationHistoryMergeFns = {
  actionRefs: mergeConversationActionRefs,
} as const;

const matchActionCandidatesForMessage = (
  content: string,
  candidates: AiopsActionCandidate[],
): AiopsActionCandidate[] => {
  const cleanupClarification = /정리 대상 범위 확인|범위가 아직 넓습니다|이 범위\(.+\)로 정리 검토를 진행할까요|범위를 확인하면/i.test(
    content,
  );
  if (cleanupClarification) {
    return [];
  }

  const cleanupReviewAnswer = /테스트 Pod 정리 검토|정리 검토 후보/.test(content);
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

  const matched = candidates.filter((candidate) => {
    const targetName = candidate.target?.name;
    const namespace = candidate.target?.namespace;
    return Boolean(
      (targetName && content.includes(targetName)) ||
        (namespace && content.includes(namespace)),
    );
  });
  return dedupeActionCandidates(matched);
};

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
  if (/already.*used|이미.*사용|이미.*실행|이미.*검토 기록/.test(lower)) {
    return '이 승인은 이미 실행 또는 검토 기록에 사용됐습니다. 실행 기록을 확인해 주세요.';
  }
  if (/not approved|승인 완료 상태가 아닌/.test(lower)) {
    return '승인 완료 상태가 아닌 기록입니다. 새 Action Plan을 다시 생성해 주세요.';
  }
  if (/separation of duties|same.*approver|requester and approver|요청자와 승인자/.test(lower)) {
    return '승인 정책상 요청자와 승인자가 달라야 합니다. 다른 운영자 계정으로 승인하거나 새 승인 절차를 시작해 주세요.';
  }
  if (/conflict|409/.test(lower)) {
    return '현재 화면의 계획/승인 상태와 서버 기록이 맞지 않습니다. 새로고침 후 같은 대상의 Action Plan을 다시 확인해 주세요.';
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

type AiopsRuntimeRecordUpdates = Partial<AiopsRuntimeStatus['spec']['records']>;

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

const mergeAiopsRecordUpdates = (
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

const mergeAiopsRecordsIntoStatus = (
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
    return `${formatToolTitle(event.name)} 시작`;
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

const markLastAssistantStreaming = (messages: Message[], streaming: boolean): Message[] => {
  const assistantIndex = findLastAssistantIndex(messages);
  if (assistantIndex < 0) {
    return messages;
  }

  const next = [...messages];
  next[assistantIndex] = {
    ...next[assistantIndex],
    streaming,
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

const approvalRecordWithExecutedStatus = (
  approval: AiopsRecordView,
  execution: AiopsRecordView,
): AiopsRecordView => {
  const spec = getRecordSpecMap(approval);
  const decision =
    spec.approvalDecision && typeof spec.approvalDecision === 'object'
      ? (spec.approvalDecision as Record<string, unknown>)
      : undefined;

  if (!decision) {
    return approval;
  }

  return {
    ...approval,
    spec: {
      ...spec,
      approvalDecision: {
        ...decision,
        executedAt: execution.metadata?.createdAt ?? new Date().toISOString(),
        status: 'executed',
      },
    },
  };
};

type MessageFeedbackChoice = 'up' | 'down';

type MessageActionFooterProps = {
  copied: boolean;
  copiedLabel: string;
  copyLabel: string;
  feedback?: MessageFeedbackChoice;
  feedbackComment?: string;
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
        feedbackCommentSaved: 'Saved',
        feedbackCommentSubmit: 'Save',
        dislikeSaved: 'Needs work saved',
        dislikeSelected: 'Needs work selected',
        like: 'Good response',
        likeSaved: 'Good response saved',
        likeSelected: 'Good response selected',
      }
    : {
        copy: '복사',
        copied: '복사됨',
        dislike: '좋지 않은 답변',
        edit: '수정해서 다시 보내기',
        feedbackCommentSaved: '저장됨',
        feedbackCommentSubmit: '저장',
        dislikeSaved: '싫어요 저장됨',
        dislikeSelected: '싫어요 선택됨',
        like: '좋은 답변',
        likeSaved: '좋아요 저장됨',
        likeSelected: '좋아요 선택됨',
      };

const feedbackCommentPlaceholder = (language: UiLanguage, feedback: MessageFeedbackChoice): string =>
  language === 'en'
    ? feedback === 'down'
      ? 'Note what was wrong or confusing'
      : 'Note what should stay this good'
    : feedback === 'down'
      ? '틀렸거나 불편한 점을 짧게 입력'
      : '유지할 만한 좋은 점을 짧게 입력';

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

const storedFeedbackKey = (payload: Pick<ChatFeedbackPayload, 'feedbackId' | 'messageId' | 'rating'>): string =>
  payload.feedbackId || `${payload.messageId}:${payload.rating}`;

const publicFeedbackAnswerContract = (message: Message): string | undefined => {
  const contract = message.answerContract?.trim();
  if (!contract) {
    return undefined;
  }

  return /fixture|local/i.test(contract) ? 'v0281-gateway-answer-contract' : contract;
};

const publicFeedbackSource = (message: Message): NonNullable<Message['answerSource']> => {
  if (message.answerSource) {
    return message.answerSource;
  }
  if (message.fallbackAnswer) {
    return 'gateway_fallback';
  }
  if (message.toolPlan || message.evidenceFooter) {
    return 'gateway_direct';
  }
  return 'copilot_reply';
};

const writeStoredMessageFeedback = (payload: ChatFeedbackPayload): void => {
  if (typeof window === 'undefined') {
    return;
  }

  const existing = readStoredMessageFeedback();
  const payloadKey = storedFeedbackKey(payload);
  const next = [
    payload,
    ...existing.filter((item) => storedFeedbackKey(item) !== payloadKey),
  ].slice(0, 200);
  window.localStorage.setItem(STORED_MESSAGE_FEEDBACK_KEY, JSON.stringify(next));
};

const removeStoredMessageFeedback = (messageId: string, rating?: MessageFeedbackChoice): void => {
  if (typeof window === 'undefined') {
    return;
  }

  const next = readStoredMessageFeedback().filter(
    (item) => item.messageId !== messageId || (rating ? item.rating !== rating : false),
  );
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
  feedbackComment,
  language,
  onCopy,
  onEditForResend,
  onFeedback,
  role,
}) => {
  const labels = messageActionLabels(language);
  const copyButtonLabel = copied ? copiedLabel || labels.copied : copyLabel || labels.copy;
  const feedbackHasSavedComment = Boolean(feedbackComment?.trim());
  const feedbackStatus =
    feedback === 'up'
      ? feedbackHasSavedComment
        ? labels.likeSaved
        : labels.likeSelected
      : feedback === 'down'
        ? feedbackHasSavedComment
          ? labels.dislikeSaved
          : labels.dislikeSelected
        : '';
  const statusLabel = copied ? copiedLabel || labels.copied : feedbackStatus;

  if (role === 'user') {
    return (
      <div className="komsco-ai__message-actions" data-message-actions="user">
        {statusLabel && (
          <span className="komsco-ai__message-action-status" role="status">
            {statusLabel}
          </span>
        )}
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
      {statusLabel && (
        <span className="komsco-ai__message-action-status" role="status">
          {statusLabel}
        </span>
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
  const hasSavedComment = savedComment.length > 0;
  const prompt =
    language === 'en'
      ? feedback === 'down'
        ? 'Improve'
        : 'Worked well'
      : feedback === 'down'
        ? '개선점'
        : '좋았던 점';
  const storageHint =
    language === 'en'
      ? 'saved: browser+Gateway'
      : '기록: 브라우저+Gateway';
  const storageHintTitle =
    language === 'en'
      ? `Browser localStorage: ${STORED_MESSAGE_FEEDBACK_KEY} · Gateway API: /v1/chat/feedback`
      : `브라우저 localStorage: ${STORED_MESSAGE_FEEDBACK_KEY} · Gateway API: /v1/chat/feedback`;

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
      <div className="komsco-ai__feedback-comment-row">
        <label>
          <span className="komsco-ai__feedback-prompt" title={storageHintTitle}>
            {prompt} · {storageHint}
          </span>
          <input
            maxLength={1000}
            onChange={(event) => setDraft(event.target.value)}
            placeholder={feedbackCommentPlaceholder(language, feedback)}
            value={draft}
          />
        </label>
        <button disabled={!dirty} type="submit">
          {dirty
            ? labels.feedbackCommentSubmit
            : hasSavedComment
              ? labels.feedbackCommentSaved
            : labels.feedbackCommentSubmit}
        </button>
      </div>
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
  const [clusterSummary, setClusterSummary] = React.useState<ClusterSummary | null>(null);
  const [clusterSummaryError, setClusterSummaryError] = React.useState('');
  const [clusterSummaryLoading, setClusterSummaryLoading] = React.useState(false);
  const [authSubject, setAuthSubject] = React.useState<AuthSubject | null>(null);
  const [authSubjectError, setAuthSubjectError] = React.useState('');
  const [aiopsStatus, setAiopsStatus] = React.useState<AiopsRuntimeStatus | null>(null);
  const optimisticAiopsRecordsRef = React.useRef<AiopsRuntimeRecordUpdates>({});
  // Guards against an out-of-order response (e.g. the 10s poller firing right
  // before a post-action refresh) silently overwriting fresher status with
  // stale data — only the response to the most recently issued request wins.
  const aiopsStatusRequestSeqRef = React.useRef(0);
  const [actionCandidates, setActionCandidates] = React.useState<AiopsActionCandidate[]>([]);
  const [busyActionCandidateId, setBusyActionCandidateId] = React.useState('');
  const [actionCandidateFeedback, setActionCandidateFeedback] = React.useState<{
    candidateId: string;
    message: string;
    tone: 'error' | 'pending' | 'success';
  } | null>(null);
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
  const [loading, setLoading] = React.useState(false);
  const {
    activeSessionId,
    conversationHistory,
    conversationId,
    messages,
    messagesRef,
    saveCurrentConversation,
    sessionActionRefs,
    setActiveSessionId,
    setConversationHistory,
    setConversationId,
    setMessages,
    setSessionActionRefs,
    setSessionActionTargetKeys,
    setUiLanguage,
    suppressNextHistoryAutosaveRef,
    uiLanguage,
    upsertSessionActionRef,
  } = useAssistantConversations({
    loading,
    mergeActionRefs: conversationHistoryMergeFns.actionRefs,
  });
  const [historySidebarOpen, setHistorySidebarOpen] = React.useState(false);
  const [historyPanelView, setHistoryPanelView] = React.useState<HistoryPanelView>('chats');
  const copy = UI_COPY[uiLanguage];
  const {
    addImageFiles,
    attachmentError,
    dragActive,
    pendingAttachments,
    removeAttachment,
    setAttachmentError,
    setDragActive,
    setPendingAttachments,
    uploadedDocuments,
    uploadedDocumentsError,
    uploadedDocumentsLoading,
  } = useAssistantUploads({
    activeSessionId,
    historyPanelView,
    historySidebarOpen,
    open,
    setHistoryPanelView,
    setHistorySidebarOpen,
    uploadedDocsErrorLabel: copy.uploadedDocsError,
  });
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
  const assistantTypewriterTimerRef = React.useRef<number | undefined>();
  const assistantTextDrainResolversRef = React.useRef<Array<() => void>>([]);
  const chatAbortControllerRef = React.useRef<AbortController | null>(null);
  const stopRequestedRef = React.useRef(false);
  const panelDragFrameRef = React.useRef<number | undefined>();
  const panelDragNextOffsetRef = React.useRef<{ x: number; y: number } | null>(null);
  const actionExecutionAvailable = canUseActionExecution(aiopsStatus);
  const actionExecutionDisabledReason = getActionExecutionDisabledReason(aiopsStatus, uiLanguage);
  const assistantConnection = getAssistantConnectionState(
    clusterSummary,
    clusterSummaryLoading,
    clusterSummaryError,
    aiopsStatus,
    aiopsStatusError,
  );
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
      style['--komsco-panel-height'] = `${panelSize.height}px`;
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
    setActionCandidateFeedback(null);
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
      setActionCandidateFeedback(null);
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
      setSessionActionRefs(conversation.actionRefs ?? []);
      setSessionActionTargetKeys(new Set(conversation.actionTargetKeys ?? []));

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

  const toggleConversationPinned = React.useCallback((conversationHistoryId: string) => {
    setConversationHistory((prev) =>
      prev.map((conversation) =>
        conversation.id === conversationHistoryId
          ? { ...conversation, pinned: !conversation.pinned }
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

  const refreshAiopsActionCandidates = React.useCallback(async () => {
    try {
      const summary = await fetchActionCandidates();
      const nextCandidates = summary.spec?.candidates ?? [];
      actionCandidatesRef.current = nextCandidates;
      setActionCandidates(nextCandidates);
      return nextCandidates;
    } catch {
      // Best-effort: the "조치 계획 생성" button simply won't appear if this fails.
      return actionCandidatesRef.current;
    }
  }, []);

  React.useEffect(() => {
    if (!open) {
      return undefined;
    }

    let disposed = false;

    const loadActionCandidates = async () => {
      if (!disposed) {
        await refreshAiopsActionCandidates();
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
  }, [open, refreshAiopsActionCandidates]);

  const refreshAiopsRuntimeStatus = React.useCallback(async () => {
    const seq = ++aiopsStatusRequestSeqRef.current;
    try {
      const status = await fetchAiopsStatus();
      if (seq !== aiopsStatusRequestSeqRef.current) {
        return null;
      }

      const mergedStatus = mergeAiopsRecordsIntoStatus(
        status,
        optimisticAiopsRecordsRef.current,
        false,
      );
      setAiopsStatus(mergedStatus);
      setAiopsStatusError('');
      return mergedStatus;
    } catch (error) {
      if (seq !== aiopsStatusRequestSeqRef.current) {
        return null;
      }
      setAiopsStatusError(error instanceof Error ? error.message : 'AIOps status request failed.');
      return null;
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

  const upsertAiopsRuntimeRecords = React.useCallback(
    (updates: AiopsRuntimeRecordUpdates) => {
      optimisticAiopsRecordsRef.current = mergeAiopsRecordUpdates(
        optimisticAiopsRecordsRef.current,
        updates,
      );
      setAiopsStatus((prev) => {
        const base = prev ?? createPendingAiopsStatus();
        return mergeAiopsRecordsIntoStatus(base, updates);
      });
    },
    [],
  );

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
      const actionMessageAnchor = getLatestAssistantMessageAnchor();

      try {
        if (action.step === 'create-plan') {
          const proposalId = getRecordName(record);
          if (!proposalId) {
            throw new Error('Action proposal id is missing.');
          }
          const plan = await createActionPlan(proposalId);
          upsertAiopsRuntimeRecords({ sealedActionPlans: [plan] });
          setAiopsActionNotice('Action plan을 생성했습니다.');
          const targetKey = getRecordTargetLabel(record);
          setSessionActionTargetKeys((prev) => new Set(prev).add(targetKey));
          upsertSessionActionRef(
            conversationActionRefFromRecord(
              plan,
              executionMode,
              actionMessageAnchor,
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
          upsertAiopsRuntimeRecords({ approvalDecisions: [approval] });
          setAiopsActionNotice('Action plan을 승인했습니다.');
          upsertSessionActionRef(
            conversationActionRefFromRecord(
              approval,
              executionMode,
              actionMessageAnchor,
            ),
          );
        }

        if (action.step === 'approve-execute-plan') {
          if (executionMode !== 'unrestricted') {
            setAiopsActionError('승인과 실행을 한 번에 처리하는 동작은 실행 무제한 모드에서만 가능합니다.');
            return;
          }
          if (!canUseUnrestrictedCommands(aiopsStatus)) {
            setAiopsActionError('Gateway가 실행 무제한 capability를 허용하지 않아 자동 승인 후 실행을 보낼 수 없습니다.');
            return;
          }
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
          const executedApproval = approvalRecordWithExecutedStatus(approval, execution);
          upsertAiopsRuntimeRecords({
            approvalDecisions: [executedApproval],
            executionRecords: [execution],
          });
          setAiopsActionNotice('실행 무제한 모드로 자동 승인 후 실행했습니다.');
          upsertSessionActionRef(
            conversationActionRefFromRecord(
              executedApproval,
              executionMode,
              actionMessageAnchor,
            ),
          );
          upsertSessionActionRef(
            conversationActionRefFromRecord(
              execution,
              executionMode,
              actionMessageAnchor,
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
          upsertAiopsRuntimeRecords({ approvalDecisions: [rejection] });
          setAiopsActionNotice('Action plan을 거절 기록했습니다.');
          upsertSessionActionRef(
            conversationActionRefFromRecord(
              rejection,
              executionMode,
              actionMessageAnchor,
            ),
          );
        }

        if (action.step === 'execute-approval') {
          const recordPlanDigest = getPlanDigest(record);
          const planDigest = getApprovalPlanDigest(record) || recordPlanDigest;
          const linkedApproval =
            recordPlanDigest && aiopsStatus
              ? aiopsStatus.spec.records.approvalDecisions.find(
                  (item) => getApprovalPlanDigest(item) === recordPlanDigest,
                )
              : undefined;
          const approvalId = getApprovalId(linkedApproval ?? record);
          const plan = findPlanByDigest(
            aiopsStatus?.spec.records.sealedActionPlans ?? [],
            planDigest,
          );
          const planId = plan ? getRecordName(plan) : '';
          if (!approvalId || !planId || !planDigest) {
            throw new Error('Approval 또는 연결된 action plan 정보가 없습니다.');
          }
          const execution = await executeApprovedAction(approvalId, planId, planDigest);
          const executedApproval = approvalRecordWithExecutedStatus(linkedApproval ?? record, execution);
          upsertAiopsRuntimeRecords({
            approvalDecisions: [executedApproval],
            executionRecords: [execution],
          });
          setAiopsActionNotice(
            isReviewOnlyActionRecord(execution)
              ? '검토 기록을 남겼습니다. 클러스터 변경은 실행하지 않았습니다.'
              : '승인된 조치를 실행했습니다.',
          );
          upsertSessionActionRef(
            conversationActionRefFromRecord(
              executedApproval,
              executionMode,
              actionMessageAnchor,
            ),
          );
          upsertSessionActionRef(
            conversationActionRefFromRecord(
              execution,
              executionMode,
              actionMessageAnchor,
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
    [
      aiopsStatus,
      executionMode,
      getLatestAssistantMessageAnchor,
      refreshAiopsRuntimeStatus,
      upsertAiopsRuntimeRecords,
      upsertSessionActionRef,
    ],
  );

	  const handleCreateActionPlanFromChat = React.useCallback(
	    async (candidate: AiopsActionCandidate) => {
      if (!executionModeAllowsActions(executionMode)) {
        const message = '읽기 전용: 후보만 표시';
        setAiopsActionNotice('');
        setAiopsActionError(message);
        setActionCandidateFeedback({
          candidateId: candidate.id,
          message,
          tone: 'error',
        });
        return;
      }
	      if (candidate.planDisabledReason) {
	        setAiopsActionNotice('');
	        setAiopsActionError(candidate.planDisabledReason);
        setActionCandidateFeedback({
          candidateId: candidate.id,
          message: candidate.planDisabledReason,
          tone: 'error',
        });
	        return;
	      }
	      if (busyActionCandidateIdRef.current) {
	        return;
	      }
      busyActionCandidateIdRef.current = candidate.id;
      setBusyActionCandidateId(candidate.id);
      setAiopsActionError('');
      setAiopsActionNotice('');
      setActionCandidateFeedback({
        candidateId: candidate.id,
        message: 'Action Plan 생성 중입니다.',
        tone: 'pending',
      });
      const actionMessageAnchor = getLatestAssistantMessageAnchor();

      try {
        const result = await createActionCandidatePlan(candidate);
        upsertAiopsRuntimeRecords({
          actionProposals: result.spec?.proposal ? [result.spec.proposal] : undefined,
          sealedActionPlans: result.spec?.plan ? [result.spec.plan] : undefined,
        });
        const createdMessage =
          'Action Plan을 생성했습니다. 아래 카드에서 승인 또는 실행을 이어갈 수 있습니다.';
        setAiopsActionNotice(createdMessage);
        setActionCandidateFeedback({
          candidateId: candidate.id,
          message: createdMessage,
          tone: 'success',
        });
        const targetKey = targetKeyFromParts(candidate.target?.namespace, candidate.target?.name);
        setSessionActionTargetKeys((prev) => new Set(prev).add(targetKey));
        upsertSessionActionRef(
          result.spec?.plan
            ? {
                ...conversationActionRefFromRecord(
                  result.spec.plan,
                  executionMode,
                  actionMessageAnchor,
                ),
                candidateId: candidate.id,
              }
            : conversationActionRefFromCandidate(candidate, actionMessageAnchor),
        );
        const refreshedStatus = await refreshAiopsRuntimeStatus();
        const linkedPlanDigest =
          result.spec?.planDigest || (result.spec?.plan ? getPlanDigest(result.spec.plan) : '');
        const highestRecord = highestLifecycleRecordForPlanDigest(refreshedStatus, linkedPlanDigest);
        if (highestRecord) {
          upsertSessionActionRef(
            conversationActionRefFromRecord(
              highestRecord,
              executionMode,
              actionMessageAnchor,
            ),
          );
        }
      } catch (error) {
        const message = aiopsActionErrorMessage(error);
        setAiopsActionError(message);
        setActionCandidateFeedback({
          candidateId: candidate.id,
          message,
          tone: 'error',
        });
      } finally {
        busyActionCandidateIdRef.current = '';
        setBusyActionCandidateId('');
      }
    },
    [
      executionMode,
      getLatestAssistantMessageAnchor,
      refreshAiopsRuntimeStatus,
      upsertAiopsRuntimeRecords,
      upsertSessionActionRef,
    ],
  );

  const appendAssistantText = React.useCallback((content: string) => {
    setMessages((prev) => {
      const assistantIndex = findLastAssistantIndex(prev);
      if (assistantIndex < 0) {
        return [...prev, { role: 'assistant', content, streaming: true, timestamp: Date.now() }];
      }

      const next = [...prev];
      next[assistantIndex] = {
        ...next[assistantIndex],
        content: next[assistantIndex].content + content,
        streaming: true,
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

  const copyMessage = React.useCallback(
    (message: Message, index: number) => {
      const redactedContent = redactSensitiveText(
        stripDefaultEvidenceAppendix(message.content).trim(),
      );
      const text = `${redactedContent}${buildEvidenceCopyText(
        message.evidenceFooter,
        uiLanguage,
      )}`.trim();
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
    },
    [uiLanguage],
  );

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
      const feedbackSource = publicFeedbackSource(message);
      const payload: ChatFeedbackPayload = {
        answerContract: publicFeedbackAnswerContract(message),
        answerSource: feedbackSource,
        conversationId: conversationId ?? activeSessionId,
        feedbackId: `feedback-${messageId.replace(/[^a-zA-Z0-9-]+/g, '-')}-${feedback}`,
        intent: message.toolPlan?.taskType,
        messageId,
        mode: executionMode,
        optionalComment: optionalComment?.trim() || undefined,
        rating: feedback,
        route: window.location.pathname,
        source: feedbackSource,
        timestamp: submittedAt,
      };

      writeStoredMessageFeedback(payload);
      void submitChatFeedback(payload)
        .then(() => refreshAiopsRuntimeStatus())
        .catch((error) => {
          // Feedback is already kept locally; gateway persistence is best-effort during local tests.
          // eslint-disable-next-line no-console
          console.warn('AIOps feedback persistence failed', error);
        });
    },
    [activeSessionId, conversationId, executionMode, refreshAiopsRuntimeStatus],
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
        removeStoredMessageFeedback(messageId, feedback);
        return;
      }

      // Selecting thumbs up/down only opens the tester comment form. Persisting
      // happens after the user writes the note and presses save, so the UI does
      // not claim "saved" for an empty review.
    },
    [activeSessionId],
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
      const files = filesFromClipboardData(event.clipboardData);
      const hasImage = files.some(isAcceptedImageFile);

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
      void addImageFiles(filesFromClipboardData(event.dataTransfer));
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
      setActionCandidateFeedback(null);
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
        { role: 'assistant', content: '', progressSteps: [], streaming: true },
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
          aiopsUiLanguage: uiLanguage,
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
        let copilotReplySeen = false;
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
            detail: 'Gateway 또는 모델이 다음 답변 조각을 준비하는 중입니다.',
            id,
            name: RESPONSE_WAIT_STEP_ID,
            startedAt: now,
            status: 'running',
            summary: '모델 답변 생성 중',
            title: '모델 답변 생성',
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
            title: '모델 답변 생성',
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
            detail: '답변 본문을 스트리밍으로 받아 대화창에 작성합니다.',
            id: ANSWER_STREAM_STEP_ID,
            name: ANSWER_STREAM_STEP_ID,
            startedAt: now,
            status: 'running',
            summary: '답변 작성 중',
            title: '답변 작성',
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
            summary: '답변 작성 완료',
            title: '답변 작성',
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
            language: uiLanguage,
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
              !clarificationAnswerSeen &&
              !copilotReplySeen
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
                  ? '질문을 조회 계획으로 분해하고 필요한 확인 순서를 고정했습니다.'
                  : '질문별 조회 계획 검증에 실패했습니다. 답변은 부족한 확인 결과를 명시해야 합니다.',
              elapsedMs: 0,
              endedAt: now,
              id: RCA_PLAN_STEP_ID,
              name: 'runtime_tool_plan',
              startedAt: now,
              status: event.status === 'success' ? 'completed' : 'failed',
              summary: event.status === 'success' ? '조회 계획 생성' : '조회 계획 실패',
              title: '조회 계획',
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
                  ? '최종 답변의 확인 결과를 정리했습니다.'
                  : '답변 전에 조회 결과와 추가 확인 항목을 정리했습니다.',
              elapsedMs: 0,
              endedAt: now,
              id: `${RCA_CONTEXT_STEP_ID}-${event.phase || 'unknown'}`,
              name: 'rca_context',
              startedAt: now,
              status: event.status === 'success' ? 'completed' : 'failed',
              summary:
                event.status === 'success'
                  ? rcaContextPhaseLabel(event.phase)
                  : '확인 결과 정리 실패',
              title: '확인 결과',
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
            } else if (event.source === 'copilot_reply') {
              copilotReplySeen = true;
              setMessages((prev) =>
                markLastAssistantSource(prev, 'copilot_reply', event.gatewayContextDigest),
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
              finishResponseWaitStep('답변 작성 시작');
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
        setMessages((prev) => markLastAssistantStreaming(prev, false));
        finishAnswerStreamStep();
        finalizeRunningProgressSteps('답변 완료');
        await refreshAiopsRuntimeStatus();
        const refreshedActionCandidates = await refreshAiopsActionCandidates();
        let matchedActionCandidatesForAnswer: AiopsActionCandidate[] = [];
        setMessages((prev) => {
          const assistantIndex = findLastAssistantIndex(prev);
          if (assistantIndex < 0) {
            return prev;
          }

          const latestAssistantContent = prev[assistantIndex].content;
          matchedActionCandidatesForAnswer = matchActionCandidatesForMessage(
            latestAssistantContent,
            refreshedActionCandidates,
          );
          if (matchedActionCandidatesForAnswer.length === 0) {
            return prev;
          }

          const next = [...prev];
          next[assistantIndex] = {
            ...next[assistantIndex],
            actionCandidates: matchedActionCandidatesForAnswer,
          };
          return next;
        });
        if (autoProposeActionsAllowedRef.current) {
          matchedActionCandidatesForAnswer
            .filter((candidate) => !candidate.planDisabledReason)
            .forEach((candidate) => {
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
          setMessages((prev) =>
            markLastAssistantStreaming(
              setLastAssistantContentIfEmpty(prev, '응답 생성을 중지했습니다.'),
              false,
            ),
          );
        } else {
          markRunningProgressFailed(error instanceof Error ? error.message : 'AI response failed.');
          setMessages((prev) => markLastAssistantStreaming(prev, false));
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
      refreshAiopsActionCandidates,
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

  const effectiveSessionActionRefs = React.useMemo(() => {
    const activeHistoryRefs =
      conversationHistory.find((conversation) => conversation.id === activeSessionId)?.actionRefs ??
      [];

    return activeHistoryRefs.reduce(
      (refs, ref) => mergeConversationActionRefs(refs, ref),
      sessionActionRefs,
    );
  }, [activeSessionId, conversationHistory, sessionActionRefs]);

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
	      toggleConversationPinned={toggleConversationPinned}
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
          aria-label="Open AIOps for OCP"
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
            aria-label="AIOps for OCP"
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
                        const isAssistantMessageWithContent =
                          message.role === 'assistant' && hasContent;
                        const messageActionAnchor =
                          message.role === 'assistant' ? actionAnchorForMessageIndex(index) : undefined;
                        const storedActionCandidates = message.actionCandidates ?? [];
                        const matched =
                          isAssistantMessageWithContent
                            ? storedActionCandidates.length > 0
                              ? storedActionCandidates
                              : isLatestAssistantMessage
                                ? matchActionCandidatesForMessage(message.content, actionCandidates)
                                : []
                            : [];
                        const matchedActionCandidates = dedupeActionCandidates(matched);
                        const createPlanDisabledReason =
                          executionModeAllowsActions(executionMode)
                            ? ''
                            : '읽기 전용: 후보만 표시';
                        const answerActionRecords =
                          isAssistantMessageWithContent
                            ? latestAnswerActionRecords({
                                actionRefs: effectiveSessionActionRefs,
                                aiopsStatus,
                                executionMode,
                                messageAnchor: messageActionAnchor,
                                messageContent: message.content,
                              })
                            : [];
                        const exactAnswerActionRefs =
                          isAssistantMessageWithContent && messageActionAnchor
                            ? effectiveSessionActionRefs.filter(
                                (ref) => ref.messageAnchor === messageActionAnchor,
                              )
                            : [];
                        const answerActionRefs =
                          exactAnswerActionRefs.length > 0
                            ? sortConversationActionRefsForDisplay(exactAnswerActionRefs).slice(0, 3)
                            : isLatestAssistantMessage && hasContent
                              ? sortConversationActionRefsForDisplay(effectiveSessionActionRefs).slice(0, 3)
                              : [];
                        const pendingActionCandidates = pendingActionCandidatesForRefs(
                          matchedActionCandidates,
                          answerActionRefs,
                        );
                        const candidateActionRecords =
                          isLatestAssistantMessage &&
                          hasContent &&
                          answerActionRecords.length === 0 &&
                          answerActionRefs.length === 0
                            ? actionRecordsForMatchedCandidates(
                                aiopsStatus,
                                executionMode,
                                matchedActionCandidates,
                              )
                            : [];
                        const resolvedAnswerActionRecords =
                          answerActionRecords.length > 0 ? answerActionRecords : candidateActionRecords;
                        const candidateActionRefsById =
                          groupActionRefsByCandidateId(answerActionRefs);
                        const candidateActionRecordsById = groupActionRecordsByCandidateId(
                          resolvedAnswerActionRecords,
                          answerActionRefs,
                        );
                        const visibleActionCandidates =
                          Object.keys(candidateActionRefsById).length > 0
                            ? matchedActionCandidates
                            : pendingActionCandidates;
                        const inlineActionRecordKeys = new Set(
                          Object.values(candidateActionRecordsById)
                            .flat()
                            .map(actionRecordInlineKey),
                        );
                        const inlineActionActivityVisible = visibleActionCandidates.some(
                          (candidate) =>
                            (candidateActionRecordsById[candidate.id]?.length ?? 0) > 0 ||
                            (candidateActionRefsById[candidate.id]?.length ?? 0) > 0,
                        );
                        const remainingAnswerActionRecords = resolvedAnswerActionRecords.filter(
                          (record) => !inlineActionRecordKeys.has(actionRecordInlineKey(record)),
                        );
                        const remainingAnswerActionRefs = answerActionRefs.filter(
                          (ref) => !ref.candidateId,
                        );
                        const showCreateActionPlanButtons =
                          visibleActionCandidates.length > 0;
                        const showActionPrepGroup =
                          Boolean(message.toolPlan) && showCreateActionPlanButtons;
                        const waitingForContent =
                          activeMessage && message.role === 'assistant' && !hasContent;
                        const assistantStillStreaming =
                          message.role === 'assistant' && message.streaming === true;
                        const canShowAssistantPostAnswer =
                          message.role === 'assistant' && hasContent && !assistantStillStreaming;
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
                                  {renderFormattedContent(
                                    message,
                                    setPreviewAttachment,
                                    uiLanguage,
                                  )}
                                </div>
                              )}
                              {canShowAssistantPostAnswer &&
                                (
                                  <AssistantEvidenceFooter
                                    footer={message.evidenceFooter}
                                    language={uiLanguage}
                                    messageContent={message.content}
                                  />
                                )}
                              {canShowAssistantPostAnswer &&
                                showActionPrepGroup &&
                                (
                                  <div className="komsco-ai__action-prep" data-aiops-action-prep>
                                    <AssistantToolPlanFooter
                                      executionMode={executionMode}
                                      language={uiLanguage}
                                      toolPlan={message.toolPlan}
                                    />
                                    <AssistantCreateActionPlanButtons
                                      actionFeedback={actionCandidateFeedback}
                                      actionRecordsByCandidateId={candidateActionRecordsById}
                                      actionRefsByCandidateId={candidateActionRefsById}
                                      aiopsStatus={aiopsStatus}
                                      busyActionId={aiopsActionBusyId}
		                                    busyCandidateId={busyActionCandidateId}
		                                    candidates={visibleActionCandidates}
                                      createDisabledReason={createPlanDisabledReason}
                                      executionMode={executionMode}
		                                    language={uiLanguage}
                                      onAction={handleAiopsAction}
		                                    onCreatePlan={handleCreateActionPlanFromChat}
                                      resolveAction={getAiopsRecordAction}
		                                  />
                                  </div>
                                )}
                              {canShowAssistantPostAnswer &&
                                !showActionPrepGroup &&
                                <AssistantToolPlanFooter
                                  executionMode={executionMode}
                                  language={uiLanguage}
                                  toolPlan={message.toolPlan}
                                />}
                              {canShowAssistantPostAnswer &&
                                !showActionPrepGroup &&
                                showCreateActionPlanButtons &&
                                (
	                                  <AssistantCreateActionPlanButtons
	                                      actionFeedback={actionCandidateFeedback}
                                      actionRecordsByCandidateId={candidateActionRecordsById}
                                      actionRefsByCandidateId={candidateActionRefsById}
                                      aiopsStatus={aiopsStatus}
                                      busyActionId={aiopsActionBusyId}
		                                    busyCandidateId={busyActionCandidateId}
		                                    candidates={visibleActionCandidates}
                                      createDisabledReason={createPlanDisabledReason}
                                      executionMode={executionMode}
		                                    language={uiLanguage}
                                      onAction={handleAiopsAction}
		                                    onCreatePlan={handleCreateActionPlanFromChat}
                                      resolveAction={getAiopsRecordAction}
		                                  />
                                )}
                              {canShowAssistantPostAnswer &&
                                (
                                  <AssistantAnswerActions
                                    aiopsActionError={aiopsActionError}
                                    aiopsActionNotice={
                                      inlineActionActivityVisible ? '' : aiopsActionNotice
                                    }
                                    aiopsStatus={aiopsStatus}
                                    busyActionId={aiopsActionBusyId}
                                    executionMode={executionMode}
                                    fallbackRefs={remainingAnswerActionRefs}
                                    language={uiLanguage}
                                    onAction={handleAiopsAction}
                                    records={remainingAnswerActionRecords}
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
                                (message.role === 'user' ||
                                  (message.role === 'assistant' && !assistantStillStreaming)) && (
                                  <MessageActionFooter
                                    copied={copiedMessageIndex === index}
                                    copiedLabel={copy.answerCopied}
                                    copyLabel={copy.answerCopy}
                                    feedback={message.feedback}
                                    feedbackComment={message.feedbackComment}
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
                              {hasContent &&
                                message.role === 'assistant' &&
                                !assistantStillStreaming &&
                                message.feedback && (
                                <MessageFeedbackComment
                                  comment={message.feedbackComment}
                                  feedback={message.feedback}
                                  key={`${index}-${message.feedback}`}
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
          language={uiLanguage}
          onClose={() => setPreviewAttachment(null)}
        />
      )}
    </div>
  );
};

export default AssistantLauncher;
