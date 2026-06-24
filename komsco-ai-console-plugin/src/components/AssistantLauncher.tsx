import * as React from 'react';
import { Button, Card, CardBody, TextArea } from '@patternfly/react-core';
import { createPortal } from 'react-dom';
import {
  ArrowDownIcon,
  BarsIcon,
  CaretDownIcon,
  ClipboardIcon,
  CommentDotsIcon,
  CompressArrowsAltIcon,
  ExclamationCircleIcon,
  ExclamationTriangleIcon,
  ExpandArrowsAltIcon,
  GlobeIcon,
  HistoryIcon,
  LockIcon,
  LockOpenIcon,
  PaperclipIcon,
  PaperPlaneIcon,
  PlusIcon,
  ServerIcon,
  ShieldAltIcon,
  StopIcon,
  TerminalIcon,
  TimesIcon,
  UserCircleIcon,
  WrenchIcon,
} from '@patternfly/react-icons';
import {
  type AiopsRecord,
  type AiopsRuntimeStatus,
  type AuthSubject,
  type ChatContextMessage,
  type ClusterSummary,
  type EvidenceStatusItem,
  type ImageAttachment,
  approveActionPlan,
  createActionPlan,
  executeApprovedAction,
  fetchAiopsStatus,
  fetchClusterSummary,
  fetchConsoleUserSubject,
  streamChat,
} from '../services/aiGateway';
import { evidenceCount, redactSensitiveText, safeEvidenceText, shortDigest } from '../utils/evidenceDisplay';
import kIcon from '../assets/k_icon.png';
import komscoLogo from '../assets/komsco_logo.svg';
import './assistant.css';

const QUICK_PROMPTS = [
  {
    icon: <ServerIcon />,
    label: 'Node 상태',
    prompt: '현재 클러스터 노드 상태를 요약하고 이상 징후가 있으면 알려줘.',
  },
  {
    icon: <ExclamationTriangleIcon />,
    label: '최근 경고',
    prompt:
      '최근 OpenShift 경고와 우선 확인할 항목을 실제 근거와 추가 확인 필요 항목으로 구분해서 정리해줘.',
  },
  {
    icon: <TerminalIcon />,
    label: '조치 절차',
    prompt: '현재 화면 기준으로 안전한 확인 절차를 단계별로 제안해줘.',
  },
  {
    icon: <ShieldAltIcon />,
    label: '조치 후보 검토',
    prompt:
      '현재 화면의 대상에 대해 가능한 AIOps 조치 후보, 승인 필요 여부, 실행 전 검증 조건을 정리해줘.',
  },
];

const ASSISTANT_TASK_MODES: Array<{
  description: string;
  icon: React.ReactNode;
  label: string;
  value: AssistantTaskMode;
}> = [
  {
    description: '일반 질문과 상태 확인',
    icon: <CommentDotsIcon />,
    label: 'Ask',
    value: 'ask',
  },
  {
    description: '원인 분석과 점검 절차',
    icon: <WrenchIcon />,
    label: 'Troubleshooting',
    value: 'troubleshooting',
  },
];

const TASK_MODE_PLACEHOLDERS: Record<AssistantTaskMode, string> = {
  ask: '무엇을 확인할까요?',
  troubleshooting: '어떤 문제를 점검할까요?',
};

type Message = {
  role: 'user' | 'assistant' | 'system';
  attachments?: ImageAttachment[];
  content: string;
  evidenceFooter?: EvidenceFooter;
  fallbackAnswer?: boolean;
  gatewayContextDigest?: string;
  progressSteps?: ProgressStep[];
};

type EvidenceFooterRef = {
  contentDigest?: string;
  evidenceId?: string;
  sourceType?: string;
  status?: string;
  summary?: string;
  type?: string;
};

type EvidenceFooterMissing = {
  contentDigest?: string;
  evidenceId?: string;
  reason?: string;
  type?: string;
};

type EvidenceFooter = {
  collectedCount: number;
  collectedRefs: EvidenceFooterRef[];
  contextId?: string;
  digest?: string;
  failedCount: number;
  failedRefs: EvidenceFooterRef[];
  missing: EvidenceFooterMissing[];
  missingCount: number;
  phase?: string;
  status?: string;
};

type AiopsExecutionMode = 'read-only' | 'execute' | 'unrestricted';
type AssistantTaskMode = 'ask' | 'troubleshooting';
type UiLanguage = 'ko' | 'en';
type PanelResizeDirection = 'n' | 'ne' | 'e' | 'se' | 's' | 'sw' | 'w' | 'nw';

type ProgressStatus = 'running' | 'completed' | 'failed';

type ProgressStep = {
  id: string;
  name: string;
  title: string;
  status: ProgressStatus;
  startedAt: number;
  detail?: string;
  elapsedMs?: number;
  endedAt?: number;
  serverName?: string;
  summary?: string;
};

type ConversationHistoryItem = {
  id: string;
  title: string;
  updatedAt: number;
  conversationId?: string;
  messages: Message[];
};

type ToolStreamEvent = {
  type: 'tool_call' | 'tool_result';
  name: string;
  id?: string;
  args?: unknown;
  detail?: string;
  fallbackAnswer?: boolean;
  gatewayContextDigest?: string;
  result?: unknown;
  serverName?: string;
  status?: string;
  summary?: string;
};

type RunStatusEvent = {
  type: 'run_status';
  elapsedMs?: number;
  gatewayContextDigest?: string;
  message: string;
  rcaContextDigest?: string;
  runId?: string;
  stage: string;
};

type LightspeedStatusUpdate = {
  fallbackActive?: boolean;
  lastContextDigest?: string | undefined;
  lastError?: string | undefined;
  lastStatus?: string | undefined;
  streamProbe?: string | undefined;
};

const URL_PATTERN = /(https?:\/\/[^\s]+)/g;
const MARKDOWN_LINK_PATTERN = /^\[(.+)\]\((https?:\/\/[^)]+)\)$/;
const INLINE_PATTERN = /(\[[^\n]+\]\(https?:\/\/[^)]+\)|\*\*[^*]+\*\*|`[^`]+`|https?:\/\/[^\s]+)/g;
const FAILED_TOOL_STATUSES = new Set(['error', 'failed', 'failure']);
const ACCEPTED_IMAGE_MIME_TYPES = new Set(['image/gif', 'image/jpeg', 'image/png', 'image/webp']);
const MAX_IMAGE_ATTACHMENTS = 4;
const MAX_IMAGE_ATTACHMENT_BYTES = 2 * 1024 * 1024;
const MAX_IMAGE_ATTACHMENT_TOTAL_BYTES = 6 * 1024 * 1024;
const MAX_RECENT_CONTEXT_MESSAGES = 8;
const CLUSTER_SUMMARY_REFRESH_MS = 10 * 1000;
const DEFAULT_AIOPS_EXECUTION_MODE: AiopsExecutionMode = 'read-only';
const HISTORY_DRAWER_WIDTH = 236;
const SCROLL_BOTTOM_THRESHOLD_PX = 80;
const GATEWAY_PREP_TOOLS = new Set(['access_check', 'attachment_check']);
const GATEWAY_PREP_STEP_ID = 'gateway-request-prep';
const RUN_LOOP_STEP_ID = 'assistant-run-loop';
const RESPONSE_WAIT_STEP_ID = 'assistant-response-wait';
const ANSWER_STREAM_STEP_ID = 'assistant-answer-stream';
const TOOL_LABELS: Record<string, string> = {
  access_check: '접근 권한 확인',
  audit_record: '감사 기록',
  attachment_check: '이미지 첨부 확인',
  configuration_view: '클러스터 설정 조회',
  evidence_ref: '증거 참조 기록',
  events_list: '이벤트 조회',
  execute_instant_query: '현재 메트릭 조회',
  execute_range_query: '기간 메트릭 조회',
  get_alerts: 'OpenShift 경고 조회',
  get_label_names: '메트릭 라벨 조회',
  get_label_values: '메트릭 값 조회',
  get_series: '메트릭 시리즈 조회',
  get_silences: '알림 침묵 조회',
  get_resources: '리소스 목록 조회',
  helm_list: 'Helm 릴리스 조회',
  list_metrics: '메트릭 목록 조회',
  list_resources: '리소스 목록 조회',
  namespaces_list: '네임스페이스 조회',
  nodes_log: '노드 로그 조회',
  nodes_stats_summary: '노드 상세 사용량 조회',
  nodes_top: '노드 사용량 조회',
  natural_action_execute: '자연어 조치 실행',
  natural_action_followup: '후속 조치 실행',
  natural_action_plan: '자연어 조치 계획 생성',
  natural_action_unresolved: '조치 대상 확인',
  pod_count_deployment_lookup: 'Deployment 조회',
  pod_count_investigation: 'Pod 개수 결과',
  pod_count_pod_lookup: 'Pod 목록 조회',
  pod_count_scope_resolve: '조회 범위 결정',
  pod_count_selector_match: 'Pod 매칭 계산',
  pods_get: 'Pod 상세 조회',
  pods_list: 'Pod 목록 조회',
  pods_list_in_namespace: 'Namespace Pod 조회',
  pods_log: 'Pod 로그 조회',
  pods_top: 'Pod 사용량 조회',
  projects_list: '프로젝트 조회',
  resources_get: '리소스 상세 조회',
  resources_list: '리소스 목록 조회',
  policy_check: '정책 확인',
  product_access_review: '제품 접근 권한 확인',
  security_boundary: '보안 경계 확인',
  show_timeseries: '시계열 차트 준비',
  subject_review: '사용자 주체 확인',
  vision_analysis: '이미지 분석',
};
const createPendingAiopsStatus = (): AiopsRuntimeStatus => ({
  spec: {
    capabilities: {
      actionExecutorConfigured: false,
      diagnosticsControllerConfigured: false,
      diagnosticsEnabled: false,
      mutationsEnabled: false,
      rag: {
        accessPath: 'gateway-only',
        aclRequired: true,
        backendType: 'pgvector',
        collection: 'komsco-aiops-runbooks',
        directDatabaseAccess: false,
        embeddingModel: 'not_configured',
        endpointConfigured: false,
        reason: 'RAG status is pending until the gateway status call completes.',
        requiredMetadata: ['documentId', 'sourceUri', 'sourceType', 'checksum', 'version', 'aclGroups'],
        status: 'pending',
        vectorDimensions: 0,
      },
      recordStoreEnabled: false,
      unrestrictedCommandsEnabled: false,
    },
    safetyContract: {
      adapterStatus: [],
      allowedReadOnlyVerbs: ['get', 'list', 'watch'],
      capabilityGates: {},
      evidenceStatus: [],
      forbiddenActions: ['create', 'update', 'patch', 'delete', 'exec', 'portforward', 'restart', 'scale', 'rollout'],
      mode: 'read_only',
      product: {
        mission: 'Evidence-first OpenShift operations assistant',
        mode: 'read_only_first',
        name: 'Cywell AI',
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
const PREP_SUBTASKS = [
  {
    detail: 'Console UserToken과 요청 본문을 확인한 뒤 Lightspeed로 전달합니다.',
    label: '요청 확인',
    toolName: 'access_check',
  },
  {
    detail: '첨부 이미지 형식과 크기를 검증한 뒤 메타데이터만 Lightspeed 컨텍스트에 포함합니다.',
    label: '첨부 확인',
    toolName: 'attachment_check',
  },
];
const RESPONSE_WAIT_PHASES = [
  {
    activity: 'Gateway가 OLS streaming endpoint로 요청을 전달했습니다.',
    title: 'OLS 질의 전달',
  },
  {
    activity: 'OpenShift Lightspeed가 UserToken 기준으로 질의를 처리합니다.',
    title: 'Lightspeed 처리',
  },
  {
    activity: 'Lightspeed에서 필요한 도구 호출 또는 답변 생성을 기다립니다.',
    title: '응답 준비',
  },
  {
    activity: 'Lightspeed 응답 스트림을 브라우저로 중계할 준비를 합니다.',
    title: '답변 스트림 준비',
  },
];

const UI_COPY: Record<
  UiLanguage,
  {
    emptyHistory: string;
    history: string;
    inputPlaceholder: string;
    newChat: string;
    openSidebar: string;
    sidebar: string;
    switchLanguage: string;
  }
> = {
  ko: {
    emptyHistory: '아직 저장된 대화가 없습니다.',
    history: '지난 대화',
    inputPlaceholder: '현재 화면이나 클러스터 상태를 질문하세요',
    newChat: '새 채팅',
    openSidebar: '대화 사이드바',
    sidebar: '대화 기록',
    switchLanguage: 'English',
  },
  en: {
    emptyHistory: 'No saved conversations yet.',
    history: 'Recent chats',
    inputPlaceholder: 'Ask about the current screen or cluster state',
    newChat: 'New chat',
    openSidebar: 'Conversation sidebar',
    sidebar: 'Conversation history',
    switchLanguage: 'Korean',
  },
};

const getMessageLabel = (role: Message['role']): string => {
  if (role === 'user') {
    return '사용자';
  }

  if (role === 'system') {
    return '시스템';
  }

  return 'KOMSCO AI AGENT';
};

const MessageIcon: React.FC<{ role: Message['role'] }> = ({ role }) => {
  if (role === 'user') {
    return <UserCircleIcon />;
  }

  if (role === 'system') {
    return <ExclamationCircleIcon />;
  }

  return <img alt="" className="komsco-ai__message-logo" src={kIcon} />;
};

const TypingIndicator: React.FC = () => (
  <div className="komsco-ai__typing" aria-label="응답 생성 중">
    <span />
    <span />
    <span />
  </div>
);

const normalizeToolName = (name: string): string =>
  name
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, '_');

const formatToolTitle = (name: string): string => {
  const normalizedName = normalizeToolName(name);

  if (TOOL_LABELS[normalizedName]) {
    return TOOL_LABELS[normalizedName];
  }

  return normalizedName
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
};

const formatDuration = (milliseconds: number): string => {
  const safeMilliseconds = Math.max(0, milliseconds);

  if (safeMilliseconds < 1000) {
    return `${Math.max(1, Math.round(safeMilliseconds))}ms`;
  }

  const totalSeconds = Math.round(safeMilliseconds / 1000);

  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;

  if (minutes > 0) {
    return `${minutes}분 ${seconds}초`;
  }

  return `${seconds}초`;
};

const formatFileSize = (size: number): string => {
  if (size < 1024) {
    return `${size} B`;
  }

  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }

  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
};

const createRunId = (): string =>
  `run-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;

const getConversationTitle = (messages: Message[], language: UiLanguage): string => {
  const firstUserMessage = messages.find((message) => message.role === 'user');
  const content = firstUserMessage?.content.trim();

  if (!content && firstUserMessage?.attachments?.length) {
    return language === 'ko' ? '이미지 첨부 대화' : 'Image conversation';
  }

  if (!content) {
    return language === 'ko' ? '새 대화' : 'New conversation';
  }

  return content.length > 34 ? `${content.slice(0, 34)}...` : content;
};

const formatHistoryTime = (timestamp: number): string =>
  new Date(timestamp).toLocaleTimeString('ko-KR', {
    hour: '2-digit',
    minute: '2-digit',
  });

const getAttachmentPreviewUrl = (attachment: ImageAttachment): string =>
  `data:${attachment.mimeType};base64,${attachment.data}`;

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

const setLastAssistantContentIfEmpty = (
  messages: Message[],
  content: string,
): Message[] => {
  const assistantIndex = findLastAssistantIndex(messages);
  if (assistantIndex < 0 || messages[assistantIndex].content.trim()) {
    return messages;
  }

  const next = [...messages];
  next[assistantIndex] = {
    ...next[assistantIndex],
    content,
  };

  return next;
};

const asRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {};

const asRecordArray = (value: unknown): Record<string, unknown>[] =>
  Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === 'object' && !Array.isArray(item))) : [];

const normalizeEvidenceRef = (value: Record<string, unknown>): EvidenceFooterRef => ({
  contentDigest: safeEvidenceText(value.contentDigest),
  evidenceId: safeEvidenceText(value.evidenceId),
  sourceType: safeEvidenceText(value.sourceType),
  status: safeEvidenceText(value.status),
  summary: safeEvidenceText(value.summary || value.eventName || 'evidence'),
  type: safeEvidenceText(value.type, 'evidence'),
});

const normalizeMissingEvidence = (value: Record<string, unknown>): EvidenceFooterMissing => ({
  contentDigest: safeEvidenceText(value.contentDigest),
  evidenceId: safeEvidenceText(value.evidenceId),
  reason: safeEvidenceText(value.reason || 'additional evidence required'),
  type: safeEvidenceText(value.type, 'evidence'),
});

const evidenceStatusCounts = (items: EvidenceStatusItem[] | undefined) => ({
  collected: (items ?? [])
    .filter((item) => item.status === 'collected')
    .reduce((total, item) => total + item.count, 0),
  missing: (items ?? [])
    .filter((item) => item.status === 'missing')
    .reduce((total, item) => total + Math.max(item.count, 1), 0),
});

const buildEvidenceFooter = (
  context: unknown,
  evidenceStatus?: EvidenceStatusItem[],
  status?: string,
): EvidenceFooter | undefined => {
  const contextRecord = asRecord(context);
  if (Object.keys(contextRecord).length === 0) {
    return undefined;
  }

  const metadata = asRecord(contextRecord.metadata);
  const evidence = asRecord(contextRecord.evidence);
  const summary = asRecord(evidence.summary);
  const collectedRefs = asRecordArray(evidence.collectedRefs).map(normalizeEvidenceRef);
  const failedRefs = asRecordArray(evidence.failedRefs).map(normalizeEvidenceRef);
  const missing = asRecordArray(evidence.missing).map(normalizeMissingEvidence);
  const statusCounts = evidenceStatusCounts(evidenceStatus);

  return {
    collectedCount: evidenceCount(summary.collectedCount, statusCounts.collected, collectedRefs.length),
    collectedRefs,
    contextId: safeEvidenceText(metadata.contextId),
    digest: safeEvidenceText(metadata.digest),
    failedCount: evidenceCount(summary.failedCount, 0, failedRefs.length),
    failedRefs,
    missing,
    missingCount: evidenceCount(summary.missingCount, statusCounts.missing, missing.length),
    phase: safeEvidenceText(metadata.phase),
    status: safeEvidenceText(status),
  };
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
    fallbackAnswer: true,
    gatewayContextDigest: gatewayContextDigest || next[assistantIndex].gatewayContextDigest,
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

const getElapsedMs = (step: ProgressStep): number => {
  if (step.status === 'running') {
    return Date.now() - step.startedAt;
  }

  return step.elapsedMs ?? (step.endedAt ?? step.startedAt) - step.startedAt;
};

const isResponseWaitStep = (step: ProgressStep): boolean =>
  step.id.startsWith(RESPONSE_WAIT_STEP_ID);

const isAnswerStreamStep = (step: ProgressStep): boolean => step.id === ANSWER_STREAM_STEP_ID;

const getResponseWaitMessageIndex = (startedAt: number): number => {
  const elapsedSeconds = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));

  return Math.min(RESPONSE_WAIT_PHASES.length - 1, Math.floor(elapsedSeconds / 3));
};

const getResponseWaitMessage = (startedAt: number): string => {
  const phase = RESPONSE_WAIT_PHASES[getResponseWaitMessageIndex(startedAt)];

  return `${phase.title} 중`;
};

const cleanMarkdownLabel = (label: string): string =>
  label
    .replace(/\\(\[|\])/g, '$1')
    .replace(/\s+/g, ' ')
    .trim();

const parseMarkdownLink = (line: string): { href: string; label: string } | null => {
  const match = line.match(MARKDOWN_LINK_PATTERN);

  if (!match) {
    return null;
  }

  return {
    href: match[2].replace(/[),.;]+$/, ''),
    label: cleanMarkdownLabel(match[1]),
  };
};

const trimIndentedCodeLine = (line: string): string => line.replace(/^( {4}|\t)/, '');

const isCommandLikeLine = (line: string): boolean =>
  /^(#|oc\s+|kubectl\s+|helm\s+|etcdctl\s+|curl\s+|podman\s+|docker\s+|jq\s+|grep\s+|watch\s+|export\s+)/.test(
    line.trim(),
  );

const collectIndentedBlock = (lines: string[], startIndex: number): string[] => {
  const block: string[] = [];
  let index = startIndex;

  while (index < lines.length) {
    const candidate = lines[index];
    if (!/^( {4}|\t)/.test(candidate) || !candidate.trim()) {
      break;
    }

    block.push(trimIndentedCodeLine(candidate));
    index += 1;
  }

  return block;
};

const renderCodeBlock = (lines: string[], key: string, language?: string): React.ReactNode => {
  const code = lines.join('\n').trimEnd();

  return (
    <pre
      className="komsco-ai__formatted-code-block"
      data-language={language || undefined}
      key={key}
    >
      <code>{code}</code>
      <button
        aria-label="명령 복사"
        className="komsco-ai__code-copy"
        onClick={() => {
          if (navigator.clipboard) {
            void navigator.clipboard.writeText(redactSensitiveText(code));
          }
        }}
        type="button"
      >
        <ClipboardIcon />
      </button>
    </pre>
  );
};

const getStepActivity = (step: ProgressStep): string => {
  if (step.status === 'failed') {
    return '오류 확인 필요';
  }

  if (step.id === GATEWAY_PREP_STEP_ID) {
    if (step.status === 'completed') {
      return '요청 준비 완료';
    }

    const completedCount = PREP_SUBTASKS.filter((item) =>
      step.detail?.includes(formatToolTitle(item.toolName)),
    ).length;
    const currentTask = PREP_SUBTASKS[Math.min(completedCount, PREP_SUBTASKS.length - 1)];

    return `${currentTask.label} 중`;
  }

  if (isResponseWaitStep(step) && step.status === 'running') {
    return getResponseWaitMessage(step.startedAt);
  }

  if (step.name === RUN_LOOP_STEP_ID) {
    return step.status === 'running' ? step.summary || '장기 실행 루프 유지 중' : '실행 루프 완료';
  }

  if (isAnswerStreamStep(step)) {
    return step.status === 'running' ? '본문을 실시간으로 수신하고 있습니다.' : '답변 생성 완료';
  }

  if (step.status === 'running') {
    return step.summary || '도구 응답을 기다리는 중입니다.';
  }

  return step.summary || '완료';
};

const renderInlineText = (text: string, keyPrefix: string): React.ReactNode[] =>
  text.split(INLINE_PATTERN).map((part, index) => {
    const markdownLink = parseMarkdownLink(part);
    if (markdownLink) {
      return (
        <a
          className="komsco-ai__formatted-link"
          href={markdownLink.href}
          key={`${keyPrefix}-md-link-${index}`}
          rel="noreferrer"
          target="_blank"
          title={markdownLink.href}
        >
          {markdownLink.label}
        </a>
      );
    }

    if (part.match(URL_PATTERN)) {
      const href = part.replace(/[),.;]+$/, '');
      const suffix = part.slice(href.length);

      return (
        <React.Fragment key={`${keyPrefix}-url-${index}`}>
          <a className="komsco-ai__formatted-link" href={href} rel="noreferrer" target="_blank">
            {href}
          </a>
          {suffix}
        </React.Fragment>
      );
    }

    if (part.startsWith('`') && part.endsWith('`')) {
      return (
        <code className="komsco-ai__formatted-code" key={`${keyPrefix}-code-${index}`}>
          {part.slice(1, -1)}
        </code>
      );
    }

    if (part.startsWith('**') && part.endsWith('**')) {
      return (
        <strong className="komsco-ai__formatted-strong" key={`${keyPrefix}-strong-${index}`}>
          {renderInlineText(part.slice(2, -2), `${keyPrefix}-strong-${index}`)}
        </strong>
      );
    }

    return <React.Fragment key={`${keyPrefix}-text-${index}`}>{part}</React.Fragment>;
  });

const renderAttachmentGrid = (
  attachments: ImageAttachment[] | undefined,
  keyPrefix: string,
  onPreview: React.Dispatch<React.SetStateAction<ImageAttachment | null>>,
): React.ReactNode => {
  if (!attachments || attachments.length === 0) {
    return null;
  }

  return (
    <div className="komsco-ai__attachment-grid" key={`${keyPrefix}-attachments`}>
      {attachments.map((attachment) => (
        <button
          aria-label={`${attachment.name} 크게 보기`}
          className="komsco-ai__attachment-card"
          key={attachment.id}
          onClick={() => onPreview(attachment)}
          title={`${attachment.name} 크게 보기`}
          type="button"
        >
          <img
            alt={attachment.name}
            className="komsco-ai__attachment-image"
            src={getAttachmentPreviewUrl(attachment)}
          />
          <div className="komsco-ai__attachment-meta">
            <span className="komsco-ai__attachment-name">{attachment.name}</span>
            <span className="komsco-ai__attachment-size">
              {attachment.mimeType} · {formatFileSize(attachment.size)}
            </span>
          </div>
        </button>
      ))}
    </div>
  );
};

const renderFormattedContent = (
  message: Message,
  onPreviewAttachment: React.Dispatch<React.SetStateAction<ImageAttachment | null>>,
): React.ReactNode => {
  if (message.role === 'user') {
    return (
      <div className="komsco-ai__message-text">
        {message.content && <div>{message.content}</div>}
        {renderAttachmentGrid(message.attachments, 'message', onPreviewAttachment)}
      </div>
    );
  }

  const lines = message.content.split('\n');
  const nodes: React.ReactNode[] = [];
  let bulletItems: string[] = [];
  let orderedItems: string[] = [];
  let codeBlockLanguage = '';
  let codeBlockLines: string[] = [];
  let inCodeBlock = false;
  let referenceItems: { href: string; label: string }[] = [];

  const flushBullets = () => {
    if (bulletItems.length === 0) {
      return;
    }

    const listIndex = nodes.length;
    nodes.push(
      <ul className="komsco-ai__formatted-list" key={`list-${listIndex}`}>
        {bulletItems.map((item, index) => (
          <li className="komsco-ai__formatted-list-item" key={`list-${listIndex}-${index}`}>
            {renderInlineText(item, `list-${listIndex}-${index}`)}
          </li>
        ))}
      </ul>,
    );
    bulletItems = [];
  };

  const flushOrdered = () => {
    if (orderedItems.length === 0) {
      return;
    }

    const listIndex = nodes.length;
    nodes.push(
      <ol
        className="komsco-ai__formatted-list komsco-ai__formatted-list--ordered"
        key={`ordered-${listIndex}`}
      >
        {orderedItems.map((item, index) => (
          <li className="komsco-ai__formatted-list-item" key={`ordered-${listIndex}-${index}`}>
            {renderInlineText(item, `ordered-${listIndex}-${index}`)}
          </li>
        ))}
      </ol>,
    );
    orderedItems = [];
  };

  const flushReferences = () => {
    if (referenceItems.length === 0) {
      return;
    }

    const referenceIndex = nodes.length;
    nodes.push(
      <div className="komsco-ai__reference-list" key={`references-${referenceIndex}`}>
        {referenceItems.map((item, index) => (
          <a
            className="komsco-ai__reference-link"
            href={item.href}
            key={`references-${referenceIndex}-${index}`}
            rel="noreferrer"
            target="_blank"
            title={item.href}
          >
            <span className="komsco-ai__reference-title">{item.label}</span>
          </a>
        ))}
      </div>,
    );
    referenceItems = [];
  };

  const flushCodeBlock = () => {
    if (!inCodeBlock && codeBlockLines.length === 0) {
      return;
    }

    const codeIndex = nodes.length;
    nodes.push(renderCodeBlock(codeBlockLines, `code-block-${codeIndex}`, codeBlockLanguage));
    codeBlockLanguage = '';
    codeBlockLines = [];
    inCodeBlock = false;
  };

  const flushLists = () => {
    flushBullets();
    flushOrdered();
  };

  const flushAll = () => {
    flushCodeBlock();
    flushLists();
    flushReferences();
  };

  const parseTableRow = (line: string): string[] =>
    line
      .replace(/^\|/, '')
      .replace(/\|$/, '')
      .split('|')
      .map((cell) => cell.trim());

  const isTableSeparator = (line: string): boolean =>
    /^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$/.test(line);

  for (let index = 0; index < lines.length; index += 1) {
    let rawLine = lines[index];
    let line = rawLine.trim();

    if (line.startsWith('```')) {
      if (inCodeBlock) {
        flushCodeBlock();
        continue;
      }

      flushAll();
      inCodeBlock = true;
      codeBlockLanguage = line.replace(/^```/, '').trim();
      continue;
    }

    if (inCodeBlock) {
      if (line === '`') {
        flushCodeBlock();
        continue;
      }

      codeBlockLines.push(rawLine);
      continue;
    }

    if (/^( {4}|\t)/.test(rawLine) && line) {
      const codeLines = collectIndentedBlock(lines, index);
      if (codeLines.some(isCommandLikeLine)) {
        flushAll();
        nodes.push(renderCodeBlock(codeLines, `indented-code-${index}`));
        index += codeLines.length - 1;
        continue;
      }

      rawLine = trimIndentedCodeLine(rawLine);
      line = rawLine.trim();
    }

    if (!line) {
      flushAll();
      continue;
    }

    if (line === '---') {
      flushAll();
      nodes.push(<div className="komsco-ai__formatted-divider" key={`divider-${index}`} />);
      continue;
    }

    const nextLine = lines[index + 1]?.trim() ?? '';
    if (line.includes('|') && isTableSeparator(nextLine)) {
      flushAll();
      const headers = parseTableRow(line);
      const rows: string[][] = [];
      let rowIndex = index + 2;

      while (rowIndex < lines.length) {
        const rowLine = lines[rowIndex].trim();
        if (!rowLine || !rowLine.includes('|')) {
          break;
        }

        rows.push(parseTableRow(rowLine));
        rowIndex += 1;
      }

      nodes.push(
        <div className="komsco-ai__table-wrap" key={`table-${index}`}>
          <table className="komsco-ai__table">
            <thead>
              <tr>
                {headers.map((header, headerIndex) => (
                  <th key={`table-${index}-head-${headerIndex}`}>
                    {renderInlineText(header, `table-${index}-head-${headerIndex}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, tableRowIndex) => (
                <tr key={`table-${index}-row-${tableRowIndex}`}>
                  {headers.map((_, cellIndex) => (
                    <td key={`table-${index}-row-${tableRowIndex}-${cellIndex}`}>
                      {renderInlineText(
                        row[cellIndex] ?? '',
                        `table-${index}-${tableRowIndex}-${cellIndex}`,
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      index = rowIndex - 1;
      continue;
    }

    const bullet = line.match(/^[-*]\s+(.+)$/);
    if (bullet) {
      flushOrdered();
      flushReferences();
      bulletItems.push(bullet[1]);
      continue;
    }

    const ordered = line.match(/^\d+\.\s+(.+)$/);
    if (ordered) {
      flushBullets();
      flushReferences();
      orderedItems.push(ordered[1]);
      continue;
    }

    const markdownReference = parseMarkdownLink(line);
    if (markdownReference) {
      flushLists();
      referenceItems.push(markdownReference);
      continue;
    }

    const reference = line.match(/^(.{2,120}?):\s+(https?:\/\/\S+)$/);
    if (reference) {
      flushLists();
      referenceItems.push({
        href: reference[2].replace(/[),.;]+$/, ''),
        label: cleanMarkdownLabel(reference[1]),
      });
      continue;
    }

    flushAll();

    if (line.startsWith('#')) {
      nodes.push(
        <div className="komsco-ai__formatted-heading" key={`heading-${index}`}>
          {renderInlineText(line.replace(/^#+\s*/, ''), `heading-${index}`)}
        </div>,
      );
      continue;
    }

    nodes.push(
      <div className="komsco-ai__formatted-line" key={`line-${index}`}>
        {renderInlineText(line, `line-${index}`)}
      </div>,
    );
  }

  flushAll();

  flushCodeBlock();

  return <div className="komsco-ai__formatted">{nodes}</div>;
};

const buildEvidenceCopyText = (footer: EvidenceFooter | undefined): string => {
  if (!footer) {
    return '';
  }

  const lines = [
    '',
    '[Evidence]',
    `- context: ${footer.contextId || shortDigest(footer.digest) || 'unavailable'}`,
    `- collected: ${footer.collectedCount}`,
    `- additional_check_required: ${footer.missingCount}`,
  ];

  footer.collectedRefs.slice(0, 3).forEach((ref) => {
    lines.push(
      `- ref: ${ref.evidenceId || 'evidence'} ${ref.type || 'evidence'} ${shortDigest(
        ref.contentDigest,
      )}`,
    );
  });

  footer.missing.slice(0, 3).forEach((item) => {
    lines.push(`- missing: ${item.type || 'evidence'} ${item.reason || 'additional evidence required'}`);
  });

  return lines.join('\n');
};

const renderEvidenceFooter = (footer: EvidenceFooter | undefined): React.ReactNode => {
  if (!footer) {
    return null;
  }

  const collectedRefs = footer.collectedRefs.slice(0, 3);
  const missing = footer.missing.slice(0, 3);
  const traceLabel = footer.contextId || shortDigest(footer.digest) || 'context pending';

  return (
    <div
      className="komsco-ai__evidence-footer"
      data-evidence-context-id={footer.contextId || ''}
      data-evidence-digest={footer.digest || ''}
    >
      <div className="komsco-ai__evidence-footer-head">
        <span className="komsco-ai__evidence-title">근거</span>
        <span className="komsco-ai__evidence-pill komsco-ai__evidence-pill--collected">
          수집 {footer.collectedCount}
        </span>
        <span className="komsco-ai__evidence-pill komsco-ai__evidence-pill--missing">
          추가 확인 {footer.missingCount}
        </span>
        <code>{traceLabel}</code>
      </div>

      {collectedRefs.length > 0 && (
        <div className="komsco-ai__evidence-list" aria-label="수집된 답변 근거">
          {collectedRefs.map((ref, index) => (
            <div className="komsco-ai__evidence-ref" key={`${ref.evidenceId || ref.type || 'ref'}-${index}`}>
              <strong>{ref.type || 'evidence'}</strong>
              <span>{ref.summary || ref.sourceType || 'runtime evidence'}</span>
              <code>{ref.evidenceId || shortDigest(ref.contentDigest) || 'ref'}</code>
            </div>
          ))}
        </div>
      )}

      {missing.length > 0 && (
        <div className="komsco-ai__evidence-missing" aria-label="추가 확인 필요 근거">
          {missing.map((item, index) => (
            <span key={`${item.type || 'missing'}-${index}`}>
              {item.type || 'evidence'}: {item.reason || '추가 확인 필요'}
            </span>
          ))}
        </div>
      )}
    </div>
  );
};

const getProgressSummary = (steps: ProgressStep[], active: boolean): string => {
  const firstStartedAt = steps[0]?.startedAt ?? Date.now();
  const lastEndedAt = steps.reduce(
    (latest, step) => Math.max(latest, step.endedAt ?? step.startedAt),
    firstStartedAt,
  );
  const elapsedMs = (active ? Date.now() : lastEndedAt) - firstStartedAt;
  const runningStep = steps.find((step) => step.status === 'running');

  if (active && runningStep) {
    return `${formatDuration(elapsedMs)} 동안 작업 중 · ${runningStep.title} · ${getStepActivity(
      runningStep,
    )}`;
  }

  return `${formatDuration(elapsedMs)} 동안 작업 완료`;
};

const getStepElapsed = (step: ProgressStep): string => {
  if (step.status === 'running') {
    return formatDuration(getElapsedMs(step));
  }

  return formatDuration(getElapsedMs(step));
};

const expandProgressStep = (step: ProgressStep): ProgressStep[] => {
  return [step];
};

const getDisplaySteps = (steps: ProgressStep[]): ProgressStep[] =>
  steps
    .flatMap(expandProgressStep)
    .filter((step) => step.name !== RUN_LOOP_STEP_ID)
    .filter(
      (step) =>
        !(isAnswerStreamStep(step) && step.status === 'completed' && getElapsedMs(step) < 300),
    );

const ProgressTimeline: React.FC<{ active: boolean; steps: ProgressStep[] }> = ({
  active,
  steps,
}) => {
  const displaySteps = getDisplaySteps(steps);

  if (displaySteps.length === 0) {
    return null;
  }

  return (
    <details className="komsco-ai__progress" key={active ? 'active' : 'complete'} open={active}>
      <summary className="komsco-ai__progress-summary">
        <span className="komsco-ai__progress-toggle" aria-hidden="true" />
        <span className="komsco-ai__progress-title">
          {getProgressSummary(displaySteps, active)}
        </span>
      </summary>
      <div className="komsco-ai__progress-list">
        {displaySteps.map((step) => {
          return (
            <div
              className={`komsco-ai__progress-step komsco-ai__progress-step--${step.status}`}
              key={step.id}
            >
              <span
                className={`komsco-ai__progress-status komsco-ai__progress-status--${step.status}`}
                aria-hidden="true"
              />
              <span className="komsco-ai__progress-step-copy">
                <span className="komsco-ai__progress-step-title">{step.title}</span>
                <span className="komsco-ai__progress-step-separator" aria-hidden="true">
                  ·
                </span>
                <span className="komsco-ai__progress-step-activity">{getStepActivity(step)}</span>
              </span>
              <span className="komsco-ai__progress-step-meta">{getStepElapsed(step)}</span>
            </div>
          );
        })}
      </div>
    </details>
  );
};

const formatSummaryTime = (updatedAt?: string): string => {
  if (!updatedAt) {
    return '수집 대기';
  }

  const date = new Date(updatedAt);
  if (Number.isNaN(date.getTime())) {
    return '수집됨';
  }

  return date.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
};

const getNodePressureLabel = (node: ClusterSummary['nodes']['items'][number]): string => {
  const pressures = [];
  if (node.pressures.disk) {
    pressures.push('Disk');
  }
  if (node.pressures.memory) {
    pressures.push('Memory');
  }
  if (node.pressures.pid) {
    pressures.push('PID');
  }

  return pressures.length > 0 ? `${pressures.join('/')} Pressure` : 'Pressure 없음';
};

const formatCpuUsage = (value?: string): string | null => {
  if (!value) {
    return null;
  }

  const trimmed = value.trim();
  const match = trimmed.match(/^(\d+(?:\.\d+)?)([a-zA-Z]*)$/);
  if (!match) {
    return trimmed;
  }

  const amount = Number(match[1]);
  if (!Number.isFinite(amount)) {
    return trimmed;
  }

  const unit = match[2];
  const cores =
    unit === 'n'
      ? amount / 1_000_000_000
      : unit === 'u'
        ? amount / 1_000_000
        : unit === 'm'
          ? amount / 1_000
          : amount;

  if (cores >= 1) {
    return `${cores.toFixed(cores >= 10 ? 0 : 1)} cores`;
  }

  return `${Math.max(1, Math.round(cores * 1000))} m`;
};

const formatMemoryUsage = (value?: string): string | null => {
  if (!value) {
    return null;
  }

  const trimmed = value.trim();
  const match = trimmed.match(/^(\d+(?:\.\d+)?)([a-zA-Z]*)$/);
  if (!match) {
    return trimmed;
  }

  const amount = Number(match[1]);
  if (!Number.isFinite(amount)) {
    return trimmed;
  }

  const unitMultipliers: Record<string, number> = {
    Ki: 1024,
    Mi: 1024 ** 2,
    Gi: 1024 ** 3,
    Ti: 1024 ** 4,
    K: 1000,
    M: 1000 ** 2,
    G: 1000 ** 3,
    T: 1000 ** 4,
    '': 1,
  };
  const multiplier = unitMultipliers[match[2]];
  if (!multiplier) {
    return trimmed;
  }

  const bytes = amount * multiplier;
  const gib = bytes / 1024 ** 3;
  if (gib >= 1) {
    return `${gib.toFixed(gib >= 10 ? 1 : 2)} GiB`;
  }

  const mib = bytes / 1024 ** 2;
  if (mib >= 1) {
    return `${mib.toFixed(mib >= 10 ? 0 : 1)} MiB`;
  }

  return `${Math.round(bytes / 1024)} KiB`;
};

const formatNodeUsage = (node: ClusterSummary['nodes']['items'][number]): string => {
  const cpu = formatCpuUsage(node.usage.cpu);
  const memory = formatMemoryUsage(node.usage.memory);
  if (!cpu && !memory) {
    return getNodePressureLabel(node);
  }

  return `CPU ${cpu ?? '-'} · 메모리 ${memory ?? '-'}`;
};

const getClusterFaultCount = (summary: ClusterSummary): number =>
  summary.operators.degraded + summary.operators.unavailable;

const getHealthTone = (summary: ClusterSummary | null): 'ok' | 'warn' | 'danger' | 'neutral' => {
  if (!summary) {
    return 'neutral';
  }

  if (summary.healthScore < 70 || getClusterFaultCount(summary) > 0 || summary.nodes.notReady > 0) {
    return 'danger';
  }

  if (summary.healthScore < 90 || summary.operators.progressing > 0) {
    return 'warn';
  }

  return 'ok';
};

const getOperatorTone = (
  operator: ClusterSummary['operators']['issues'][number],
): 'warn' | 'danger' => {
  if (!operator.available || operator.degraded) {
    return 'danger';
  }

  return 'warn';
};

const renderStatusTag = (
  label: string,
  tone: 'ok' | 'warn' | 'danger' | 'review' | 'neutral' = 'neutral',
  title?: string,
) => (
  <span className={`komsco-ai__scope-tag komsco-ai__scope-tag--${tone}`} title={title}>
    {label}
  </span>
);

const canUseActionExecution = (status: AiopsRuntimeStatus | null): boolean =>
  Boolean(
    status?.spec.capabilities.mutationsEnabled &&
      status.spec.capabilities.actionExecutorConfigured,
  );

const canUseUnrestrictedCommands = (status: AiopsRuntimeStatus | null): boolean =>
  Boolean(status?.spec.capabilities.unrestrictedCommandsEnabled);

const getActionExecutionDisabledReason = (status: AiopsRuntimeStatus | null): string => {
  if (!status) {
    return 'AIOps runtime status has not been loaded yet.';
  }

  const reasons = [];
  if (!status.spec.capabilities.mutationsEnabled) {
    reasons.push('mutation gate disabled');
  }
  if (!status.spec.capabilities.actionExecutorConfigured) {
    reasons.push('Action Executor URL not configured');
  }

  return reasons.join('; ');
};

const getUnrestrictedDisabledReason = (status: AiopsRuntimeStatus | null): string => {
  if (!status) {
    return 'AIOps runtime status has not been loaded yet.';
  }

  return status.spec.capabilities.unrestrictedCommandsEnabled
    ? ''
    : 'unrestricted command gate disabled';
};

const executionModeAllowsActions = (mode: AiopsExecutionMode): boolean =>
  mode === 'execute' || mode === 'unrestricted';

const getExecutionModeLabel = (mode: AiopsExecutionMode): string => {
  if (mode === 'unrestricted') {
    return 'UI 실험 무제한';
  }
  if (mode === 'execute') {
    return 'UI 실행 가능';
  }
  return 'UI 읽기 전용';
};

const getExecutionModeShortLabel = (mode: AiopsExecutionMode): string => {
  if (mode === 'unrestricted') {
    return '무제한';
  }
  if (mode === 'execute') {
    return '실행';
  }
  return '읽기';
};

const getExecutionModeTone = (mode: AiopsExecutionMode): 'ok' | 'review' | 'danger' => {
  if (mode === 'unrestricted') {
    return 'danger';
  }
  if (mode === 'execute') {
    return 'review';
  }
  return 'ok';
};

const getClusterHost = (apiUrl?: string): string => {
  if (!apiUrl) {
    return 'cluster pending';
  }

  try {
    return new URL(apiUrl).host;
  } catch {
    return apiUrl;
  }
};

const renderExecutionModeToggle = (
  executionMode: AiopsExecutionMode,
  actionExecutionAvailable: boolean,
  actionExecutionDisabledReason: string,
  unrestrictedAvailable: boolean,
  unrestrictedDisabledReason: string,
  onExecutionModeChange: (mode: AiopsExecutionMode) => void,
) => (
  <div className="komsco-ai__mode-toggle" role="group" aria-label="AIOps 실행 모드">
    <button
      aria-label="읽기 전용 모드"
      aria-pressed={executionMode === 'read-only'}
      className={`komsco-ai__mode-toggle-button${
        executionMode === 'read-only' ? ' komsco-ai__mode-toggle-button--active' : ''
      }`}
      onClick={() => onExecutionModeChange('read-only')}
      title="읽기 전용 모드"
      type="button"
    >
      <ShieldAltIcon />
      <span>읽기 전용</span>
    </button>
    <button
      aria-label="승인 후 실행 모드"
      aria-pressed={executionMode === 'execute'}
      className={`komsco-ai__mode-toggle-button${
        executionMode === 'execute' ? ' komsco-ai__mode-toggle-button--active-execute' : ''
      }`}
      data-disabled-reason={!actionExecutionAvailable ? actionExecutionDisabledReason : undefined}
      disabled={!actionExecutionAvailable}
      onClick={() => onExecutionModeChange('execute')}
      title={
        actionExecutionAvailable
          ? '승인 후 실행 모드'
          : `승인 후 실행 비활성: ${actionExecutionDisabledReason}`
      }
      type="button"
    >
      <TerminalIcon />
      <span>실행</span>
    </button>
    <button
      aria-label="실험 무제한 모드"
      aria-pressed={executionMode === 'unrestricted'}
      className={`komsco-ai__mode-toggle-button${
        executionMode === 'unrestricted' ? ' komsco-ai__mode-toggle-button--active-danger' : ''
      }`}
      data-disabled-reason={!unrestrictedAvailable ? unrestrictedDisabledReason : undefined}
      disabled={!unrestrictedAvailable}
      onClick={() => onExecutionModeChange('unrestricted')}
      title={
        unrestrictedAvailable
          ? '실험 무제한 모드'
          : `실험 무제한 비활성: ${unrestrictedDisabledReason}`
      }
      type="button"
    >
      <ExclamationCircleIcon />
      <span>무제한</span>
    </button>
  </div>
);

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

type AiopsRecordView = AiopsRecord;
type AiopsActionStep = 'create-plan' | 'approve-plan' | 'execute-approval';

type AiopsRecordAction = {
  disabledReason?: string;
  label: string;
  step: AiopsActionStep;
};

const getRecordSpecMap = (record: AiopsRecordView): Record<string, unknown> =>
  record.spec && typeof record.spec === 'object' ? record.spec : {};

const asObjectMap = (value: unknown): Record<string, unknown> | undefined =>
  value && typeof value === 'object' ? (value as Record<string, unknown>) : undefined;

const getRecordName = (record: AiopsRecordView): string => record.metadata?.name ?? '';

const getSealedActionPlan = (record: AiopsRecordView): Record<string, unknown> | undefined =>
  asObjectMap(getRecordSpecMap(record).sealedActionPlan);

const getPlanDigest = (record: AiopsRecordView): string => {
  const plan = getSealedActionPlan(record);
  const digest = asObjectMap(plan?.digest);

  return typeof digest?.planDigest === 'string' ? digest.planDigest : '';
};

const getApprovalDecision = (record: AiopsRecordView): Record<string, unknown> | undefined =>
  asObjectMap(getRecordSpecMap(record).approvalDecision);

const getApprovalId = (record: AiopsRecordView): string => {
  const decision = getApprovalDecision(record);

  return typeof decision?.approvalId === 'string' ? decision.approvalId : getRecordName(record);
};

const getApprovalPlanDigest = (record: AiopsRecordView): string => {
  const decision = getApprovalDecision(record);

  return typeof decision?.planDigest === 'string' ? decision.planDigest : '';
};

const findPlanByDigest = (
  plans: AiopsRecordView[],
  planDigest: string,
): AiopsRecordView | undefined => plans.find((plan) => getPlanDigest(plan) === planDigest);

const hasApprovalForPlan = (approvals: AiopsRecordView[], planDigest: string): boolean =>
  approvals.some((record) => {
    const decision = getApprovalDecision(record);
    const status = String(decision?.status ?? '');

    return decision?.planDigest === planDigest && ['approved', 'executed'].includes(status);
  });

const hasExecutionForApproval = (executions: AiopsRecordView[], approvalId: string): boolean =>
  executions.some((record) => getRecordSpecMap(record).approvalId === approvalId);

const getRecordPhase = (record: AiopsRecordView): string => {
  const spec = getRecordSpecMap(record);
  const status = spec.status;
  if (status && typeof status === 'object' && 'phase' in status) {
    return String((status as Record<string, unknown>).phase ?? 'unknown');
  }
  const decision = spec.approvalDecision;
  if (decision && typeof decision === 'object' && 'status' in decision) {
    return String((decision as Record<string, unknown>).status ?? 'unknown');
  }
  const mutationOutcome = spec.mutationOutcome;
  if (mutationOutcome && typeof mutationOutcome === 'object' && 'status' in mutationOutcome) {
    return String((mutationOutcome as Record<string, unknown>).status ?? 'unknown');
  }
  return 'recorded';
};

const getRecordTargetLabel = (record: AiopsRecordView): string => {
  const spec = getRecordSpecMap(record);
  const directTarget = spec.target;
  const candidate = spec.candidate;
  const sealedActionPlan = spec.sealedActionPlan;
  const target =
    directTarget && typeof directTarget === 'object'
      ? directTarget
      : candidate && typeof candidate === 'object'
        ? (candidate as Record<string, unknown>).targetNode
        : sealedActionPlan && typeof sealedActionPlan === 'object'
          ? (sealedActionPlan as Record<string, unknown>).target
          : undefined;

  if (!target || typeof target !== 'object') {
    return record.metadata?.name ?? 'unknown';
  }

  const map = target as Record<string, unknown>;
  const namespace = map.namespace ? `${String(map.namespace)}/` : '';
  return `${namespace}${String(map.name ?? record.metadata?.name ?? 'unknown')}`;
};

const getPhaseTone = (phase: string): 'ok' | 'warn' | 'danger' | 'review' | 'neutral' => {
  if (/verified|succeeded|completed|executed|approved|submitted/.test(phase)) {
    return 'ok';
  }
  if (/failed|denied|expired|disabled|mismatch|stale/.test(phase)) {
    return 'danger';
  }
  if (/waiting|pending|proposed|sealed|review/.test(phase)) {
    return 'review';
  }
  return 'neutral';
};

const getAiopsRecordAction = (
  record: AiopsRecordView,
  aiopsStatus: AiopsRuntimeStatus | null,
  executionMode: AiopsExecutionMode,
): AiopsRecordAction | null => {
  const spec = getRecordSpecMap(record);
  const kind = record.kind ?? '';
  const records = aiopsStatus?.spec.records;
  const modeDisabledReason = !canUseActionExecution(aiopsStatus)
    ? 'Gateway 실행 기능 미구성'
    : !executionModeAllowsActions(executionMode)
      ? '실행 가능 또는 실험 무제한 모드 선택 필요'
      : '';
  const withModeGate = (action: AiopsRecordAction): AiopsRecordAction =>
    modeDisabledReason
      ? { ...action, disabledReason: action.disabledReason ?? modeDisabledReason }
      : action;

  if (kind === 'ActionProposalRecord' || spec.candidateActionRequest) {
    return withModeGate({ label: '계획', step: 'create-plan' });
  }

  if (kind === 'SealedActionPlanRecord' || spec.sealedActionPlan) {
    const planDigest = getPlanDigest(record);
    if (!planDigest) {
      return withModeGate({
        disabledReason: 'plan digest 없음',
        label: '승인',
        step: 'approve-plan',
      });
    }
    if (hasApprovalForPlan(records?.approvalDecisions ?? [], planDigest)) {
      return null;
    }

    return withModeGate({ label: '승인', step: 'approve-plan' });
  }

  if (kind === 'ApprovalDecisionRecord' || spec.approvalDecision) {
    const decision = getApprovalDecision(record);
    const status = String(decision?.status ?? '');
    const approvalId = getApprovalId(record);
    const plan = findPlanByDigest(records?.sealedActionPlans ?? [], getApprovalPlanDigest(record));

    if (status !== 'approved') {
      return null;
    }
    if (hasExecutionForApproval(records?.executionRecords ?? [], approvalId)) {
      return null;
    }
    if (!plan) {
      return withModeGate({
        disabledReason: '연결된 plan 없음',
        label: '실행',
        step: 'execute-approval',
      });
    }

    return withModeGate({ label: '실행', step: 'execute-approval' });
  }

  return null;
};

const renderRecordRows = (records: AiopsRecordView[], emptyLabel: string) => {
  if (records.length === 0) {
    return <div className="komsco-ai__rail-empty">{emptyLabel}</div>;
  }

  return records.slice(0, 4).map((record) => {
    const phase = getRecordPhase(record);
    return (
      <div className="komsco-ai__rail-command" key={record.metadata?.name ?? phase}>
        <code>{record.metadata?.name ?? record.kind ?? 'record'}</code>
        <p>{getRecordTargetLabel(record)}</p>
        {renderStatusTag(phase, getPhaseTone(phase))}
      </div>
    );
  });
};

const renderActionRecordRows = (
  records: AiopsRecordView[],
  emptyLabel: string,
  aiopsStatus: AiopsRuntimeStatus | null,
  executionMode: AiopsExecutionMode,
  busyActionId: string,
  onAction: (record: AiopsRecordView, action: AiopsRecordAction) => void,
) => {
  if (records.length === 0) {
    return <div className="komsco-ai__rail-empty">{emptyLabel}</div>;
  }

  return records.slice(0, 6).map((record) => {
    const phase = getRecordPhase(record);
    const action = getAiopsRecordAction(record, aiopsStatus, executionMode);
    const actionId = `${action?.step ?? 'none'}:${getRecordName(record)}`;
    const busy = actionId === busyActionId;

    return (
      <div className="komsco-ai__rail-command" key={record.metadata?.name ?? phase}>
        <div className="komsco-ai__rail-command-head">
          <code>{record.metadata?.name ?? record.kind ?? 'record'}</code>
          {renderStatusTag(phase, getPhaseTone(phase))}
        </div>
        <p>{getRecordTargetLabel(record)}</p>
        {action && (
          <div className="komsco-ai__rail-action-row">
            <Button
              className="komsco-ai__rail-action-button"
              isDisabled={busy || Boolean(action.disabledReason)}
              isLoading={busy}
              onClick={() => onAction(record, action)}
              size="sm"
              title={action.disabledReason}
              variant="secondary"
            >
              <span className="komsco-ai__rail-action-icon">
                <TerminalIcon />
              </span>
              {action.label}
            </Button>
            {action.disabledReason && (
              <span className="komsco-ai__rail-action-note">{action.disabledReason}</span>
            )}
          </div>
        )}
      </div>
    );
  });
};

const renderInsightRail = (
  summary: ClusterSummary | null,
  loading: boolean,
  error: string,
  aiopsStatus: AiopsRuntimeStatus | null,
  aiopsStatusError: string,
  executionMode: AiopsExecutionMode,
  aiopsActionBusyId: string,
  aiopsActionError: string,
  aiopsActionNotice: string,
  onAiopsAction: (record: AiopsRecordView, action: AiopsRecordAction) => void,
) => (
  <aside className="komsco-ai__insight-rail" aria-label="현재 분석 컨텍스트">
    <h2 className="komsco-ai__rail-title">현재 클러스터 컨텍스트</h2>
    <div className={`komsco-ai__health-card komsco-ai__health-card--${getHealthTone(summary)}`}>
      <div className="komsco-ai__health-head">
        <span>Cluster health score</span>
        <span>마지막 갱신 {formatSummaryTime(summary?.updatedAt)}</span>
      </div>
      <div className="komsco-ai__health-score">
        {summary ? summary.healthScore : loading ? '...' : '--'} <small>/ 100</small>
      </div>
      <div className={`komsco-ai__health-bar${summary ? '' : ' komsco-ai__health-bar--pending'}`}>
        {summary ? (
          <span
            className={`komsco-ai__health-bar-fill komsco-ai__health-bar-fill--${getHealthTone(
              summary,
            )}`}
            style={{ width: `${summary.healthScore}%` }}
          />
        ) : (
          <span className="komsco-ai__health-bar-placeholder">status pending</span>
        )}
      </div>
    </div>

    {error && (
      <div className="komsco-ai__rail-error">
        클러스터 요약을 가져오지 못했습니다. 대화 기능은 계속 사용할 수 있습니다.
      </div>
    )}

    <div className="komsco-ai__rail-section">
      <div className="komsco-ai__rail-section-head">
        <strong>노드 상태</strong>
        <span>
          {summary
            ? `${summary.nodes.ready}/${summary.nodes.total} Ready`
            : loading
              ? '수집 중'
              : '대기'}
        </span>
      </div>
      {(summary?.nodes.items ?? []).slice(0, 5).map((node) => (
        <div className="komsco-ai__alert-mini" key={node.name}>
          <span
            className={`komsco-ai__alert-mini-dot${
              node.ready && !Object.values(node.pressures).some(Boolean)
                ? ' komsco-ai__alert-mini-dot--green'
                : ''
            }`}
          />
          <div>
            <div className="komsco-ai__alert-mini-title">{node.name}</div>
            <div className="komsco-ai__alert-mini-sub">
              {node.roles.join(', ')} · {node.kubeletVersion ?? 'version unknown'}
            </div>
            <div className="komsco-ai__alert-mini-sub">{formatNodeUsage(node)}</div>
          </div>
          <span
            className={`komsco-ai__rail-badge${node.ready ? ' komsco-ai__rail-badge--ok' : ''}`}
          >
            {node.ready ? 'READY' : 'CHECK'}
          </span>
        </div>
      ))}
      {summary && summary.nodes.items.length === 0 && (
        <div className="komsco-ai__rail-empty">조회 가능한 노드가 없습니다.</div>
      )}
    </div>

    <div className="komsco-ai__rail-section">
      <div className="komsco-ai__rail-section-head">
        <strong>클러스터 상태</strong>
        <span>{summary?.version.version ?? 'version pending'}</span>
      </div>
      <div className="komsco-ai__scope-list">
        {summary
          ? renderStatusTag(
              `Available ${summary.operators.available}/${summary.operators.total}`,
              summary.operators.available === summary.operators.total ? 'ok' : 'warn',
            )
          : renderStatusTag('Available 대기')}
        {summary
          ? renderStatusTag(
              `장애 ${getClusterFaultCount(summary)}건`,
              getClusterFaultCount(summary) > 0 ? 'danger' : 'ok',
              'Degraded + Unavailable Operator 수',
            )
          : renderStatusTag('장애 대기')}
        {summary
          ? renderStatusTag(
              `Progressing ${summary.operators.progressing}건`,
              summary.operators.progressing > 0 ? 'warn' : 'neutral',
            )
          : renderStatusTag('Progressing 대기')}
        {summary
          ? renderStatusTag(summary.version.channel ?? 'Channel unknown', 'neutral')
          : renderStatusTag('Channel 대기')}
        {summary
          ? renderStatusTag(
              summary.version.updateAvailable ? 'Update available' : 'No update signal',
              summary.version.updateAvailable ? 'review' : 'neutral',
            )
          : renderStatusTag('Update signal 대기')}
        {summary
          ? renderStatusTag(
              summary.version.upgradeable === false ? 'Upgrade blocked' : 'Upgradeable',
              summary.version.upgradeable === false ? 'warn' : 'ok',
              summary.version.upgradeableMessage,
            )
          : renderStatusTag('Upgradeable 대기')}
        {summary
          ? renderStatusTag(
              `Metrics ${summary.nodes.metricsAvailable ? 'available' : 'unavailable'}`,
              summary.nodes.metricsAvailable ? 'ok' : 'warn',
            )
          : renderStatusTag('Metrics 대기')}
      </div>
    </div>

    <div className="komsco-ai__rail-section">
      <div className="komsco-ai__rail-section-head">
        <strong>Operator 이슈</strong>
        <span>{summary ? `${summary.operators.issues.length}건` : '대기'}</span>
      </div>
      {(summary?.operators.issues ?? []).slice(0, 5).map((operator) => (
        <div
          className={`komsco-ai__rail-command komsco-ai__rail-command--${getOperatorTone(
            operator,
          )}`}
          key={operator.name}
        >
          <code>{operator.name}</code>
          <p>{operator.reason || operator.message || '상태 확인 필요'}</p>
        </div>
      ))}
      {summary && summary.operators.issues.length === 0 && (
        <div className="komsco-ai__rail-empty">주요 Operator 이슈가 없습니다.</div>
      )}
    </div>

    <div className="komsco-ai__rail-section">
      <div className="komsco-ai__rail-section-head">
        <strong>AIOps 실행 상태</strong>
        <span>{aiopsStatus ? '연결됨' : aiopsStatusError ? '확인 필요' : '수집 중'}</span>
      </div>
      <div className="komsco-ai__scope-list">
        {renderStatusTag(
          aiopsStatus
            ? aiopsStatus.spec.capabilities.diagnosticsEnabled
              ? 'Diagnostics on'
              : 'Diagnostics off'
            : 'Diagnostics pending',
          aiopsStatus
            ? aiopsStatus.spec.capabilities.diagnosticsEnabled
              ? 'ok'
              : 'warn'
            : 'neutral',
        )}
        {renderStatusTag(
          aiopsStatus
            ? aiopsStatus.spec.capabilities.mutationsEnabled
              ? 'Mutations on'
              : 'Mutations off'
            : 'Mutations pending',
          aiopsStatus
            ? aiopsStatus.spec.capabilities.mutationsEnabled
              ? 'review'
              : 'neutral'
            : 'neutral',
        )}
        {renderStatusTag(
          getExecutionModeLabel(executionMode),
          getExecutionModeTone(executionMode),
        )}
        {renderStatusTag(
          aiopsStatus
            ? aiopsStatus.spec.capabilities.unrestrictedCommandsEnabled
            ? 'Unrestricted on'
              : 'Unrestricted off'
            : 'Unrestricted pending',
          aiopsStatus
            ? aiopsStatus.spec.capabilities.unrestrictedCommandsEnabled
              ? 'danger'
              : 'neutral'
            : 'neutral',
        )}
        {renderStatusTag(
          aiopsStatus
            ? aiopsStatus.spec.capabilities.recordStoreEnabled
              ? 'Ledger on'
              : 'Ledger off'
            : 'Ledger pending',
          aiopsStatus
            ? aiopsStatus.spec.capabilities.recordStoreEnabled
              ? 'ok'
              : 'warn'
            : 'neutral',
        )}
        {renderStatusTag(
          aiopsStatus
            ? aiopsStatus.spec.capabilities.rag?.status === 'not_configured'
              ? 'RAG not configured'
              : aiopsStatus.spec.capabilities.rag?.status === 'configured_skeleton'
                ? 'RAG skeleton'
                : `RAG ${aiopsStatus.spec.capabilities.rag?.status ?? 'unknown'}`
            : 'RAG pending',
          aiopsStatus
            ? aiopsStatus.spec.capabilities.rag?.status === 'not_configured'
              ? 'warn'
              : 'neutral'
            : 'neutral',
        )}
      </div>
      {aiopsStatusError && (
        <div className="komsco-ai__rail-error">AIOps 상태를 가져오지 못했습니다.</div>
      )}
    </div>

    <div className="komsco-ai__rail-section">
      <div className="komsco-ai__rail-section-head">
        <strong>RCA Context</strong>
        <span>{aiopsStatus?.spec.safetyContract?.rcaContextStatus?.status ?? '대기'}</span>
      </div>
      <div className="komsco-ai__scope-list">
        {renderStatusTag(
          `Collected ${
            aiopsStatus?.spec.safetyContract?.evidenceStatus
              ?.filter((item) => item.status === 'collected')
              .reduce((total, item) => total + item.count, 0) ?? 0
          }`,
          'ok',
        )}
        {renderStatusTag(
          `Missing ${
            aiopsStatus?.spec.safetyContract?.evidenceStatus
              ?.filter((item) => item.status === 'missing')
              .length ?? 0
          }`,
          'warn',
        )}
      </div>
      <div className="komsco-ai__rail-command">
        <code>
          {aiopsStatus?.spec.safetyContract?.rcaContextStatus?.digest ??
            'waiting_for_first_question'}
        </code>
        <p>
          {aiopsStatus?.spec.safetyContract?.rcaContextStatus?.latestContext
            ? 'RCA Context JSON is linked to the latest chat run.'
            : '질문 실행 후 evidence/missing evidence context가 연결됩니다.'}
        </p>
      </div>
    </div>

    <div className="komsco-ai__rail-section">
      <div className="komsco-ai__rail-section-head">
        <strong>최근 진단</strong>
        <span>{aiopsStatus ? `${aiopsStatus.spec.records.diagnosticRequests.length}건` : '대기'}</span>
      </div>
      {renderRecordRows(aiopsStatus?.spec.records.diagnosticRequests ?? [], '최근 진단 요청이 없습니다.')}
    </div>

    <div className="komsco-ai__rail-section">
      <div className="komsco-ai__rail-section-head">
        <strong>승인·실행</strong>
        <span>
          {aiopsStatus
            ? `${
                aiopsStatus.spec.records.actionProposals.length +
                aiopsStatus.spec.records.sealedActionPlans.length +
                aiopsStatus.spec.records.approvalDecisions.length +
                aiopsStatus.spec.records.executionRecords.length
              }건`
            : '대기'}
        </span>
      </div>
      {aiopsActionError && <div className="komsco-ai__rail-error">{aiopsActionError}</div>}
      {aiopsActionNotice && <div className="komsco-ai__rail-success">{aiopsActionNotice}</div>}
      {renderActionRecordRows(
        [
          ...(aiopsStatus?.spec.records.actionProposals ?? []),
          ...(aiopsStatus?.spec.records.sealedActionPlans ?? []),
          ...(aiopsStatus?.spec.records.approvalDecisions ?? []),
          ...(aiopsStatus?.spec.records.executionRecords ?? []),
        ],
        '최근 승인 또는 실행 기록이 없습니다.',
        aiopsStatus,
        executionMode,
        aiopsActionBusyId,
        onAiopsAction,
      )}
    </div>
  </aside>
);

type AssistantLauncherProps = {
  defaultOpen?: boolean;
  embedded?: boolean;
  lockOpen?: boolean;
  overlayId?: string;
  closeOverlay?: () => void;
};

const FullscreenPortal: React.FC<{ active: boolean; children: React.ReactNode }> = ({
  active,
  children,
}) => {
  if (active && typeof document !== 'undefined') {
    return createPortal(children, document.body);
  }

  return <>{children}</>;
};

const AssistantLauncher: React.FC<AssistantLauncherProps> = ({
  defaultOpen = false,
  embedded = false,
  lockOpen = false,
}) => {
  const [open, setOpen] = React.useState(defaultOpen || embedded || lockOpen);
  const [fullScreen, setFullScreen] = React.useState(false);
  const [input, setInput] = React.useState('');
  const [pendingAttachments, setPendingAttachments] = React.useState<ImageAttachment[]>([]);
  const [attachmentError, setAttachmentError] = React.useState('');
  const [clusterSummary, setClusterSummary] = React.useState<ClusterSummary | null>(null);
  const [clusterSummaryError, setClusterSummaryError] = React.useState('');
  const [clusterSummaryLoading, setClusterSummaryLoading] = React.useState(false);
  const [authSubject, setAuthSubject] = React.useState<AuthSubject | null>(null);
  const [authSubjectError, setAuthSubjectError] = React.useState('');
  const [aiopsStatus, setAiopsStatus] = React.useState<AiopsRuntimeStatus | null>(null);
  const [aiopsStatusError, setAiopsStatusError] = React.useState('');
  const [aiopsActionBusyId, setAiopsActionBusyId] = React.useState('');
  const [aiopsActionError, setAiopsActionError] = React.useState('');
  const [aiopsActionNotice, setAiopsActionNotice] = React.useState('');
  const [executionMode, setExecutionMode] = React.useState<AiopsExecutionMode>(
    DEFAULT_AIOPS_EXECUTION_MODE,
  );
  const [dragActive, setDragActive] = React.useState(false);
  const [messages, setMessages] = React.useState<Message[]>([]);
  const [conversationId, setConversationId] = React.useState<string | undefined>();
  const [activeSessionId, setActiveSessionId] = React.useState(() => createRunId());
  const [conversationHistory, setConversationHistory] = React.useState<ConversationHistoryItem[]>([]);
  const [historySidebarOpen, setHistorySidebarOpen] = React.useState(false);
  const [quickPromptMenuOpen, setQuickPromptMenuOpen] = React.useState(false);
  const [taskModeMenuOpen, setTaskModeMenuOpen] = React.useState(false);
  const [assistantTaskMode, setAssistantTaskMode] = React.useState<AssistantTaskMode>('ask');
  const [panelResizeUnlocked, setPanelResizeUnlocked] = React.useState(false);
  const [panelSize, setPanelSize] = React.useState<{ height?: number; width?: number }>({});
  const [historyDrawerBounds, setHistoryDrawerBounds] = React.useState<{
    height?: number;
    left?: number;
    top?: number;
  }>({});
  const [stickToBottom, setStickToBottom] = React.useState(true);
  const [showScrollToBottom, setShowScrollToBottom] = React.useState(false);
  const [uiLanguage, setUiLanguage] = React.useState<UiLanguage>('ko');
  const [loading, setLoading] = React.useState(false);
  const [copiedMessageIndex, setCopiedMessageIndex] = React.useState<number | null>(null);
  const [previewAttachment, setPreviewAttachment] = React.useState<ImageAttachment | null>(null);
  const [, setProgressTick] = React.useState(0);
  const surfaceRef = React.useRef<HTMLDivElement | null>(null);
  const bodyRef = React.useRef<HTMLDivElement | null>(null);
  const bodyEndRef = React.useRef<HTMLDivElement | null>(null);
  const fileInputRef = React.useRef<HTMLInputElement | null>(null);
  const quickPromptMenuRef = React.useRef<HTMLDivElement | null>(null);
  const taskModeMenuRef = React.useRef<HTMLDivElement | null>(null);
  const assistantTextQueueRef = React.useRef('');
  const assistantTypewriterTimerRef = React.useRef<number | undefined>();
  const chatAbortControllerRef = React.useRef<AbortController | null>(null);
  const stopRequestedRef = React.useRef(false);
  const actionExecutionAvailable = canUseActionExecution(aiopsStatus);
  const unrestrictedAvailable = canUseUnrestrictedCommands(aiopsStatus);
  const actionExecutionDisabledReason = getActionExecutionDisabledReason(aiopsStatus);
  const unrestrictedDisabledReason = getUnrestrictedDisabledReason(aiopsStatus);
  const assistantConnection = getAssistantConnectionState(
    clusterSummary,
    clusterSummaryLoading,
    clusterSummaryError,
    aiopsStatus,
    aiopsStatusError,
  );
  const lightspeedStatus = aiopsStatus?.spec.safetyContract?.lightspeedStatus;
  const headerConnectionLabel = [
    assistantConnection.label,
    `Lightspeed stream: ${lightspeedStatus?.streamProbe ?? 'status pending'}${
      lightspeedStatus?.fallbackActive ? ' (Gateway fallback active)' : ''
    }`,
    `Safety mode: ${aiopsStatus?.spec.safetyContract?.mode ?? 'status pending'}`,
  ].join(' · ');
  const copy = UI_COPY[uiLanguage];
  const selectedTaskMode =
    ASSISTANT_TASK_MODES.find((item) => item.value === assistantTaskMode) ||
    ASSISTANT_TASK_MODES[0];
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
      prev.height === next.height && prev.left === next.left && prev.top === next.top
        ? prev
        : next,
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
      const minHeight = 420;
      const maxHeight = Math.max(minHeight, window.innerHeight - 32);
      const minWidth = Math.min(460, Math.max(320, window.innerWidth - 32));
      const maxWidth = Math.max(
        minWidth,
        embedded
          ? Math.min(parentRect?.width || window.innerWidth - 32, window.innerWidth - 32)
          : window.innerWidth - 32,
      );
      const clamp = (value: number, min: number, max: number) =>
        Math.min(Math.max(value, min), max);

      const handleMouseMove = (moveEvent: MouseEvent) => {
        const deltaX = moveEvent.clientX - startX;
        const deltaY = moveEvent.clientY - startY;
        const nextHeight = direction.includes('n')
          ? clamp(initialRect.height - deltaY, minHeight, maxHeight)
          : direction.includes('s')
            ? clamp(initialRect.height + deltaY, minHeight, maxHeight)
            : initialRect.height;
        const nextWidth = direction.includes('w')
          ? clamp(initialRect.width - deltaX, minWidth, maxWidth)
          : direction.includes('e')
            ? clamp(initialRect.width + deltaX, minWidth, maxWidth)
            : initialRect.width;

        setPanelSize({
          height: Math.round(nextHeight),
          width: Math.round(nextWidth),
        });
      };

      const stopPanelResize = () => {
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', stopPanelResize);
      };

      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', stopPanelResize);
    },
    [embedded, fullScreen, panelResizeUnlocked],
  );

  React.useEffect(() => {
    if (!aiopsStatus) {
      return;
    }
    if (!actionExecutionAvailable && executionMode === 'execute') {
      setExecutionMode('read-only');
    }
    if (!unrestrictedAvailable && executionMode === 'unrestricted') {
      setExecutionMode('read-only');
    }
  }, [actionExecutionAvailable, aiopsStatus, executionMode, unrestrictedAvailable]);

  React.useLayoutEffect(() => {
    if (!historySidebarOpen || fullScreen) {
      setHistoryDrawerBounds({});
      return undefined;
    }

    updateHistoryDrawerBounds();
    window.addEventListener('resize', updateHistoryDrawerBounds);
    window.addEventListener('scroll', updateHistoryDrawerBounds, true);

    const observer =
      typeof ResizeObserver === 'undefined' ? undefined : new ResizeObserver(updateHistoryDrawerBounds);
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
    if (!quickPromptMenuOpen && !taskModeMenuOpen) {
      return undefined;
    }

    const handleDocumentMouseDown = (event: MouseEvent) => {
      const target = event.target as Node | null;
      if (
        target &&
        (quickPromptMenuRef.current?.contains(target) ||
          taskModeMenuRef.current?.contains(target))
      ) {
        return;
      }

      setQuickPromptMenuOpen(false);
      setTaskModeMenuOpen(false);
    };

    const handleDocumentKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') {
        return;
      }

      setQuickPromptMenuOpen(false);
      setTaskModeMenuOpen(false);
    };

    document.addEventListener('mousedown', handleDocumentMouseDown);
    document.addEventListener('keydown', handleDocumentKeyDown);

    return () => {
      document.removeEventListener('mousedown', handleDocumentMouseDown);
      document.removeEventListener('keydown', handleDocumentKeyDown);
    };
  }, [quickPromptMenuOpen, taskModeMenuOpen]);

  const handleExecutionModeChange = React.useCallback(
    (mode: AiopsExecutionMode) => {
      if (mode === 'execute' && !actionExecutionAvailable) {
        return;
      }
      if (mode === 'unrestricted' && !unrestrictedAvailable) {
        return;
      }

      setAiopsActionError('');
      setExecutionMode(mode);
    },
    [actionExecutionAvailable, unrestrictedAvailable],
  );

  const saveCurrentConversation = React.useCallback(
    (snapshotMessages = messages, snapshotConversationId = conversationId) => {
      if (snapshotMessages.length === 0) {
        return;
      }

      const item: ConversationHistoryItem = {
        id: activeSessionId,
        title: getConversationTitle(snapshotMessages, uiLanguage),
        updatedAt: Date.now(),
        conversationId: snapshotConversationId,
        messages: snapshotMessages,
      };

      setConversationHistory((prev) => [
        item,
        ...prev.filter((conversation) => conversation.id !== activeSessionId),
      ].slice(0, 12));
    },
    [activeSessionId, conversationId, messages, uiLanguage],
  );

  React.useEffect(() => {
    if (!loading) {
      saveCurrentConversation();
    }
  }, [loading, saveCurrentConversation]);

  const startNewConversation = React.useCallback(() => {
    if (loading) {
      return;
    }

    saveCurrentConversation();
    setActiveSessionId(createRunId());
    setConversationId(undefined);
    setMessages([]);
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

      saveCurrentConversation();
      setActiveSessionId(conversation.id);
      setConversationId(conversation.conversationId);
      setMessages(conversation.messages);
      setInput('');
      setPendingAttachments([]);
      setAttachmentError('');
      setQuickPromptMenuOpen(false);
      setTaskModeMenuOpen(false);
    },
    [loading, saveCurrentConversation],
  );

  const scrollToBottom = React.useCallback((behavior: ScrollBehavior = 'smooth') => {
    const body = bodyRef.current;
    if (body) {
      body.scrollTo({ top: body.scrollHeight, behavior });
    }
    bodyEndRef.current?.scrollIntoView({ block: 'end', behavior });
  }, []);

  const handleConversationScroll = React.useCallback(
    (event: React.UIEvent<HTMLDivElement>) => {
      const target = event.currentTarget;
      const distanceToBottom = target.scrollHeight - target.scrollTop - target.clientHeight;
      const nearBottom = distanceToBottom <= SCROLL_BOTTOM_THRESHOLD_PX;

      setStickToBottom(nearBottom);
      setShowScrollToBottom(!nearBottom);
    },
    [],
  );

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
      const [summaryResult, statusResult, consoleUserResult] = await Promise.allSettled([
        fetchClusterSummary(),
        fetchAiopsStatus(),
        fetchConsoleUserSubject(),
      ]);
      if (disposed) {
        return;
      }

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

  const refreshAiopsRuntimeStatus = React.useCallback(async () => {
    try {
      const status = await fetchAiopsStatus();

      setAiopsStatus(status);
      setAiopsStatusError('');
    } catch (error) {
      setAiopsStatusError(
        error instanceof Error ? error.message : 'AIOps status request failed.',
      );
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
        return;
      }
      if (!executionModeAllowsActions(executionMode)) {
        setAiopsActionError('실행 가능 또는 실험 무제한 모드를 선택해야 승인·실행할 수 있습니다.');
        return;
      }

      const actionId = `${action.step}:${getRecordName(record)}`;

      setAiopsActionBusyId(actionId);
      setAiopsActionError('');
      setAiopsActionNotice('');

      try {
        if (action.step === 'create-plan') {
          const proposalId = getRecordName(record);
          if (!proposalId) {
            throw new Error('Action proposal id is missing.');
          }
          await createActionPlan(proposalId);
          setAiopsActionNotice('Action plan을 생성했습니다.');
        }

        if (action.step === 'approve-plan') {
          const planId = getRecordName(record);
          const planDigest = getPlanDigest(record);
          if (!planId || !planDigest) {
            throw new Error('Action plan id 또는 digest가 없습니다.');
          }
          await approveActionPlan(planId, planDigest);
          setAiopsActionNotice('Action plan을 승인했습니다.');
        }

        if (action.step === 'execute-approval') {
          const approvalId = getApprovalId(record);
          const planDigest = getApprovalPlanDigest(record);
          const plan = findPlanByDigest(aiopsStatus?.spec.records.sealedActionPlans ?? [], planDigest);
          const planId = plan ? getRecordName(plan) : '';
          if (!approvalId || !planId || !planDigest) {
            throw new Error('Approval 또는 연결된 action plan 정보가 없습니다.');
          }
          await executeApprovedAction(approvalId, planId, planDigest);
          setAiopsActionNotice('승인된 조치를 실행했습니다.');
        }

        await refreshAiopsRuntimeStatus();
      } catch (error) {
        setAiopsActionError(error instanceof Error ? error.message : 'AIOps action failed.');
      } finally {
        setAiopsActionBusyId('');
      }
    },
    [aiopsStatus, executionMode, refreshAiopsRuntimeStatus],
  );

  const appendAssistantText = React.useCallback((content: string) => {
    setMessages((prev) => {
      const assistantIndex = findLastAssistantIndex(prev);
      if (assistantIndex < 0) {
        return [...prev, { role: 'assistant', content }];
      }

      const next = [...prev];
      next[assistantIndex] = {
        ...next[assistantIndex],
        content: next[assistantIndex].content + content,
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
  }, [appendAssistantText, clearAssistantTypewriterTimer]);

  const enqueueAssistantText = React.useCallback(
    (content: string) => {
      assistantTextQueueRef.current += content;
      flushAssistantTextQueueNow();
    },
    [flushAssistantTextQueueNow],
  );

  const waitForAssistantTextQueue = React.useCallback(async () => {
    flushAssistantTextQueueNow();
  }, [flushAssistantTextQueueNow]);

  React.useEffect(
    () => () => {
      clearAssistantTypewriterTimer();
    },
    [clearAssistantTypewriterTimer],
  );

  const copyMessage = React.useCallback((message: Message, index: number) => {
    const redactedContent = redactSensitiveText(message.content.trim());
    const text = `${redactedContent}${buildEvidenceCopyText(message.evidenceFooter)}`.trim();
    if (!text || !navigator.clipboard) {
      return;
    }

    void navigator.clipboard.writeText(text).then(() => {
      setCopiedMessageIndex(index);
      window.setTimeout(() => {
        setCopiedMessageIndex((current) => (current === index ? null : current));
      }, 1400);
    });
  }, []);

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

  const addImageFiles = React.useCallback(
    async (files: File[]) => {
      const imageFiles = files.filter((file) => ACCEPTED_IMAGE_MIME_TYPES.has(file.type));

      if (imageFiles.length === 0) {
        setAttachmentError('지원되는 이미지 형식은 PNG, JPEG, WebP, GIF입니다.');
        return;
      }

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

      try {
        const attachments = await Promise.all(imageFiles.map(readImageAttachment));
        setPendingAttachments((prev) => [...prev, ...attachments]);
        setAttachmentError('');
      } catch (error) {
        setAttachmentError(
          error instanceof Error ? error.message : '이미지 파일을 읽지 못했습니다.',
        );
      }
    },
    [pendingAttachments],
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

      if ((!question && attachments.length === 0) || loading) {
        return;
      }

      setStickToBottom(true);
      setShowScrollToBottom(false);
      setInput('');
      setPendingAttachments([]);
      setAttachmentError('');
      setQuickPromptMenuOpen(false);
      setTaskModeMenuOpen(false);
      setLoading(true);
      flushAssistantTextQueueNow();
      window.setTimeout(() => scrollToBottom('auto'), 0);
      const recentMessages = buildRecentContextMessages(messages);
      setMessages((prev) => [
        ...prev,
        { role: 'user', attachments, content: question },
        { role: 'assistant', content: '', progressSteps: [] },
      ]);

      const abortController = new AbortController();
      chatAbortControllerRef.current = abortController;
      stopRequestedRef.current = false;

      try {
        const runId = createRunId();
        const pageContext = {
          ...buildConsolePageContext(),
          aiopsExecutionMode: executionMode,
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
        let fallbackAnswerSeen = false;
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
            detail: 'OpenShift Lightspeed가 실제 응답 스트림을 시작하기를 기다리는 중입니다.',
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
            detail: '응답 본문 스트림을 수신하고 화면에 렌더링합니다.',
            id: ANSWER_STREAM_STEP_ID,
            name: ANSWER_STREAM_STEP_ID,
            startedAt: now,
            status: 'running',
            summary: '본문 스트리밍',
            title: '답변 생성',
          });
        };

        const finishAnswerStreamStep = () => {
          if (!answerStreamStartedAt) {
            return;
          }

          const now = Date.now();
          upsertProgressStep({
            detail: '응답 본문 스트리밍이 완료되었습니다.',
            elapsedMs: now - answerStreamStartedAt,
            endedAt: now,
            id: ANSWER_STREAM_STEP_ID,
            name: ANSWER_STREAM_STEP_ID,
            startedAt: answerStreamStartedAt,
            status: 'completed',
            summary: '본문 스트리밍 완료',
            title: '답변 생성',
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

        for await (const event of streamChat({
          attachments,
          conversationId,
          message: question,
          pageContext,
          recentMessages,
          runId,
        }, { signal: abortController.signal })) {
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
            }
            if (event.stage === 'completed' && !lightspeedStageSeen && !fallbackAnswerSeen) {
              updateLightspeedStatus({
                fallbackActive: false,
                lastStatus: 'gateway_direct',
                streamProbe: 'not_used',
              });
            }
          }

          if (event.type === 'tool_plan') {
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
          }

          if (event.type === 'rca_context') {
            const evidenceFooter = buildEvidenceFooter(
              event.context,
              event.evidenceStatus,
              event.status,
            );
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
                              ((event.context as Record<string, unknown>).metadata as
                                | Record<string, unknown>
                                | undefined)?.digest ?? '',
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
            if (event.fallbackAnswer || event.source === 'gateway_fallback') {
              fallbackAnswerSeen = true;
              setMessages((prev) => markLastAssistantFallback(prev, event.gatewayContextDigest));
              updateLightspeedStatus({
                fallbackActive: true,
                lastContextDigest: event.gatewayContextDigest,
                lastStatus: event.streamProbe ?? 'failed',
                streamProbe: event.streamProbe ?? 'failed',
              });
            }
            if (event.content.trim()) {
              finishResponseWaitStep('본문 스트리밍 시작');
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
      } catch (error) {
        const stopped =
          stopRequestedRef.current ||
          (error instanceof Error && error.name === 'AbortError');

        flushAssistantTextQueueNow();
        if (stopped) {
          markRunningProgressFailed('사용자가 응답 생성을 중지했습니다.');
          setMessages((prev) =>
            setLastAssistantContentIfEmpty(prev, '응답 생성을 중지했습니다.'),
          );
        } else {
          markRunningProgressFailed(error instanceof Error ? error.message : 'AI response failed.');
          setMessages((prev) => [
            ...prev,
            {
              role: 'system',
              content: error instanceof Error ? error.message : 'AI response failed.',
            },
          ]);
        }
      } finally {
        chatAbortControllerRef.current = null;
        stopRequestedRef.current = false;
        setLoading(false);
      }
    },
    [
      enqueueAssistantText,
      assistantTaskMode,
      executionMode,
      flushAssistantTextQueueNow,
      input,
      loading,
      markRunningProgressFailed,
      scrollToBottom,
      conversationId,
      messages,
      pendingAttachments,
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
  }, [flushAssistantTextQueueNow, loading]);

  const closeAssistant = React.useCallback(() => {
    if (lockOpen) {
      return;
    }

    setOpen(false);
  }, [lockOpen]);

  const historySidebar = historySidebarOpen ? (
    <aside className="komsco-ai__history-sidebar" aria-label={copy.sidebar} style={historySidebarStyle}>
      <Button
        className="komsco-ai__new-chat"
        isDisabled={loading}
        onClick={startNewConversation}
        variant="secondary"
      >
        <PlusIcon />
        <span>{copy.newChat}</span>
      </Button>
      <div className="komsco-ai__history-title">
        <HistoryIcon />
        <span>{copy.history}</span>
      </div>
      <div className="komsco-ai__history-list">
        {conversationHistory.length === 0 ? (
          <div className="komsco-ai__history-empty">{copy.emptyHistory}</div>
        ) : (
          conversationHistory.map((conversation) => (
            <button
              className={`komsco-ai__history-item${
                conversation.id === activeSessionId ? ' komsco-ai__history-item--active' : ''
              }`}
              disabled={loading}
              key={conversation.id}
              onClick={() => loadConversation(conversation)}
              title={conversation.title}
              type="button"
            >
              <span>{conversation.title}</span>
              <small>{formatHistoryTime(conversation.updatedAt)}</small>
            </button>
          ))
        )}
      </div>
      <div className="komsco-ai__history-user" aria-label="현재 OpenShift 사용자">
        <div className="komsco-ai__history-user-avatar">
          <UserCircleIcon />
        </div>
        <div className="komsco-ai__history-user-main">
          <strong title={authSubject?.username || authSubjectError || '사용자 확인 중'}>
            {authSubject?.username || (authSubjectError ? '인증 확인 필요' : '확인 중')}
          </strong>
          <small title={clusterSummary?.apiUrl || ''}>{getClusterHost(clusterSummary?.apiUrl)}</small>
        </div>
      </div>
    </aside>
  ) : null;
  const historySidebarPortal =
    historySidebar && !fullScreen && typeof document !== 'undefined'
      ? createPortal(historySidebar, document.body)
      : null;

  return (
    <div
      className={`komsco-ai${embedded ? ' komsco-ai--embedded' : ''}${
        fullScreen ? ' komsco-ai--fullscreen-active' : ''
      }`}
    >
      {!open && !embedded && (
        <Button
          aria-label="Open Cywell AI"
          className="komsco-ai__fab"
          onClick={() => setOpen(true)}
        >
          <span className="komsco-ai__fab-icon">
            <img alt="" className="komsco-ai__fab-logo" src={kIcon} />
          </span>
          <span
            className={`komsco-ai__fab-status komsco-ai__fab-status--${assistantConnection.tone}`}
          />
        </Button>
      )}

      {(open || embedded || lockOpen) && (
        <FullscreenPortal active={fullScreen}>
        <div
          ref={surfaceRef}
          className={`komsco-ai__surface${fullScreen ? ' komsco-ai__surface--fullscreen' : ''}${
            historySidebarOpen ? ' komsco-ai__surface--history-open' : ''
          }${panelResizeUnlocked ? ' komsco-ai__surface--resize-unlocked' : ''}${
            !panelResizeUnlocked ? ' komsco-ai__surface--resize-locked' : ''
          }`}
          style={surfaceStyle}
        >
          {fullScreen ? historySidebar : null}
          <Card className={`komsco-ai__panel${fullScreen ? ' komsco-ai__panel--fullscreen' : ''}`}>
          <div className="komsco-ai__header">
            <Button
              aria-label={copy.openSidebar}
              className="komsco-ai__icon-button komsco-ai__sidebar-toggle"
              onClick={() => setHistorySidebarOpen((value) => !value)}
              title={copy.openSidebar}
              variant="plain"
            >
              <BarsIcon />
            </Button>
            <div className="komsco-ai__brand">
              <div className="komsco-ai__brand-mark">
                <img alt="" className="komsco-ai__brand-logo" src={komscoLogo} />
              </div>
            </div>
            <div className="komsco-ai__header-status" aria-label="AIOps 상태 및 실행 모드">
              <span
                aria-label={headerConnectionLabel}
                className={`komsco-ai__status-chip komsco-ai__status-chip--${assistantConnection.tone}`}
                title={headerConnectionLabel}
              >
                <span className="komsco-ai__status-chip-dot" />
                <span>
                  {assistantConnection.tone === 'connected'
                    ? '연결됨'
                    : assistantConnection.tone === 'danger'
                      ? '확인 필요'
                      : '확인 중'}
                </span>
              </span>
              <span
                className={`komsco-ai__mode-chip komsco-ai__mode-chip--${executionMode}`}
                title={getExecutionModeLabel(executionMode)}
              >
                {getExecutionModeShortLabel(executionMode)}
              </span>
              {renderExecutionModeToggle(
                executionMode,
                actionExecutionAvailable,
                actionExecutionDisabledReason,
                unrestrictedAvailable,
                unrestrictedDisabledReason,
                handleExecutionModeChange,
              )}
            </div>
            <div className="komsco-ai__header-actions">
              <Button
                aria-label={copy.switchLanguage}
                className="komsco-ai__icon-button komsco-ai__language-button"
                onClick={() => setUiLanguage((value) => (value === 'ko' ? 'en' : 'ko'))}
                title={copy.switchLanguage}
                variant="plain"
              >
                <GlobeIcon />
                <span className="komsco-ai__language-code">
                  {uiLanguage === 'ko' ? 'EN' : 'KO'}
                </span>
              </Button>
              <Button
                aria-label={fullScreen ? 'Exit full screen' : 'Open full screen'}
                className="komsco-ai__icon-button"
                onClick={() => setFullScreen((value) => !value)}
                variant="plain"
              >
                {fullScreen ? <CompressArrowsAltIcon /> : <ExpandArrowsAltIcon />}
              </Button>
              <Button
                aria-label={panelResizeUnlocked ? '창 크기 잠금' : '창 크기 잠금 해제'}
                className={`komsco-ai__icon-button${
                  panelResizeUnlocked ? ' komsco-ai__icon-button--active' : ''
                }`}
                onClick={togglePanelResizeLock}
                title={panelResizeUnlocked ? '창 크기 잠금' : '창 크기 잠금 해제'}
                variant="plain"
              >
                {panelResizeUnlocked ? <LockOpenIcon /> : <LockIcon />}
              </Button>
              {!lockOpen && (
                <Button
                  aria-label="Close Cywell AI"
                  className="komsco-ai__icon-button"
                  onClick={closeAssistant}
                  variant="plain"
                >
                  <TimesIcon />
                </Button>
              )}
            </div>
          </div>

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
                    <div className="komsco-ai__empty">
                      <div className="komsco-ai__empty-mark">
                        <img alt="" className="komsco-ai__empty-logo" src={kIcon} />
                      </div>
                      <div className="komsco-ai__empty-title">운영 확인 항목을 정리합니다</div>
                      <div className="komsco-ai__empty-text">
                        현재 콘솔 맥락과 OLS 조회 결과를 기준으로 안전한 점검 순서를 구성합니다.
                      </div>
                    </div>
                  )}

                  {messages.map((message, index) => {
                    const hasProgress = (message.progressSteps?.length ?? 0) > 0;
                    const hasContent = message.content.trim().length > 0;
                    const activeMessage = loading && index === messages.length - 1;
                    const waitingForContent =
                      activeMessage && message.role === 'assistant' && !hasContent;

                    return (
                      <div
                        className={`komsco-ai__message komsco-ai__message--${message.role}`}
                        key={`${message.role}-${index}`}
                      >
                        <div className="komsco-ai__message-stack">
                          <div className="komsco-ai__message-head">
                            {message.role !== 'user' && (
                              <div className="komsco-ai__message-avatar">
                                <MessageIcon role={message.role} />
                              </div>
                            )}
                            <div className="komsco-ai__message-label">
                              {getMessageLabel(message.role)}
                            </div>
                            {message.role === 'assistant' && message.fallbackAnswer && (
                              <span
                                className="komsco-ai__message-fallback"
                                title={
                                  message.gatewayContextDigest
                                    ? `Gateway context ${message.gatewayContextDigest}`
                                    : 'Gateway fallback answer'
                                }
                              >
                                Gateway fallback
                              </span>
                            )}
                            {message.role === 'assistant' && hasContent && (
                              <button
                                aria-label="답변 복사"
                                className="komsco-ai__message-copy"
                                onClick={() => copyMessage(message, index)}
                                title="답변 복사"
                                type="button"
                              >
                                <ClipboardIcon />
                                <span>{copiedMessageIndex === index ? '복사됨' : '복사'}</span>
                              </button>
                            )}
                          </div>
                          {waitingForContent && <TypingIndicator />}
                          {(hasContent || (!hasProgress && !waitingForContent)) && (
                            <div className="komsco-ai__message-content">
                              {renderFormattedContent(message, setPreviewAttachment)}
                            </div>
                          )}
                          {message.role === 'assistant' &&
                            hasContent &&
                            renderEvidenceFooter(message.evidenceFooter)}
                          {hasProgress && message.progressSteps && (
                            <ProgressTimeline active={false} steps={message.progressSteps} />
                          )}
                        </div>
                      </div>
                    );
                  })}

                  {loading && messages[messages.length - 1]?.role !== 'assistant' && (
                    <div className="komsco-ai__loading">
                      <TypingIndicator />
                    </div>
                  )}
                  <div ref={bodyEndRef} />
                </div>
              </CardBody>

              <div
                className={`komsco-ai__composer-wrap${
                  dragActive ? ' komsco-ai__composer-wrap--drag-active' : ''
                }`}
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
              >
                {showScrollToBottom && (
                  <Button
                    aria-label="최신 답변으로 이동"
                    className="komsco-ai__scroll-bottom"
                    onClick={() => {
                      setStickToBottom(true);
                      setShowScrollToBottom(false);
                      scrollToBottom('auto');
                    }}
                    variant="secondary"
                  >
                    <ArrowDownIcon />
                  </Button>
                )}
                <div className="komsco-ai__input">
                  <input
                    accept="image/png,image/jpeg,image/webp,image/gif"
                    aria-label="이미지 첨부"
                    className="komsco-ai__file-input"
                    disabled={loading}
                    multiple
                    onChange={handleFileInputChange}
                    ref={fileInputRef}
                    type="file"
                  />
                  <div className="komsco-ai__composer">
                    {pendingAttachments.length > 0 && (
                      <div className="komsco-ai__pending-attachments">
                        {pendingAttachments.map((attachment) => (
                          <div className="komsco-ai__pending-attachment" key={attachment.id}>
                            <button
                              aria-label={`${attachment.name} 크게 보기`}
                              className="komsco-ai__pending-attachment-preview"
                              onClick={() => setPreviewAttachment(attachment)}
                              title={`${attachment.name} · ${formatFileSize(attachment.size)}`}
                              type="button"
                            >
                              <img
                                alt={attachment.name}
                                className="komsco-ai__pending-attachment-image"
                                src={getAttachmentPreviewUrl(attachment)}
                              />
                            </button>
                            <Button
                              aria-label={`${attachment.name} 첨부 제거`}
                              className="komsco-ai__attachment-remove"
                              isDisabled={loading}
                              onClick={(event) => {
                                event.stopPropagation();
                                removeAttachment(attachment.id);
                              }}
                              variant="plain"
                            >
                              <TimesIcon />
                            </Button>
                          </div>
                        ))}
                      </div>
                    )}
                    {attachmentError && (
                      <div className="komsco-ai__attachment-error">{attachmentError}</div>
                    )}
                    <TextArea
                      aria-label="Question"
                      autoResize
                      className="komsco-ai__textarea"
                      onChange={(_, value) => setInput(value)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' && !event.shiftKey) {
                          event.preventDefault();
                          send();
                        }
                      }}
                      onPaste={handlePaste}
                      placeholder={
                        uiLanguage === 'ko'
                          ? TASK_MODE_PLACEHOLDERS[assistantTaskMode]
                          : copy.inputPlaceholder
                      }
                      rows={1}
                      style={{ maxHeight: 110, minHeight: 35, overflowY: 'auto' }}
                      value={input}
                    />
                    <div className="komsco-ai__composer-toolbar">
                      <div className="komsco-ai__composer-tools">
                        <div className="komsco-ai__quick-menu" ref={quickPromptMenuRef}>
                          <Button
                            aria-expanded={quickPromptMenuOpen}
                            aria-label="자주 쓰는 점검 질문 열기"
                            aria-haspopup="menu"
                            className="komsco-ai__tool-button komsco-ai__quick-menu-trigger"
                            isDisabled={loading}
                            onClick={() => {
                              setQuickPromptMenuOpen((value) => !value);
                              setTaskModeMenuOpen(false);
                            }}
                            variant="plain"
                          >
                            <PlusIcon />
                          </Button>
                          {quickPromptMenuOpen && (
                            <div className="komsco-ai__quick-menu-panel" role="menu">
                              {QUICK_PROMPTS.map((item) => (
                                <button
                                  className="komsco-ai__quick-menu-item"
                                  key={item.label}
                                  onClick={() => {
                                    setQuickPromptMenuOpen(false);
                                    void send(item.prompt);
                                  }}
                                  role="menuitem"
                                  type="button"
                                >
                                  <span className="komsco-ai__quick-prompt-icon">{item.icon}</span>
                                  <span className="komsco-ai__quick-menu-copy">
                                    <strong>{item.label}</strong>
                                    <small>{item.prompt}</small>
                                  </span>
                                </button>
                              ))}
                            </div>
                          )}
                        </div>
                        <Button
                          aria-label="이미지 첨부"
                          className="komsco-ai__tool-button komsco-ai__attach"
                          isDisabled={loading || pendingAttachments.length >= MAX_IMAGE_ATTACHMENTS}
                          onClick={() => fileInputRef.current?.click()}
                          variant="plain"
                        >
                          <PaperclipIcon />
                        </Button>
                        <div className="komsco-ai__task-mode" ref={taskModeMenuRef}>
                          <button
                            aria-expanded={taskModeMenuOpen}
                            aria-haspopup="listbox"
                            className="komsco-ai__task-mode-button"
                            data-assistant-task-mode={assistantTaskMode}
                            disabled={loading}
                            onClick={() => {
                              setTaskModeMenuOpen((value) => !value);
                              setQuickPromptMenuOpen(false);
                            }}
                            type="button"
                          >
                            <span className="komsco-ai__task-mode-icon">{selectedTaskMode.icon}</span>
                            <span className="komsco-ai__task-mode-label">{selectedTaskMode.label}</span>
                            <CaretDownIcon />
                          </button>
                          {taskModeMenuOpen && (
                            <div className="komsco-ai__task-mode-menu" role="listbox">
                              {ASSISTANT_TASK_MODES.map((item) => (
                                <button
                                  aria-selected={assistantTaskMode === item.value}
                                  className="komsco-ai__task-mode-option"
                                  data-komsco-task-mode={item.value}
                                  key={item.value}
                                  onClick={() => {
                                    setAssistantTaskMode(item.value);
                                    setTaskModeMenuOpen(false);
                                  }}
                                  role="option"
                                  type="button"
                                >
                                  <span className="komsco-ai__task-mode-icon">{item.icon}</span>
                                  <span>
                                    <strong>{item.label}</strong>
                                    <small>{item.description}</small>
                                  </span>
                                </button>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                      <Button
                        aria-label={loading ? '응답 중지' : '질문 전송'}
                        className={`komsco-ai__send${loading ? ' komsco-ai__send--stop' : ''}`}
                        isDisabled={!loading && !input.trim() && pendingAttachments.length === 0}
                        onClick={() => {
                          if (loading) {
                            cancelAssistantResponse();
                            return;
                          }
                          void send();
                        }}
                        variant="plain"
                      >
                        {loading ? <StopIcon /> : <PaperPlaneIcon />}
                      </Button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            {renderInsightRail(
              clusterSummary,
              clusterSummaryLoading,
              clusterSummaryError,
              aiopsStatus,
              aiopsStatusError,
              executionMode,
              aiopsActionBusyId,
              aiopsActionError,
              aiopsActionNotice,
              handleAiopsAction,
            )}
          </div>
          </Card>
          {panelResizeUnlocked && !fullScreen && (
            <div className="komsco-ai__resize-handles" aria-label="채팅창 크기 조절 핸들">
              {(['n', 'ne', 'e', 'se', 's', 'sw', 'w', 'nw'] as PanelResizeDirection[]).map(
                (direction) => (
                  <button
                    aria-label={`채팅창 ${direction} 방향 크기 조절`}
                    className={`komsco-ai__resize-handle komsco-ai__resize-handle--${direction}${
                      direction === 'se' ? ' komsco-ai__resize-grip' : ''
                    }`}
                    key={direction}
                    onMouseDown={(event) => startPanelResize(event, direction)}
                    type="button"
                  />
                ),
              )}
            </div>
          )}
        </div>
        </FullscreenPortal>
      )}
      {historySidebarPortal}
      {previewAttachment && (
        <div
          aria-label={`${previewAttachment.name} 크게 보기`}
          aria-modal="true"
          className="komsco-ai__image-lightbox"
          onClick={() => setPreviewAttachment(null)}
          role="dialog"
        >
          <div
            className="komsco-ai__image-lightbox-panel"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="komsco-ai__image-lightbox-head">
              <div className="komsco-ai__image-lightbox-title">
                <strong>{previewAttachment.name}</strong>
                <span>
                  {previewAttachment.mimeType} · {formatFileSize(previewAttachment.size)}
                </span>
              </div>
              <Button
                aria-label="이미지 크게 보기 닫기"
                className="komsco-ai__image-lightbox-close"
                onClick={() => setPreviewAttachment(null)}
                variant="plain"
              >
                <TimesIcon />
              </Button>
            </div>
            <div className="komsco-ai__image-lightbox-body">
              <img
                alt={previewAttachment.name}
                className="komsco-ai__image-lightbox-image"
                src={getAttachmentPreviewUrl(previewAttachment)}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AssistantLauncher;
