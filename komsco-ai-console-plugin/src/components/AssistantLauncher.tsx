import * as React from 'react';
import { Button, Card, CardBody, Switch, TextArea } from '@patternfly/react-core';
import * as ReactDOM from 'react-dom';
import {
  CoolArrowDownIcon,
  CoolCaretDownIcon,
  CoolChatDotsIcon,
  CoolCheckIcon,
  CoolClockIcon,
  CoolCloseIcon,
  CoolComposeIcon,
  CoolCopyIcon,
  CoolDesktopTowerIcon,
  CoolDocumentIcon,
  CoolExpandIcon,
  CoolGlobeIcon,
  CoolInfoIcon,
  CoolListChecklistIcon,
  CoolLockIcon,
  CoolLockOpenIcon,
  CoolMenuIcon,
  CoolPaperclipIcon,
  CoolPaperPlaneIcon,
  CoolPlusIcon,
  CoolSettingsIcon,
  CoolShieldCheckIcon,
  CoolShrinkIcon,
  CoolStopIcon,
  CoolTerminalIcon,
  CoolUserCircleIcon,
  CoolWarningIcon,
} from './coolicons';
import {
  type AiopsActionCandidate,
  type AiopsRecord,
  type AiopsRuntimeStatus,
  type AuthSubject,
  type ChatContextMessage,
  type ClusterSummary,
  type EvidenceStatusItem,
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
  streamChat,
  uploadRagDocument,
  uploadRagDocumentFile,
} from '../services/aiGateway';
import {
  evidenceCount,
  redactSensitiveText,
  safeEvidenceText,
  shortDigest,
} from '../utils/evidenceDisplay';
import kIcon from '../assets/k_icon.png';
import komscoLogo from '../assets/komsco_logo.svg';
import './assistant.css';

const QUICK_PROMPTS = [
  {
    icon: <CoolDesktopTowerIcon />,
    label: 'Node 상태',
    prompt: '현재 클러스터 노드 상태를 요약하고 이상 징후가 있으면 알려줘.',
  },
  {
    icon: <CoolWarningIcon />,
    label: '최근 경고',
    prompt:
      '최근 OpenShift 경고와 우선 확인할 항목을 실제 근거와 추가 확인 필요 항목으로 구분해서 정리해줘.',
  },
  {
    icon: <CoolTerminalIcon />,
    label: '화면 진단',
    prompt:
      '현재 화면의 대상 리소스에 대해 가능한 안전 조회를 실행하고, 확인한 증적과 원인 후보, 승인 가능한 조치 후보를 정리해줘.',
  },
  {
    icon: <CoolShieldCheckIcon />,
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
    icon: <CoolChatDotsIcon />,
    label: 'Ask',
    value: 'ask',
  },
  {
    description: '원인 분석과 점검 절차',
    icon: <CoolSettingsIcon />,
    label: 'Troubleshooting',
    value: 'troubleshooting',
  },
];

const TASK_MODE_PLACEHOLDERS: Record<AssistantTaskMode, string> = {
  ask: '무엇을 확인할까요?',
  troubleshooting: '어떤 문제를 점검할까요?',
};

type HistoryPanelView = 'chats' | 'uploads';

type Message = {
  role: 'user' | 'assistant' | 'system';
  answerContract?: string;
  attachments?: ImageAttachment[];
  content: string;
  evidenceFooter?: EvidenceFooter;
  fallbackAnswer?: boolean;
  gatewayContextDigest?: string;
  progressSteps?: ProgressStep[];
  timestamp?: number;
  toolPlan?: ToolPlanFooter;
};

type ToolPlanStep = {
  adapter?: string;
  evidenceType?: string;
  reason?: string;
  step?: number | string;
  tool?: string;
  verb?: string;
};

type ToolPlanMissingEvidence = {
  reason?: string;
  type?: string;
};

type ToolPlanFooter = {
  executionPolicyMode?: string;
  missingEvidence: ToolPlanMissingEvidence[];
  steps: ToolPlanStep[];
  targetNamespace?: string;
  targetResourceKind?: string;
  targetResourceName?: string;
  taskType?: string;
  validationOk?: boolean;
  validationViolations: string[];
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

type EvidenceFooterQueryStep = {
  adapter?: string;
  evidenceType?: string;
  reason?: string;
  status?: string;
  step?: string;
  tool?: string;
};

type RagAppendixRef = {
  sourceUri?: string;
  title: string;
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
  queryPlan: EvidenceFooterQueryStep[];
  status?: string;
};

type AiopsExecutionMode = 'read-only' | 'execute' | 'unrestricted';
type AssistantTaskMode = 'ask' | 'troubleshooting';
type UiLanguage = 'ko' | 'en';
type PanelResizeDirection = 'n' | 'ne' | 'e' | 'se' | 's' | 'sw' | 'w' | 'nw';

type AssistantDraftPrompt = {
  id: string;
  pageContext?: Record<string, unknown>;
  prompt: string;
  taskMode?: AssistantTaskMode;
};

const draftExecutionMode = (pageContext?: Record<string, unknown>): AiopsExecutionMode | null => {
  const value = String(pageContext?.aiopsExecutionMode ?? '').trim().toLowerCase();
  if (value === 'read-only' || value === 'read_only' || value === 'evidence-check' || value === 'evidence_check') {
    return 'read-only';
  }
  if (value === 'execute' || value === 'unrestricted') {
    return value;
  }
  return null;
};

const TASK_MODE_EMPTY_COPY: Record<
  AssistantTaskMode,
  Record<UiLanguage, { title: string; text: string }>
> = {
  ask: {
    ko: {
      title: '무엇을 확인할까요?',
      text: '클러스터 상태, 최근 경고, 노드와 Pod 현황을 승인 실행으로 확인합니다.',
    },
    en: {
      title: 'What should I check?',
      text: 'Ask about cluster status, recent alerts, nodes, and pods in approval-gated execution mode.',
    },
  },
  troubleshooting: {
    ko: {
      title: '문제 원인을 점검합니다',
      text: 'Event, Pod, Operator, Metrics 근거를 모아 원인 후보와 다음 확인 절차를 정리합니다.',
    },
    en: {
      title: 'Troubleshoot an issue',
      text: 'I will collect evidence from events, pods, operators, and metrics, then organize likely causes and next checks.',
    },
  },
};

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
const ACCEPTED_RAG_DOCUMENT_MIME_TYPES = new Set([
  'application/pdf',
  'application/json',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/x-yaml',
  'text/log',
  'text/markdown',
  'text/plain',
  'text/x-markdown',
]);
const ACCEPTED_RAG_DOCUMENT_EXTENSIONS = [
  '.docx',
  '.json',
  '.log',
  '.md',
  '.markdown',
  '.pdf',
  '.pptx',
  '.txt',
  '.xlsx',
  '.yaml',
  '.yml',
];
const MULTIPART_RAG_DOCUMENT_EXTENSIONS = ['.docx', '.pdf', '.pptx', '.xlsx'];
const MULTIPART_RAG_DOCUMENT_MIME_TYPES = new Set([
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
]);
const FILE_INPUT_ACCEPT = [
  'image/png',
  'image/jpeg',
  'image/webp',
  'image/gif',
  'text/plain',
  'text/markdown',
  'application/json',
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  '.docx',
  '.json',
  '.log',
  '.md',
  '.markdown',
  '.pdf',
  '.pptx',
  '.txt',
  '.xlsx',
  '.yaml',
  '.yml',
].join(',');
const MAX_IMAGE_ATTACHMENTS = 4;
const MAX_IMAGE_ATTACHMENT_BYTES = 2 * 1024 * 1024;
const MAX_IMAGE_ATTACHMENT_TOTAL_BYTES = 6 * 1024 * 1024;
const MAX_RAG_DOCUMENT_UPLOAD_BYTES = 5 * 1024 * 1024;
const MAX_RECENT_CONTEXT_MESSAGES = 8;
const CLUSTER_SUMMARY_REFRESH_MS = 10 * 1000;
const DEFAULT_AIOPS_EXECUTION_MODE: AiopsExecutionMode = 'execute';
const HISTORY_DRAWER_WIDTH = 236;
const MIN_STOP_BUTTON_VISIBLE_MS = 2000;
const SCROLL_BOTTOM_THRESHOLD_PX = 80;
const GATEWAY_PREP_TOOLS = new Set(['access_check', 'attachment_check']);
const GATEWAY_PREP_STEP_ID = 'gateway-request-prep';
const ACTION_ANSWER_CONTRACT_PATTERN = /(^|[-_])action([-.]|$)/i;
const RCA_PLAN_STEP_ID = 'assistant-rca-plan';
const RCA_CONTEXT_STEP_ID = 'assistant-rca-context';
const RUN_LOOP_STEP_ID = 'assistant-run-loop';
const RESPONSE_WAIT_STEP_ID = 'assistant-response-wait';
const ANSWER_STREAM_STEP_ID = 'assistant-answer-stream';
const ASSISTANT_TYPEWRITER_CHARS = 18;
const ASSISTANT_TYPEWRITER_INTERVAL_MS = 24;
const flushReactSync = (callback: () => void) => {
  const flushSync = (ReactDOM as unknown as { flushSync?: (syncCallback: () => void) => void })
    .flushSync;

  if (flushSync) {
    flushSync(callback);
    return;
  }

  callback();
};
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
  runtime_tool_plan: '증거 수집 계획',
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
    detail: '사용자 권한과 질문 내용을 확인한 뒤 답변 생성을 요청합니다.',
    label: '요청 확인',
    toolName: 'access_check',
  },
  {
    detail: '첨부 이미지 형식과 크기를 확인한 뒤 필요한 메타데이터만 답변 요청에 포함합니다.',
    label: '첨부 확인',
    toolName: 'attachment_check',
  },
];
const RESPONSE_WAIT_PHASES = [
  {
    activity: 'Gateway가 OpenShift Lightspeed에 답변 생성을 요청했습니다.',
    title: '답변 요청',
  },
  {
    activity: 'OpenShift Lightspeed가 사용자 권한 범위 안에서 질문을 처리합니다.',
    title: '질문 처리',
  },
  {
    activity: '필요한 도구 조회와 답변 생성을 기다립니다.',
    title: '답변 준비',
  },
  {
    activity: '생성된 답변을 화면에 표시할 준비를 합니다.',
    title: '화면 표시 준비',
  },
];

const UI_COPY: Record<
  UiLanguage,
  {
    emptyHistory: string;
    emptyUploadedDocs: string;
    fileAttach: string;
    history: string;
    inputPlaceholder: string;
    newChat: string;
    openHistoryPanel: string;
    openUploadedDocs: string;
    openSidebar: string;
    sidebar: string;
    switchLanguage: string;
    userLabel: string;
    systemLabel: string;
    answerCopy: string;
    answerCopied: string;
    scrollToLatest: string;
    uploadedDocs: string;
    uploadedDocsError: string;
    uploadedDocsLoading: string;
  }
> = {
  ko: {
    emptyHistory: '아직 저장된 대화가 없습니다.',
    emptyUploadedDocs: '업로드된 문서가 없습니다. 파일 첨부 RAG 연결 후 이곳에 표시됩니다.',
    fileAttach: '파일 첨부',
    history: '지난 대화',
    inputPlaceholder: '현재 화면이나 클러스터 상태를 질문하세요',
    newChat: '새 채팅',
    openHistoryPanel: '대화 기록 패널',
    openUploadedDocs: '업로드 문서 패널',
    openSidebar: '대화 사이드바',
    sidebar: '대화 기록',
    switchLanguage: 'Switch to English',
    userLabel: '사용자',
    systemLabel: '시스템',
    answerCopy: '복사',
    answerCopied: '복사됨',
    scrollToLatest: '최신 답변으로 이동',
    uploadedDocs: '업로드 문서',
    uploadedDocsError: '업로드 문서 목록을 불러오지 못했습니다.',
    uploadedDocsLoading: '업로드 문서를 확인하는 중입니다.',
  },
  en: {
    emptyHistory: 'No saved conversations yet.',
    emptyUploadedDocs:
      'No uploaded documents yet. They will appear here after file-attachment RAG ingestion is connected.',
    fileAttach: 'Attach file',
    history: 'Recent chats',
    inputPlaceholder: 'Ask about the current screen or cluster state',
    newChat: 'New chat',
    openHistoryPanel: 'Conversation history panel',
    openUploadedDocs: 'Uploaded documents panel',
    openSidebar: 'Conversation sidebar',
    sidebar: 'Conversation history',
    switchLanguage: '한국어로 전환',
    userLabel: 'User',
    systemLabel: 'System',
    answerCopy: 'Copy',
    answerCopied: 'Copied',
    scrollToLatest: 'Jump to latest answer',
    uploadedDocs: 'Uploaded documents',
    uploadedDocsError: 'Unable to load uploaded documents.',
    uploadedDocsLoading: 'Checking uploaded documents.',
  },
};

const getMessageLabel = (role: Message['role'], language: UiLanguage): string => {
  if (role === 'user') {
    return UI_COPY[language].userLabel;
  }

  if (role === 'system') {
    return UI_COPY[language].systemLabel;
  }

  return 'KOMSCO AI AGENT';
};

const MessageIcon: React.FC<{ role: Message['role'] }> = ({ role }) => {
  if (role === 'user') {
    return <CoolUserCircleIcon />;
  }

  if (role === 'system') {
    return <CoolInfoIcon />;
  }

  return <img alt="" className="komsco-ai__message-logo" src={kIcon} />;
};

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

const STORED_CONVERSATION_HISTORY_KEY = 'komsco-ai.assistant.conversation-history.v1';
const STORED_ACTIVE_CONVERSATION_KEY = 'komsco-ai.assistant.active-conversation.v1';
const STORED_UI_LANGUAGE_KEY = 'komsco-ai.assistant.ui-language.v1';
const MAX_STORED_CONVERSATIONS = 12;

type StoredActiveConversation = {
  activeSessionId: string;
  conversationId?: string;
  messages: Message[];
};

const getAssistantStorage = (): Storage | null => {
  if (typeof window === 'undefined') {
    return null;
  }

  try {
    return window.localStorage;
  } catch {
    return null;
  }
};

const isStorageRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const readStoredJson = (key: string): unknown => {
  const storage = getAssistantStorage();
  if (!storage) {
    return undefined;
  }

  try {
    const raw = storage.getItem(key);
    return raw ? JSON.parse(raw) : undefined;
  } catch {
    return undefined;
  }
};

const writeStoredJson = (key: string, value: unknown): void => {
  const storage = getAssistantStorage();
  if (!storage) {
    return;
  }

  try {
    storage.setItem(key, JSON.stringify(value));
  } catch {
    // Browser storage is best-effort UI state. Gateway JSONL remains the audit source.
  }
};

const sanitizeMessageForStorage = (message: Message): Message => {
  const { attachments: _attachments, ...storedMessage } = message;
  return storedMessage;
};

const normalizeStoredMessage = (value: unknown): Message | undefined => {
  if (!isStorageRecord(value)) {
    return undefined;
  }

  const { role, content } = value;
  if (
    (role !== 'user' && role !== 'assistant' && role !== 'system') ||
    typeof content !== 'string'
  ) {
    return undefined;
  }

  return sanitizeMessageForStorage({
    ...(value as Message),
    content,
    role,
  });
};

const normalizeStoredMessages = (value: unknown): Message[] =>
  Array.isArray(value)
    ? value.flatMap((message) => {
        const normalized = normalizeStoredMessage(message);
        return normalized ? [normalized] : [];
      })
    : [];

const normalizeStoredConversation = (value: unknown): ConversationHistoryItem | undefined => {
  if (!isStorageRecord(value)) {
    return undefined;
  }

  const messages = normalizeStoredMessages(value.messages);
  if (messages.length === 0) {
    return undefined;
  }

  const id = typeof value.id === 'string' && value.id ? value.id : createRunId();
  const title =
    typeof value.title === 'string' && value.title.trim()
      ? value.title
      : getConversationTitle(messages, 'ko');
  const updatedAt =
    typeof value.updatedAt === 'number' && Number.isFinite(value.updatedAt)
      ? value.updatedAt
      : Date.now();
  const conversationId =
    typeof value.conversationId === 'string' && value.conversationId
      ? value.conversationId
      : undefined;

  return {
    id,
    title,
    updatedAt,
    conversationId,
    messages,
  };
};

const readStoredConversationHistory = (): ConversationHistoryItem[] => {
  const stored = readStoredJson(STORED_CONVERSATION_HISTORY_KEY);
  if (!Array.isArray(stored)) {
    return [];
  }

  return stored
    .flatMap((conversation) => {
      const normalized = normalizeStoredConversation(conversation);
      return normalized ? [normalized] : [];
    })
    .slice(0, MAX_STORED_CONVERSATIONS);
};

const writeStoredConversationHistory = (
  conversationHistory: ConversationHistoryItem[],
): void => {
  writeStoredJson(
    STORED_CONVERSATION_HISTORY_KEY,
    conversationHistory.slice(0, MAX_STORED_CONVERSATIONS).map((conversation) => ({
      ...conversation,
      messages: conversation.messages.map(sanitizeMessageForStorage),
    })),
  );
};

const readStoredActiveConversation = (): StoredActiveConversation | undefined => {
  const stored = readStoredJson(STORED_ACTIVE_CONVERSATION_KEY);
  if (!isStorageRecord(stored)) {
    return undefined;
  }

  const messages = normalizeStoredMessages(stored.messages);
  const activeSessionId =
    typeof stored.activeSessionId === 'string' && stored.activeSessionId
      ? stored.activeSessionId
      : createRunId();
  const conversationId =
    typeof stored.conversationId === 'string' && stored.conversationId
      ? stored.conversationId
      : undefined;

  return {
    activeSessionId,
    conversationId,
    messages,
  };
};

const writeStoredActiveConversation = (snapshot: StoredActiveConversation): void => {
  writeStoredJson(STORED_ACTIVE_CONVERSATION_KEY, {
    ...snapshot,
    messages: snapshot.messages.map(sanitizeMessageForStorage),
  });
};

const normalizeUiLanguage = (value: unknown): UiLanguage =>
  value === 'en' || value === 'ko' ? value : 'ko';

const readStoredUiLanguage = (): UiLanguage => normalizeUiLanguage(readStoredJson(STORED_UI_LANGUAGE_KEY));

const writeStoredUiLanguage = (language: UiLanguage): void => {
  writeStoredJson(STORED_UI_LANGUAGE_KEY, language);
};

const languageLocale = (language: UiLanguage): string => (language === 'ko' ? 'ko-KR' : 'en-US');

const formatHistoryTime = (timestamp: number, language: UiLanguage): string =>
  new Date(timestamp).toLocaleTimeString(languageLocale(language), {
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

const asRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};

const asRecordArray = (value: unknown): Record<string, unknown>[] =>
  Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> =>
        Boolean(item && typeof item === 'object' && !Array.isArray(item)),
      )
    : [];

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

const normalizeEvidenceQueryStep = (value: Record<string, unknown>): EvidenceFooterQueryStep => ({
  adapter: safeEvidenceText(value.adapter),
  evidenceType: safeEvidenceText(value.evidenceType || value.evidence_type, 'evidence'),
  reason: safeEvidenceText(value.reason || '근거 수집 단계'),
  status: safeEvidenceText(value.status || 'planned'),
  step: safeEvidenceText(value.step),
  tool: safeEvidenceText(value.tool || value.official_tool, 'tool'),
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
  const analysisPlan = asRecord(contextRecord.analysisPlan);
  const answerExperience = asRecord(contextRecord.answerExperience);
  const collectedRefs = asRecordArray(evidence.collectedRefs).map(normalizeEvidenceRef);
  const failedRefs = asRecordArray(evidence.failedRefs).map(normalizeEvidenceRef);
  const missing = asRecordArray(evidence.missing).map(normalizeMissingEvidence);
  const queryPlanSource = asRecordArray(answerExperience.queryPlan).length
    ? asRecordArray(answerExperience.queryPlan)
    : asRecordArray(analysisPlan.queryPlan).length
      ? asRecordArray(analysisPlan.queryPlan)
      : asRecordArray(analysisPlan.evidenceCollectionSteps);
  const queryPlan = queryPlanSource.map(normalizeEvidenceQueryStep);
  const statusCounts = evidenceStatusCounts(evidenceStatus);

  return {
    collectedCount: evidenceCount(
      summary.collectedCount,
      statusCounts.collected,
      collectedRefs.length,
    ),
    collectedRefs,
    contextId: safeEvidenceText(metadata.contextId),
    digest: safeEvidenceText(metadata.digest),
    failedCount: evidenceCount(summary.failedCount, 0, failedRefs.length),
    failedRefs,
    missing,
    missingCount: evidenceCount(summary.missingCount, statusCounts.missing, missing.length),
    phase: safeEvidenceText(metadata.phase),
    queryPlan,
    status: safeEvidenceText(status),
  };
};

const rcaRailEvidenceCounts = (status: AiopsRuntimeStatus | null | undefined) => {
  const safetyContract = status?.spec.safetyContract;
  const statusCounts = evidenceStatusCounts(safetyContract?.evidenceStatus);
  const contextRecord = asRecord(safetyContract?.rcaContextStatus?.latestContext);
  const evidence = asRecord(contextRecord.evidence);
  const summary = asRecord(evidence.summary);
  const collectedRefs = asRecordArray(evidence.collectedRefs);
  const missing = asRecordArray(evidence.missing);

  return {
    collected: Math.max(
      statusCounts.collected,
      evidenceCount(summary.collectedCount, statusCounts.collected, collectedRefs.length),
    ),
    missing: Math.max(
      statusCounts.missing,
      evidenceCount(summary.missingCount, statusCounts.missing, missing.length),
    ),
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

const buildToolPlanFooter = (raw: unknown): ToolPlanFooter | undefined => {
  if (!raw || typeof raw !== 'object') {
    return undefined;
  }

  const plan = raw as Record<string, unknown>;
  const target = (plan.target && typeof plan.target === 'object' ? plan.target : {}) as Record<
    string,
    unknown
  >;
  const executionPolicy = (
    plan.execution_policy && typeof plan.execution_policy === 'object' ? plan.execution_policy : {}
  ) as Record<string, unknown>;
  const validation = (
    plan.validation && typeof plan.validation === 'object' ? plan.validation : {}
  ) as Record<string, unknown>;

  const isRecord = (value: unknown): value is Record<string, unknown> =>
    Boolean(value) && typeof value === 'object';

  const rawSteps = Array.isArray(plan.tool_plan) ? plan.tool_plan.filter(isRecord) : [];
  const steps: ToolPlanStep[] = rawSteps.map((step) => {
    const stepId =
      typeof step.step === 'number' || typeof step.step === 'string' ? step.step : undefined;
    return {
      adapter: typeof step.adapter === 'string' ? step.adapter : undefined,
      evidenceType: typeof step.evidence_type === 'string' ? step.evidence_type : undefined,
      reason: typeof step.reason === 'string' ? step.reason : undefined,
      step: stepId,
      tool: typeof step.tool === 'string' ? step.tool : undefined,
      verb: typeof step.verb === 'string' ? step.verb : undefined,
    };
  });

  const rawMissing = Array.isArray(plan.missing_evidence)
    ? plan.missing_evidence.filter(isRecord)
    : [];
  const missingEvidence: ToolPlanMissingEvidence[] = rawMissing.map((item) => ({
    reason: typeof item.reason === 'string' ? item.reason : undefined,
    type: typeof item.type === 'string' ? item.type : undefined,
  }));

  if (steps.length === 0) {
    return undefined;
  }

  return {
    executionPolicyMode:
      typeof executionPolicy.mode === 'string' ? executionPolicy.mode : undefined,
    missingEvidence,
    steps,
    targetNamespace: typeof target.namespace === 'string' ? target.namespace : undefined,
    targetResourceKind: typeof target.resourceKind === 'string' ? target.resourceKind : undefined,
    targetResourceName: typeof target.resourceName === 'string' ? target.resourceName : undefined,
    taskType: typeof plan.task_type === 'string' ? plan.task_type : undefined,
    validationOk: typeof validation.ok === 'boolean' ? validation.ok : undefined,
    validationViolations: Array.isArray(validation.violations)
      ? validation.violations.filter((item): item is string => typeof item === 'string')
      : [],
  };
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
    fallbackAnswer: true,
    gatewayContextDigest: gatewayContextDigest || next[assistantIndex].gatewayContextDigest,
  };

  return next;
};

const markLastAssistantAnswerContract = (messages: Message[], answerContract?: string): Message[] => {
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

const isActionAnswerContract = (answerContract?: string): boolean =>
  Boolean(answerContract && ACTION_ANSWER_CONTRACT_PATTERN.test(answerContract));

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

const stripDefaultEvidenceAppendix = (content: string): string => {
  const lines = content.split('\n');
  const appendixIndex = lines.findIndex((line) =>
    /^\s*\[?\s*RAG\s*근거\s*\]?\s*$/i.test(line.trim()),
  );

  if (appendixIndex < 0) {
    return content;
  }

  return lines.slice(0, appendixIndex).join('\n').trimEnd();
};

const extractRagAppendixRefs = (content: string): RagAppendixRef[] => {
  const lines = content.split('\n');
  const appendixIndex = lines.findIndex((line) =>
    /^\s*\[?\s*RAG\s*근거\s*\]?\s*$/i.test(line.trim()),
  );

  if (appendixIndex < 0) {
    return [];
  }

  const refs: RagAppendixRef[] = [];
  lines.slice(appendixIndex + 1).forEach((rawLine) => {
    const line = rawLine.trim();
    const titleMatch = line.match(/^\d+\.\s+(.+?)(?:\s+\([^)]*\))?$/);
    if (titleMatch) {
      refs.push({ title: titleMatch[1].trim() });
      return;
    }

    const sourceMatch = line.match(/^[-*]\s*source:\s*(.+)$/i);
    if (sourceMatch && refs.length > 0) {
      refs[refs.length - 1] = {
        ...refs[refs.length - 1],
        sourceUri: sourceMatch[1].trim(),
      };
    }
  });

  return refs.slice(0, 5);
};

const evidenceTypeLabel = (type?: string): string => {
  const normalized = String(type || '').trim().toLowerCase();
  if (normalized === 'node') {
    return '노드';
  }
  if (normalized === 'alert') {
    return '경고';
  }
  if (normalized === 'metric') {
    return '메트릭';
  }
  if (normalized === 'pod_status' || normalized === 'pod') {
    return 'Pod';
  }
  if (normalized === 'snapshot') {
    return '스냅샷';
  }
  if (normalized === 'event') {
    return '이벤트';
  }
  if (normalized === 'runbook') {
    return '런북';
  }
  if (normalized === 'openshift_api') {
    return 'OpenShift API';
  }
  if (normalized === 'openshift') {
    return 'OpenShift';
  }
  if (!normalized) {
    return '근거';
  }
  return type || '근거';
};

const evidenceStepStatusLabel = (status?: string): string => {
  const normalized = String(status || '').trim().toLowerCase();
  if (normalized === 'collected' || normalized === 'success' || normalized === 'succeeded') {
    return '수집됨';
  }
  if (normalized === 'not_attempted' || normalized === 'planned' || normalized === 'pending') {
    return '대기';
  }
  if (normalized === 'failed' || normalized === 'error') {
    return '확인 필요';
  }
  return status || '대기';
};

const rcaContextPhaseLabel = (phase?: string): string => {
  const normalized = String(phase || '').trim().toLowerCase();
  if (normalized === 'post_answer') {
    return '답변 근거 연결 완료';
  }
  if (normalized === 'pre_answer' || normalized === 'plan_ready') {
    return '답변 근거 준비 완료';
  }
  return '답변 근거 연결 완료';
};

const rcaStatusLabel = (status?: string): string => {
  const normalized = String(status || '').trim().toLowerCase();
  if (normalized === 'available' || normalized === 'success' || normalized === 'ready') {
    return '연결됨';
  }
  if (normalized === 'failed' || normalized === 'error') {
    return '확인 필요';
  }
  return status || '대기';
};

const productProgressText = (value?: string): string => {
  const text = String(value || '').trim();
  if (!text) {
    return '';
  }

  const phaseMatch = text.match(/^RCA\s*문맥\s*연결\s*:\s*([a-z_]+)/i);
  if (phaseMatch) {
    return rcaContextPhaseLabel(phaseMatch[1]);
  }
  if (/^RCA\s*문맥\s*연결$/i.test(text)) {
    return '답변 근거';
  }
  if (text === 'RCA 문맥 연결 실패') {
    return '답변 근거 연결 실패';
  }
  const legacyRcaDigestText = ['RCA Context', 'digest와', ['evidence', 'refs'].join(' ')].join(
    ' ',
  );
  if (text.includes(legacyRcaDigestText)) {
    return '최종 답변에 사용한 근거를 연결했습니다.';
  }
  if (text.includes('수집/누락/실패 근거를 RCA Context로 연결')) {
    return '답변 전에 수집 근거와 추가 확인 항목을 정리했습니다.';
  }
  if (/^ev-[a-z0-9-]+\s+기록$/i.test(text)) {
    return '근거 기록 완료';
  }
  if (text === '증거 참조 기록 시작') {
    return '근거 기록 시작';
  }
  if (text === '증거 참조 기록') {
    return '근거 기록';
  }
  if (text === 'Rag Context Evidence') {
    return '문서 근거';
  }
  if (text === 'RCA Context' || text === 'RCA Evidence Context' || text === 'RCA 근거 문맥') {
    return '답변 근거';
  }
  if (text === 'Active Alerts Evidence') {
    return '경고 근거';
  }
  if (text === 'Node Status Evidence') {
    return '노드 상태 근거';
  }
  if (text === 'Restart Metric Evidence') {
    return '재시작 지표 근거';
  }
  const ragSearchMatch = text.match(/^RAG 근거\s+(\d+)건\s+검색$/);
  if (ragSearchMatch) {
    return `문서 근거 ${ragSearchMatch[1]}건 확인`;
  }

  return text
    .replace(/Node 상태 RCA 증거 수집 완료/g, '노드 상태 근거 수집 완료')
    .replace(/Active Alert RCA 증거 수집 완료/g, '경고 근거 수집 완료')
    .replace(/Restart metric RCA 증거 수집 완료/g, '재시작 지표 수집 완료')
    .replace(/Node Status Evidence 시작/g, '노드 상태 근거 확인 시작')
    .replace(/Active Alerts Evidence 시작/g, '경고 근거 확인 시작')
    .replace(/Restart Metric Evidence 시작/g, '재시작 지표 확인 시작')
    .replace(/Node 상태 근거 수집 완료/g, '노드 상태 근거 수집 완료')
    .replace(/Active Alert 근거 수집 완료/g, '경고 근거 수집 완료')
    .replace(/Restart metric 근거 수집 완료/g, '재시작 지표 수집 완료')
    .replace(/문서 근거 시작/g, '문서 근거 확인 시작')
    .replace(/Rag Context Evidence 시작/g, '문서 근거 확인 시작')
    .replace(/Rag Context Evidence/g, '문서 근거')
    .replace(/RCA Evidence Context/g, '답변 근거')
    .replace(/RCA 근거 문맥/g, '답변 근거')
    .replace(/Node Status 근거 시작/g, '노드 상태 근거 확인 시작')
    .replace(/Active Alerts 근거 시작/g, '경고 근거 확인 시작')
    .replace(/Restart Metric 근거 시작/g, '재시작 지표 확인 시작')
    .replace(/문서 Context 근거 시작/g, '문서 근거 확인 시작')
    .replace(/RCA 증거/g, '근거')
    .replace(/실행형 Tool Plan/g, '증거 수집 계획')
    .replace(/Tool Plan/g, '증거 수집 계획')
    .replace(/RCA Context/g, '답변 근거')
    .replace(/RCA\s*문맥/g, '답변 근거')
    .replace(/\bEvidence\b/g, '근거')
    .replace(/\bRag\b/g, '문서')
    .replace(/evidence\s+refs/g, '근거')
    .replace(/digest/g, '연결 정보')
    .replace(/post_answer/g, '답변 완료 후')
    .replace(/pre_answer/g, '답변 전')
    .replace(/plan_ready/g, '답변 준비');
};

const compactEvidenceTypeSummary = (refs: EvidenceFooterRef[]): string => {
  const labels = [...new Set(refs.map((ref) => evidenceTypeLabel(ref.type)).filter(Boolean))];
  if (labels.length === 0) {
    return '수집 근거 없음';
  }

  return labels.slice(0, 4).join(', ');
};

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
        <CoolCopyIcon />
      </button>
    </pre>
  );
};

const getStepActivity = (step: ProgressStep): string => {
  const summary = productProgressText(step.summary);

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
    return step.status === 'running' ? summary || '장기 실행 루프 유지 중' : '실행 루프 완료';
  }

  if (isAnswerStreamStep(step)) {
    return step.status === 'running' ? '답변을 화면에 표시하는 중입니다.' : '답변 표시 완료';
  }

  if (step.status === 'running') {
    return summary || '도구 응답을 기다리는 중입니다.';
  }

  return summary || '완료';
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

const FORMATTED_HEADING_TONE_KEYWORDS: Array<{ keywords: string[]; tone: string }> = [
  { keywords: ['재발 방지', '재발방지'], tone: 'prevention' },
  { keywords: ['후속 조치', '후속조치'], tone: 'followup' },
  { keywords: ['권장 조치', '조치 방안', '조치'], tone: 'action' },
  { keywords: ['추가 확인', '검증'], tone: 'evidence' },
  { keywords: ['원인'], tone: 'cause' },
  { keywords: ['근거'], tone: 'evidence' },
];

const formattedHeadingTone = (headingText: string): string | undefined => {
  const match = FORMATTED_HEADING_TONE_KEYWORDS.find(({ keywords }) =>
    keywords.some((keyword) => headingText.includes(keyword)),
  );
  return match?.tone;
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

  const lines = stripDefaultEvidenceAppendix(message.content).split('\n');
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
      const headingText = line.replace(/^#+\s*/, '');
      const tone = formattedHeadingTone(headingText);
      nodes.push(
        <div
          className={`komsco-ai__formatted-heading${
            tone ? ` komsco-ai__formatted-heading--${tone}` : ''
          }`}
          key={`heading-${index}`}
        >
          {renderInlineText(headingText, `heading-${index}`)}
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
    '[근거 요약]',
    `- 수집 근거: ${footer.collectedCount}건`,
    `- 추가 확인: ${footer.missingCount}건`,
  ];

  footer.collectedRefs.slice(0, 3).forEach((ref) => {
    lines.push(`- ${evidenceTypeLabel(ref.type)}: ${ref.summary || '근거 수집 완료'}`);
  });

  footer.queryPlan.slice(0, 5).forEach((step) => {
    lines.push(
      `- 조회 계획: ${evidenceTypeLabel(step.evidenceType || step.tool)} ${step.reason || '근거 수집 단계'}`,
    );
  });

  return lines.join('\n');
};

const renderEvidenceFooter = (
  footer: EvidenceFooter | undefined,
  messageContent = '',
): React.ReactNode => {
  if (!footer) {
    return null;
  }

  const collectedRefs = footer.collectedRefs.slice(0, 3);
  const missing = footer.missing.slice(0, 3);
  const queryPlan = footer.queryPlan.slice(0, 6);
  const ragAppendixRefs = extractRagAppendixRefs(messageContent);
  const evidenceSummary = compactEvidenceTypeSummary(footer.collectedRefs);

  return (
    <div
      className="komsco-ai__evidence-footer"
      data-evidence-context-id={footer.contextId || ''}
      data-evidence-digest={footer.digest || ''}
    >
      <div className="komsco-ai__evidence-footer-head">
        <span className="komsco-ai__evidence-title">근거</span>
        <span className="komsco-ai__evidence-pill komsco-ai__evidence-pill--collected">
          수집 {footer.collectedCount}건
        </span>
        {footer.missingCount > 0 && (
          <span className="komsco-ai__evidence-pill komsco-ai__evidence-pill--missing">
            추가 확인 {footer.missingCount}건
          </span>
        )}
        <span className="komsco-ai__evidence-summary">{evidenceSummary}</span>
      </div>

      {(collectedRefs.length > 0 || missing.length > 0 || queryPlan.length > 0 || ragAppendixRefs.length > 0) && (
        <details className="komsco-ai__evidence-detail">
          <summary>
            <span>근거 상세보기</span>
          </summary>
          {ragAppendixRefs.length > 0 && (
            <div className="komsco-ai__rag-source-list" aria-label="문서 근거">
              <strong>문서 근거</strong>
              {ragAppendixRefs.map((ref, index) => (
                <div className="komsco-ai__rag-source-item" key={`${ref.title}-${index}`}>
                  <span>{ref.title}</span>
                  {ref.sourceUri && <code>{ref.sourceUri}</code>}
                </div>
              ))}
            </div>
          )}

          {collectedRefs.length > 0 && (
            <div className="komsco-ai__evidence-list" aria-label="수집된 답변 근거">
              {collectedRefs.map((ref, index) => (
                <div
                  className="komsco-ai__evidence-ref"
                  key={`${ref.evidenceId || ref.type || 'ref'}-${index}`}
                >
                  <strong>{evidenceTypeLabel(ref.type)}</strong>
                  <span>{ref.summary || ref.sourceType || '근거 수집 완료'}</span>
                </div>
              ))}
            </div>
          )}

          {missing.length > 0 && (
            <div className="komsco-ai__evidence-missing" aria-label="추가 확인 필요 근거">
              {missing.map((item, index) => (
                <span key={`${item.type || 'missing'}-${index}`}>
                  {evidenceTypeLabel(item.type)}: {item.reason || '추가 확인 필요'}
                </span>
              ))}
            </div>
          )}

          <ol className="komsco-ai__evidence-query-plan" aria-label="조회 계획">
            {queryPlan.map((step, index) => (
              <li key={`${step.step || index}-${step.tool || 'tool'}`}>
                <strong>{evidenceTypeLabel(step.evidenceType || step.tool)}</strong>
                <span>{step.reason || '근거 수집 단계'}</span>
                <code>{evidenceStepStatusLabel(step.status)}</code>
              </li>
            ))}
          </ol>
        </details>
      )}
    </div>
  );
};

const isReadOnlyExecutionPolicy = (mode?: string): boolean => mode === 'evidence_check';

const executionPolicyLabel = (mode?: string): string => {
  if (mode === 'evidence_check') {
    return '조회 전용';
  }
  if (mode === 'unrestricted') {
    return '실행 무제한';
  }
  if (mode === 'controlled_execution') {
    return '승인 후 실행';
  }
  return mode || '알 수 없음';
};

const renderToolPlanFooter = (toolPlan: ToolPlanFooter | undefined): React.ReactNode => {
  if (!toolPlan || toolPlan.steps.length === 0) {
    return null;
  }

  const steps = toolPlan.steps.slice(0, 6);
  const missingEvidence = toolPlan.missingEvidence.slice(0, 3);
  const readOnly = isReadOnlyExecutionPolicy(toolPlan.executionPolicyMode);
  const targetLabel = [toolPlan.targetResourceKind, toolPlan.targetResourceName]
    .filter(Boolean)
    .join(' ');

  return (
    <div className="komsco-ai__toolplan-footer">
      <div className="komsco-ai__toolplan-footer-head">
        <span className="komsco-ai__evidence-title">조회 계획</span>
        <span className="komsco-ai__evidence-pill komsco-ai__evidence-pill--collected">
          {toolPlan.taskType}
        </span>
        <span
          className={`komsco-ai__evidence-pill ${
            readOnly
              ? 'komsco-ai__evidence-pill--collected'
              : 'komsco-ai__evidence-pill--policy-warning'
          }`}
        >
          {executionPolicyLabel(toolPlan.executionPolicyMode)}
        </span>
        {toolPlan.validationOk === false && (
          <span className="komsco-ai__evidence-pill komsco-ai__evidence-pill--missing">
            계획 검증 실패
          </span>
        )}
      </div>

      <details className="komsco-ai__evidence-detail">
        <summary>
          <span>조회 계획 상세보기</span>
        </summary>
        {targetLabel && (
          <div className="komsco-ai__toolplan-target">
            대상: {targetLabel}
            {toolPlan.targetNamespace ? ` (${toolPlan.targetNamespace})` : ''}
          </div>
        )}
        <ol className="komsco-ai__evidence-query-plan" aria-label="조회 계획 단계">
          {steps.map((step, index) => (
            <li key={`${step.step || index}-${step.tool || 'tool'}`}>
              <strong>{evidenceTypeLabel(step.evidenceType || step.tool)}</strong>
              <span>{step.reason || '조회 단계'}</span>
              <code>{step.verb || step.tool}</code>
            </li>
          ))}
        </ol>
        {missingEvidence.length > 0 && (
          <div className="komsco-ai__evidence-missing" aria-label="추가 확인 필요 근거">
            {missingEvidence.map((item, index) => (
              <span key={`${item.type || 'missing'}-${index}`}>
                {evidenceTypeLabel(item.type)}: {item.reason || '추가 확인 필요'}
              </span>
            ))}
          </div>
        )}
        {toolPlan.validationViolations.length > 0 && (
          <div className="komsco-ai__toolplan-violations" aria-label="계획 검증 문제">
            {toolPlan.validationViolations.map((violation, index) => (
              <span key={`violation-${index}`}>{violation}</span>
            ))}
          </div>
        )}
      </details>
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
    return `${formatDuration(elapsedMs)} 동안 작업 중`;
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

const getCurrentProgressStep = (steps: ProgressStep[]): ProgressStep =>
  steps.find((step) => step.status === 'running') ?? steps[steps.length - 1];

const ProgressTimeline: React.FC<{ active: boolean; steps: ProgressStep[] }> = ({
  active,
  steps,
}) => {
  const displaySteps = getDisplaySteps(steps);

  if (displaySteps.length === 0) {
    return null;
  }

  const currentStep = getCurrentProgressStep(displaySteps);

  return (
    <div className="komsco-ai__progress-wrap">
      <details className="komsco-ai__progress" key={active ? 'active' : 'complete'}>
        <summary className="komsco-ai__progress-summary" aria-live="polite">
          <span
            className={`komsco-ai__flow-pulse komsco-ai__flow-pulse--${currentStep.status}`}
            aria-hidden="true"
          />
          <span className="komsco-ai__progress-activity">{getStepActivity(currentStep)}</span>
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
                  <span className="komsco-ai__progress-step-title">
                    {productProgressText(step.title)}
                  </span>
                  <span className="komsco-ai__progress-step-separator" aria-hidden="true">
                    ·
                  </span>
                  <span className="komsco-ai__progress-step-activity">
                    {getStepActivity(step)}
                  </span>
                </span>
                <span className="komsco-ai__progress-step-meta">{getStepElapsed(step)}</span>
              </div>
            );
          })}
        </div>
      </details>
    </div>
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

const cpuCoresFromUsage = (value?: string): number | null => {
  if (!value) {
    return null;
  }

  const match = value.trim().match(/^(\d+(?:\.\d+)?)([a-zA-Z]*)$/);
  if (!match) {
    return null;
  }

  const amount = Number(match[1]);
  if (!Number.isFinite(amount)) {
    return null;
  }

  const unit = match[2];
  if (unit === 'n') {
    return amount / 1_000_000_000;
  }
  if (unit === 'u') {
    return amount / 1_000_000;
  }
  if (unit === 'm') {
    return amount / 1_000;
  }

  return amount;
};

const memoryBytesFromUsage = (value?: string): number | null => {
  if (!value) {
    return null;
  }

  const match = value.trim().match(/^(\d+(?:\.\d+)?)([a-zA-Z]*)$/);
  if (!match) {
    return null;
  }

  const amount = Number(match[1]);
  if (!Number.isFinite(amount)) {
    return null;
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

  return multiplier ? amount * multiplier : null;
};

const formatCpuCores = (cores: number): string =>
  cores >= 1
    ? `${cores.toFixed(cores >= 10 ? 0 : 1)} cores`
    : `${Math.max(1, Math.round(cores * 1000))} m`;

const formatMemoryBytes = (bytes: number): string => {
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

const getClusterUsageSummary = (summary: ClusterSummary): string => {
  const cpuTotal = summary.nodes.items.reduce((total, node) => {
    const cores = cpuCoresFromUsage(node.usage.cpu);
    return cores === null ? total : total + cores;
  }, 0);
  const memoryTotal = summary.nodes.items.reduce((total, node) => {
    const bytes = memoryBytesFromUsage(node.usage.memory);
    return bytes === null ? total : total + bytes;
  }, 0);

  if (!summary.nodes.metricsAvailable) {
    return 'Metrics API unavailable';
  }

  if (cpuTotal <= 0 && memoryTotal <= 0) {
    return 'Metrics connected, usage pending';
  }

  return `CPU ${cpuTotal > 0 ? formatCpuCores(cpuTotal) : '-'} · 메모리 ${
    memoryTotal > 0 ? formatMemoryBytes(memoryTotal) : '-'
  }`;
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

const getNodeCompactStatus = (
  summary: ClusterSummary | null,
  loading: boolean,
  error: string,
): {
  label: string;
  title: string;
  tone: 'ok' | 'warn' | 'danger' | 'review' | 'neutral';
} => {
  if (summary) {
    const label = `Node ${summary.nodes.ready}/${summary.nodes.total}`;
    if (summary.nodes.notReady > 0) {
      return {
        label: `${label} 확인 필요`,
        title: `${summary.nodes.notReady} node(s) are not ready.`,
        tone: 'danger',
      };
    }

    if (summary.nodes.total > 0 && summary.nodes.ready === summary.nodes.total) {
      return {
        label: `${label} · Ready`,
        title: 'All reported nodes are Ready.',
        tone: 'ok',
      };
    }

    return {
      label: `${label} 부분 확인`,
      title: 'Node readiness is partially available.',
      tone: 'warn',
    };
  }

  if (error) {
    return {
      label: 'Node 확인 필요',
      title: error,
      tone: 'danger',
    };
  }

  return {
    label: loading ? 'Node 수집 중' : 'Node 대기',
    title: 'Cluster node summary is not available yet.',
    tone: 'neutral',
  };
};

const getOperatorCompactStatus = (
  summary: ClusterSummary | null,
  loading: boolean,
  error: string,
): {
  label: string;
  title: string;
  tone: 'ok' | 'warn' | 'danger' | 'review' | 'neutral';
} => {
  if (summary) {
    const faultCount = getClusterFaultCount(summary);
    if (faultCount > 0) {
      return {
        label: `Operator ${faultCount}건 확인`,
        title: `${faultCount} degraded/unavailable operator issue(s) need attention.`,
        tone: 'danger',
      };
    }

    if (summary.operators.progressing > 0) {
      return {
        label: `Operator ${summary.operators.progressing}건 진행`,
        title: `${summary.operators.progressing} operator(s) are progressing.`,
        tone: 'warn',
      };
    }

    if (summary.operators.total > 0 && summary.operators.available === summary.operators.total) {
      return {
        label: `Operator ${summary.operators.available}/${summary.operators.total} 정상`,
        title: `All ${summary.operators.total} ClusterOperators are available.`,
        tone: 'ok',
      };
    }

    return {
      label: `Operator ${summary.operators.available}/${summary.operators.total} 확인`,
      title: 'ClusterOperator summary is partially available.',
      tone: 'warn',
    };
  }

  if (error) {
    return {
      label: 'Operator 확인 필요',
      title: error,
      tone: 'danger',
    };
  }

  return {
    label: loading ? 'Operator 수집 중' : 'Operator 대기',
    title: 'ClusterOperator summary is not available yet.',
    tone: 'neutral',
  };
};

const renderStatusTag = (
  label: string,
  tone: 'ok' | 'warn' | 'danger' | 'review' | 'neutral' = 'neutral',
  title?: string,
  icon?: React.ReactNode,
) => (
  <span className={`komsco-ai__scope-tag komsco-ai__scope-tag--${tone}`} title={title}>
    {icon && <span className="komsco-ai__scope-tag-icon">{icon}</span>}
    {label}
  </span>
);

const renderHeaderOpsChip = (
  label: string,
  tone: 'ok' | 'warn' | 'danger' | 'review' | 'neutral',
  title: string,
  icon: React.ReactNode,
) => (
  <span className={`komsco-ai__header-op-chip komsco-ai__header-op-chip--${tone}`} title={title}>
    <span className="komsco-ai__header-op-icon">{icon}</span>
    <span>{label}</span>
  </span>
);

const renderHeaderOpsStatus = (summary: ClusterSummary | null, loading: boolean, error: string) => {
  const nodeStatus = getNodeCompactStatus(summary, loading, error);
  const operatorStatus = getOperatorCompactStatus(summary, loading, error);

  const headerNodeLabel = nodeStatus.label
    .replace(' · Ready', '')
    .replace(' 부분 확인', '')
    .replace(' 확인 필요', '');
  const headerOperatorLabel =
    summary && getClusterFaultCount(summary) > 0
      ? `Operator 장애 ${getClusterFaultCount(summary)}`
      : summary && summary.operators.progressing > 0
        ? `Operator 진행 ${summary.operators.progressing}`
        : summary &&
            summary.operators.total > 0 &&
            summary.operators.available === summary.operators.total
          ? 'Operator 정상'
          : operatorStatus.label.replace(' 확인 필요', ' 확인');

  return (
    <div className="komsco-ai__header-ops" aria-label="클러스터 운영 상태">
      {renderHeaderOpsChip(
        headerNodeLabel,
        nodeStatus.tone,
        nodeStatus.title,
        <CoolDesktopTowerIcon />,
      )}
      {renderHeaderOpsChip(
        headerOperatorLabel,
        operatorStatus.tone,
        operatorStatus.title,
        operatorStatus.tone === 'ok' ? <CoolCheckIcon /> : <CoolListChecklistIcon />,
      )}
    </div>
  );
};

const renderRailSummaryBadges = (
  summary: ClusterSummary | null,
  loading: boolean,
  error: string,
) => {
  const nodeStatus = getNodeCompactStatus(summary, loading, error);
  const operatorStatus = getOperatorCompactStatus(summary, loading, error);

  return (
    <div className="komsco-ai__rail-status-pair" aria-label="클러스터 핵심 상태">
      {renderStatusTag(
        nodeStatus.label,
        nodeStatus.tone,
        nodeStatus.title,
        <CoolDesktopTowerIcon />,
      )}
      {renderStatusTag(
        operatorStatus.label,
        operatorStatus.tone,
        operatorStatus.title,
        <CoolWarningIcon />,
      )}
    </div>
  );
};

const canUseActionExecution = (status: AiopsRuntimeStatus | null): boolean =>
  Boolean(
    status?.spec.capabilities.mutationsEnabled && status.spec.capabilities.actionExecutorConfigured,
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
    : 'unrestricted command gate not reported by runtime';
};

const executionModeAllowsActions = (mode: AiopsExecutionMode): boolean =>
  mode === 'execute' || mode === 'unrestricted';

const getExecutionModeShortLabel = (mode: AiopsExecutionMode): string => {
  if (mode === 'unrestricted') {
    return '무제한';
  }
  if (mode === 'execute') {
    return '실행';
  }
  return '읽기';
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
      title="조회와 근거 수집만 수행하고 조치 계획, 승인, 실행은 만들지 않습니다."
      type="button"
    >
      <CoolShieldCheckIcon />
      <span>읽기 전용</span>
    </button>
    <button
      aria-label="승인 후 실행 모드"
      aria-pressed={executionMode === 'execute'}
      className={`komsco-ai__mode-toggle-button${
        executionMode === 'execute' ? ' komsco-ai__mode-toggle-button--active-execute' : ''
      }`}
      data-disabled-reason={!actionExecutionAvailable ? actionExecutionDisabledReason : undefined}
      onClick={() => onExecutionModeChange('execute')}
      title={
        actionExecutionAvailable
          ? '승인 후 실행 모드'
          : `승인 후 실행 비활성: ${actionExecutionDisabledReason}`
      }
      type="button"
    >
      <CoolTerminalIcon />
      <span>실행 가능</span>
    </button>
    <button
      aria-label="실험 무제한 모드"
      aria-pressed={executionMode === 'unrestricted'}
      className={`komsco-ai__mode-toggle-button${
        executionMode === 'unrestricted' ? ' komsco-ai__mode-toggle-button--active-danger' : ''
      }`}
      onClick={() => onExecutionModeChange('unrestricted')}
      title="실험 무제한 모드"
      type="button"
    >
      <CoolInfoIcon />
      <span>실행 무제한</span>
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
type AiopsActionStep = 'create-plan' | 'approve-plan' | 'reject-plan' | 'execute-approval';
type AiopsLifecycleStage = 'proposal' | 'plan' | 'approval' | 'execution';
type UiTone = 'ok' | 'warn' | 'danger' | 'review' | 'neutral';

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

    return decision?.planDigest === planDigest && ['approved', 'executed', 'rejected'].includes(status);
  });

const hasExecutionForApproval = (executions: AiopsRecordView[], approvalId: string): boolean =>
  executions.some((record) => getRecordSpecMap(record).approvalId === approvalId);

const findExecutionForApproval = (
  executions: AiopsRecordView[],
  approvalId: string,
): AiopsRecordView | undefined =>
  executions.find((record) => getRecordSpecMap(record).approvalId === approvalId);

interface ExecutionOutcomeSummary {
  tone: 'ok' | 'warn' | 'danger';
  title: string;
  detail: string;
}

// evict_one_unhealthy_controller_owned_pod verification only checks the
// target immediately after the mutation call, before the controller has
// necessarily finished recreating the pod yet — so a fresh "여전히 존재" read
// is expected transient noise, not a real failure signal, for the first
// few seconds after execution.
const REMEDIATION_REASON_LABEL_KO: Record<string, string> = {
  target_pod_removed: '대상 Pod가 클러스터에서 제거되었습니다.',
  target_pod_deleting: '대상 Pod가 종료 처리 중입니다. 컨트롤러가 곧 새로 만듭니다.',
  target_pod_replaced: '컨트롤러가 대상 Pod를 새로 재생성했습니다.',
  target_pod_still_present:
    '조치를 실행했지만 대상 Pod가 아직 그대로입니다. 잠시 후 다시 확인해 주세요.',
  restart_annotation_observed: '배포에 재시작 요청이 반영되었습니다.',
  restart_annotation_not_observed: '재시작 반영이 아직 확인되지 않았습니다.',
  scale_spec_matches: '레플리카 수 변경이 반영되었습니다.',
  scale_spec_mismatch: '레플리카 수 변경이 아직 반영되지 않았습니다.',
  rollback_template_annotation_observed: '이전 리비전으로 롤백이 반영되었습니다.',
  rollback_annotation_not_observed: '롤백 반영이 아직 확인되지 않았습니다.',
  hpa_bounds_match: 'HPA 범위 변경이 반영되었습니다.',
  hpa_bounds_mismatch: 'HPA 범위 변경이 아직 반영되지 않았습니다.',
  no_postcondition_for_tool:
    '조치는 실행되었지만 이 조치 유형은 자동 확인을 지원하지 않습니다. 클러스터에서 직접 확인해 주세요.',
  target_resource_unavailable: '대상 리소스를 다시 조회하지 못해 결과를 확인하지 못했습니다.',
};

const getExecutionOutcomeSummary = (
  record: AiopsRecordView,
  aiopsStatus: AiopsRuntimeStatus | null,
): ExecutionOutcomeSummary | null => {
  const decision = getApprovalDecision(record);
  if (!decision) {
    return null;
  }

  const approvalId = getApprovalId(record);
  const executions = aiopsStatus?.spec.records.executionRecords ?? [];
  const execution = findExecutionForApproval(executions, approvalId);
  if (!execution) {
    return null;
  }

  const isAutoPolicy = decision.decidedBy === 'auto-policy';
  const decisionAction = asObjectMap(decision.action);
  const toolName = typeof decisionAction?.toolName === 'string' ? decisionAction.toolName : '';
  const executionSpec = getRecordSpecMap(execution);
  const mutationOutcome = asObjectMap(executionSpec.mutationOutcome);
  const remediationOutcome = asObjectMap(executionSpec.remediationOutcome);
  const mutationStatus = typeof mutationOutcome?.status === 'string' ? mutationOutcome.status : '';
  const remediationStatus =
    typeof remediationOutcome?.status === 'string' ? remediationOutcome.status : '';
  const remediationReason =
    typeof remediationOutcome?.reason === 'string' ? remediationOutcome.reason : '';

  const title = isAutoPolicy
    ? toolName
      ? `자동으로 조치를 실행했습니다 (정책: ${toolName})`
      : '자동으로 조치를 실행했습니다.'
    : '조치를 실행했습니다.';

  if (mutationStatus === 'mutation_failed') {
    return {
      tone: 'danger',
      title,
      detail: '실행 요청이 실패했습니다. 다시 시도하거나 직접 확인해 주세요.',
    };
  }
  if (mutationStatus === 'mutation_disabled') {
    return {
      tone: 'warn',
      title,
      detail: '실행 기능이 비활성화되어 있어 실제 클러스터에는 반영되지 않았습니다.',
    };
  }

  if (remediationStatus === 'verified') {
    return {
      tone: 'ok',
      title,
      detail: REMEDIATION_REASON_LABEL_KO[remediationReason] || '문제 해결이 확인되었습니다.',
    };
  }
  if (remediationStatus === 'verification_failed') {
    return {
      tone: 'warn',
      title,
      detail:
        REMEDIATION_REASON_LABEL_KO[remediationReason] ||
        '실행은 됐지만 해결 여부가 아직 확인되지 않았습니다.',
    };
  }

  return {
    tone: 'warn',
    title,
    detail:
      REMEDIATION_REASON_LABEL_KO[remediationReason] ||
      '실행은 됐지만 이 조치 유형은 자동 확인을 지원하지 않습니다. 클러스터에서 직접 확인해 주세요.',
  };
};

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

const getActionRecordStage = (record: AiopsRecordView): AiopsLifecycleStage => {
  const spec = getRecordSpecMap(record);
  const kind = record.kind ?? '';
  if (kind === 'ExecutionRecord' || spec.mutationOutcome || spec.approvalId) {
    return 'execution';
  }
  if (kind === 'ApprovalDecisionRecord' || spec.approvalDecision) {
    return 'approval';
  }
  if (kind === 'SealedActionPlanRecord' || spec.sealedActionPlan) {
    return 'plan';
  }
  return 'proposal';
};

const getActionRecordStageLabel = (record: AiopsRecordView): string => {
  const stage = getActionRecordStage(record);
  if (stage === 'execution') {
    return 'Execution record';
  }
  if (stage === 'approval') {
    return 'Approval decision';
  }
  if (stage === 'plan') {
    return 'Sealed plan';
  }
  return 'Proposal';
};

const getActionRecordProof = (record: AiopsRecordView): string => {
  const spec = getRecordSpecMap(record);
  const planDigest = getPlanDigest(record);
  const approvalPlanDigest = getApprovalPlanDigest(record);
  const approvalId = getApprovalId(record);

  if (planDigest) {
    return `sealed plan digest ${shortDigest(planDigest)}`;
  }
  if (approvalPlanDigest) {
    const decision = getApprovalDecision(record);
    const status = String(decision?.status ?? 'unknown');
    const approvalLabel = status === 'approved' ? 'active approval' : `${status} approval`;
    return `${approvalLabel} ${shortDigest(approvalId)} · plan digest ${shortDigest(approvalPlanDigest)}`;
  }
  if (typeof spec.approvalId === 'string') {
    return `execution record · approval ${shortDigest(spec.approvalId)}`;
  }
  return 'proposal waits for a sealed plan before approval';
};

const getActionLifecycleSteps = (status: AiopsRuntimeStatus | null) => {
  const records = status?.spec.records;

  return [
    {
      count: records?.actionProposals.length ?? 0,
      detail: 'candidate action request',
      key: 'proposal',
      label: 'Proposal',
    },
    {
      count: records?.sealedActionPlans.length ?? 0,
      detail: 'sealed plan digest',
      key: 'plan',
      label: 'Sealed plan',
    },
    {
      count: records?.approvalDecisions.length ?? 0,
      detail: 'approval decision',
      key: 'approval',
      label: 'Approval',
    },
    {
      count: records?.executionRecords.length ?? 0,
      detail: 'execution record',
      key: 'execution',
      label: 'Execution',
    },
  ] as Array<{
    count: number;
    detail: string;
    key: AiopsLifecycleStage;
    label: string;
  }>;
};

const getActionLifecycleSummary = (
  status: AiopsRuntimeStatus | null,
  executionMode: AiopsExecutionMode,
) => {
  if (!status) {
    return {
      label: 'Runtime status',
      text: 'AIOps runtime status loading; execution disabled until status resolves.',
      tone: 'neutral' as UiTone,
      value: 'pending',
    };
  }

  const actionExecutorConfigured = Boolean(status?.spec.capabilities.actionExecutorConfigured);
  const mutationsEnabled = Boolean(status?.spec.capabilities.mutationsEnabled);
  const actionsAllowed = canUseActionExecution(status) && executionModeAllowsActions(executionMode);
  const blockers: string[] = [];
  if (!actionExecutorConfigured) {
    blockers.push('Action Executor URL not configured');
  }
  if (!mutationsEnabled) {
    blockers.push('Mutation gate disabled: approval execution cannot submit changes yet');
  }
  if (!executionModeAllowsActions(executionMode)) {
    blockers.push('UI mode blocks proposal, approval, and execution mutations');
  }

  if (blockers.length === 0 && actionsAllowed) {
    return {
      label: 'Current gate',
      text: 'Plan, approval, and execution requests may be submitted after server-side checks.',
      tone: 'review' as UiTone,
      value: getExecutionModeShortLabel(executionMode),
    };
  }

  return {
    label: 'Current blocker',
    text: blockers.join('; '),
    tone: 'warn' as UiTone,
    value: 'not configured',
  };
};

const renderExecutionCapabilityBadges = (
  status: AiopsRuntimeStatus | null,
  executionMode: AiopsExecutionMode,
) => {
  const actionExecutionAvailable = canUseActionExecution(status);
  const unrestrictedAvailable = canUseUnrestrictedCommands(status);
  const readOnlyActive = executionMode === 'read-only';
  const executeActive = executionMode === 'execute';
  const unrestrictedActive = executionMode === 'unrestricted';

  return (
    <div className="komsco-ai__scope-list komsco-ai__scope-list--execution">
      {renderStatusTag(
        '읽기 전용',
        readOnlyActive ? 'ok' : 'neutral',
        '조회와 근거 수집만 수행하고 조치 계획, 승인, 실행은 만들지 않습니다.',
        <CoolShieldCheckIcon />,
      )}
      {renderStatusTag(
        '승인 실행',
        actionExecutionAvailable ? (executeActive ? 'review' : 'ok') : 'warn',
        actionExecutionAvailable
          ? 'Action Executor가 연결되어 승인된 실행 요청을 보낼 수 있습니다.'
          : getActionExecutionDisabledReason(status),
        <CoolTerminalIcon />,
      )}
      {renderStatusTag(
        '실행 무제한',
        unrestrictedActive ? 'danger' : unrestrictedAvailable ? 'review' : 'neutral',
        unrestrictedActive
          ? unrestrictedAvailable
            ? '로컬 실험 모드에서 제한 없는 명령 실행이 허용됩니다.'
            : '실행 무제한 모드가 선택되었습니다. Gateway capability가 OFF이면 실행 시 서버가 거절 사유를 반환합니다.'
          : unrestrictedAvailable
            ? '로컬 실험 모드에서 제한 없는 명령 실행이 허용됩니다.'
            : getUnrestrictedDisabledReason(status),
        <CoolInfoIcon />,
      )}
    </div>
  );
};

const renderActionLifecycle = (
  aiopsStatus: AiopsRuntimeStatus | null,
  executionMode: AiopsExecutionMode,
) => {
  const summary = getActionLifecycleSummary(aiopsStatus, executionMode);
  const actionExecutorState = !aiopsStatus
    ? 'pending'
    : aiopsStatus.spec.capabilities.actionExecutorConfigured
      ? 'configured'
      : 'not-configured';
  const mutationFlagState = !aiopsStatus
    ? 'pending'
    : aiopsStatus.spec.capabilities.mutationsEnabled
      ? 'enabled'
      : 'disabled';

  return (
    <div
      className="komsco-ai__action-lifecycle"
      data-action-executor-state={actionExecutorState}
      data-execute-guard="sealed-plan-digest active-approval evidence-freshness ssar mutation-flag"
      data-komsco-action-lifecycle
      data-mutation-flag-state={mutationFlagState}
      data-ui-execution-mode={executionMode}
    >
      <div className="komsco-ai__action-lifecycle-steps" aria-label="AIOps action lifecycle">
        {getActionLifecycleSteps(aiopsStatus).map((step) => (
          <div
            className={`komsco-ai__action-lifecycle-step${
              step.count > 0 ? ' komsco-ai__action-lifecycle-step--active' : ''
            }`}
            data-action-lifecycle-step={step.key}
            key={step.key}
          >
            <span>{step.label}</span>
            <strong>{step.count}</strong>
            <small>{step.detail}</small>
          </div>
        ))}
      </div>
      <div className="komsco-ai__action-lifecycle-summary">
        <div className="komsco-ai__action-lifecycle-current">
          <div>
            <strong>{summary.label}</strong>
            <p>{summary.text}</p>
          </div>
          {renderStatusTag(summary.value, summary.tone)}
        </div>
        <p className="komsco-ai__action-lifecycle-proof">
          Execute guard: sealed plan digest, active approval, evidence freshness, SSAR, and mutation
          flag are checked. Expired or stale evidence blocks execution and is surfaced as a failure
          reason; create a new plan and approval.
        </p>
      </div>
    </div>
  );
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
      ? '읽기 전용 모드에서는 승인·실행 불가'
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

const renderUploadedDocumentRows = (
  documents: RagUploadedDocument[],
  emptyText: string,
): React.ReactNode => {
  if (documents.length === 0) {
    return <div className="komsco-ai__history-empty">{emptyText}</div>;
  }

  return documents.map((document) => (
    <div
      className="komsco-ai__uploaded-doc-item"
      key={document.documentId}
      title={document.sourceUri || document.title}
    >
      <div className="komsco-ai__uploaded-doc-title">{document.title}</div>
      <div className="komsco-ai__uploaded-doc-meta">
        <span>{document.chunkCount ?? 0} chunks</span>
        <span>{formatFileSize(document.contentBytes ?? 0)}</span>
      </div>
      <div className="komsco-ai__uploaded-doc-source">
        {document.sourceUri || document.documentId}
      </div>
    </div>
  ));
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
    const actions =
      action?.step === 'approve-plan'
        ? [action, { ...action, label: '거절', step: 'reject-plan' as const }]
        : action
          ? [action]
          : [];

    return (
      <div
        className="komsco-ai__rail-command"
        data-action-lifecycle-stage={getActionRecordStage(record)}
        key={record.metadata?.name ?? phase}
      >
        <div className="komsco-ai__rail-command-head">
          <div className="komsco-ai__rail-command-title">
            <span>{getActionRecordStageLabel(record)}</span>
            <code>{record.metadata?.name ?? record.kind ?? 'record'}</code>
          </div>
          {renderStatusTag(phase, getPhaseTone(phase))}
        </div>
        <p>{getRecordTargetLabel(record)}</p>
        <p className="komsco-ai__rail-action-proof">{getActionRecordProof(record)}</p>
        {actions.length > 0 && (
          <div className="komsco-ai__rail-action-row">
            {actions.map((item) => {
              const actionId = `${item.step}:${getRecordName(record)}`;
              const busy = actionId === busyActionId;
              return (
                <Button
                  className="komsco-ai__rail-action-button"
                  isDisabled={busy || Boolean(item.disabledReason)}
                  isLoading={busy}
                  key={item.step}
                  onClick={() => onAction(record, item)}
                  size="sm"
                  title={item.disabledReason}
                  variant={item.step === 'reject-plan' ? 'link' : 'secondary'}
                >
                  <span className="komsco-ai__rail-action-icon">
                    <CoolTerminalIcon />
                  </span>
                  {item.label}
                </Button>
              );
            })}
            {action?.disabledReason && (
              <span className="komsco-ai__rail-action-note">{action.disabledReason}</span>
            )}
          </div>
        )}
      </div>
    );
  });
};

const matchActionCandidatesForMessage = (
  content: string,
  candidates: AiopsActionCandidate[],
): AiopsActionCandidate[] =>
  candidates.filter((candidate) => {
    const name = candidate.target?.name;
    return Boolean(name) && content.includes(name!);
  });

const actionCandidateButtonLabel = (candidate: AiopsActionCandidate): string => {
  const kind = candidate.target?.kind ? `${candidate.target.kind} ` : '';
  const name = candidate.target?.name ?? candidate.title;
  return `조치 계획 생성: ${kind}${name}`;
};

const latestAnswerActionRecords = (
  aiopsStatus: AiopsRuntimeStatus | null,
  executionMode: AiopsExecutionMode,
): AiopsRecordView[] => {
  const records = aiopsStatus?.spec.records;
  if (!records) {
    return [];
  }

  return [
    ...records.approvalDecisions,
    ...records.sealedActionPlans,
    ...records.actionProposals,
  ]
    .filter(
      (record) =>
        Boolean(getAiopsRecordAction(record, aiopsStatus, executionMode)) ||
        Boolean(getExecutionOutcomeSummary(record, aiopsStatus)),
    )
    .sort(
      (a, b) =>
        new Date(String(b.metadata?.createdAt ?? 0)).getTime() -
        new Date(String(a.metadata?.createdAt ?? 0)).getTime(),
    )
    .slice(0, 3);
};

const renderCreateActionPlanButtons = (
  candidates: AiopsActionCandidate[],
  busyCandidateId: string,
  onCreatePlan: (candidate: AiopsActionCandidate) => void,
): React.ReactNode => {
  if (candidates.length === 0) {
    return null;
  }

  return (
    <div className="komsco-ai__create-action-plan">
      {candidates.map((candidate) => {
        const busy = candidate.id === busyCandidateId;
        return (
          <Button
            isDisabled={busy}
            isLoading={busy}
            key={candidate.id}
            onClick={() => onCreatePlan(candidate)}
            size="sm"
            variant="secondary"
          >
            {actionCandidateButtonLabel(candidate)}
          </Button>
        );
      })}
    </div>
  );
};

const renderAssistantAnswerActions = (
  records: AiopsRecordView[],
  aiopsStatus: AiopsRuntimeStatus | null,
  executionMode: AiopsExecutionMode,
  busyActionId: string,
  onAction: (record: AiopsRecordView, action: AiopsRecordAction) => void,
) => {
  if (records.length === 0) {
    return null;
  }

  return (
    <div
      className="komsco-ai__answer-actions"
      data-komsco-answer-action-buttons
      aria-label="챗봇 답변 직접 조치 버튼"
    >
      <div className="komsco-ai__answer-actions-head">
        <strong>바로 해결</strong>
        <span>검증된 AIOps 기록에서 다음 버튼만 표시합니다.</span>
      </div>
      <div className="komsco-ai__answer-action-list">
        {records.map((record) => {
          const action = getAiopsRecordAction(record, aiopsStatus, executionMode);
          const actions =
            action?.step === 'approve-plan'
              ? [action, { ...action, label: '거절', step: 'reject-plan' as const }]
              : action
                ? [action]
                : [];

          const phase = getRecordPhase(record);

          if (actions.length === 0) {
            const outcome = getExecutionOutcomeSummary(record, aiopsStatus);
            if (!outcome) {
              return null;
            }
            const outcomeIcon = outcome.tone === 'ok' ? '✓' : outcome.tone === 'warn' ? '!' : '✕';

            return (
              <div
                className={`komsco-ai__answer-action-card komsco-ai__answer-action-card--${outcome.tone}`}
                data-action-lifecycle-stage={getActionRecordStage(record)}
                key={getRecordName(record) || phase}
              >
                <div className="komsco-ai__answer-action-main">
                  <span>{getActionRecordStageLabel(record)}</span>
                  <strong>{getRecordTargetLabel(record)}</strong>
                </div>
                <div className="komsco-ai__answer-action-outcome">
                  <div className="komsco-ai__answer-action-outcome-title">
                    <span className="komsco-ai__answer-action-outcome-icon">{outcomeIcon}</span>
                    {outcome.title}
                  </div>
                  <div className="komsco-ai__answer-action-outcome-detail">{outcome.detail}</div>
                </div>
              </div>
            );
          }

          return (
            <div
              className="komsco-ai__answer-action-card"
              data-action-lifecycle-stage={getActionRecordStage(record)}
              key={getRecordName(record) || phase}
            >
              <div className="komsco-ai__answer-action-main">
                <span>{getActionRecordStageLabel(record)}</span>
                <strong>{getRecordTargetLabel(record)}</strong>
                <small>{getActionRecordProof(record)}</small>
              </div>
              <div className="komsco-ai__answer-action-controls">
                {actions.map((item) => {
                  const actionId = `${item.step}:${getRecordName(record)}`;
                  const busy = actionId === busyActionId;
                  return (
                    <Button
                      className="komsco-ai__answer-action-button"
                      data-answer-action-step={item.step}
                      isDisabled={busy || Boolean(item.disabledReason)}
                      isLoading={busy}
                      key={item.step}
                      onClick={() => onAction(record, item)}
                      size="sm"
                      title={item.disabledReason}
                      variant={item.step === 'reject-plan' ? 'link' : 'secondary'}
                    >
                      <span className="komsco-ai__rail-action-icon">
                        <CoolTerminalIcon />
                      </span>
                      {item.label}
                    </Button>
                  );
                })}
              </div>
              {action?.disabledReason && (
                <div className="komsco-ai__answer-action-note">{action.disabledReason}</div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

const messagePreview = (content: string, limit = 110): string => {
  const collapsed = content.replace(/\s+/g, ' ').trim();
  if (!collapsed) {
    return '내용 없음';
  }

  return collapsed.length > limit ? `${collapsed.slice(0, limit - 1)}...` : collapsed;
};

const messageTime = (timestamp: number | undefined, language: UiLanguage): string => {
  if (!timestamp) {
    return '시간 대기';
  }

  return new Date(timestamp).toLocaleTimeString(languageLocale(language), {
    hour: '2-digit',
    minute: '2-digit',
  });
};

const conversationMessages = (messages: Message[]): Message[] =>
  messages.filter((message) => message.role === 'user' || message.role === 'assistant');

const latestMessageByRole = (
  messages: Message[],
  role: 'user' | 'assistant',
): Message | undefined =>
  [...messages].reverse().find((message) => message.role === role && message.content.trim());

const renderConversationSnapshot = (
  messages: Message[],
  conversationHistory: ConversationHistoryItem[],
  language: UiLanguage,
) => {
  const visibleMessages = conversationMessages(messages);
  const latestUser = latestMessageByRole(visibleMessages, 'user');
  const latestAssistant = latestMessageByRole(visibleMessages, 'assistant');
  const timeline = visibleMessages.slice(-4);

  return (
    <>
      <div className="komsco-ai__rail-section">
        <div className="komsco-ai__rail-section-head">
          <strong>대화 요약</strong>
          <span>{visibleMessages.length}건</span>
        </div>
        {latestUser || latestAssistant ? (
          <>
            <div className="komsco-ai__rail-command">
              <code>최근 질문 · {messageTime(latestUser?.timestamp, language)}</code>
              <p>{latestUser ? messagePreview(latestUser.content) : '아직 질문이 없습니다.'}</p>
            </div>
            <div className="komsco-ai__rail-command">
              <code>최근 답변 · {messageTime(latestAssistant?.timestamp, language)}</code>
              <p>
                {latestAssistant
                  ? messagePreview(latestAssistant.content)
                  : '아직 답변이 없습니다.'}
              </p>
            </div>
          </>
        ) : (
          <div className="komsco-ai__rail-empty">
            질문을 보내면 요약과 답변 흐름이 여기에 남습니다.
          </div>
        )}
      </div>

      <div className="komsco-ai__rail-section">
        <div className="komsco-ai__rail-section-head">
          <strong>질문·답변 타임라인</strong>
          <span>최신 {timeline.length}건</span>
        </div>
        {timeline.length > 0 ? (
          timeline.map((message, index) => (
            <div
              className="komsco-ai__rail-command"
              data-message-role={message.role}
              key={`${message.timestamp ?? index}-${message.role}`}
            >
              <div className="komsco-ai__rail-command-head">
                <div className="komsco-ai__rail-command-title">
                  <span>{message.role === 'user' ? '사용자' : 'KOMSCO AI AGENT'}</span>
                  <code>{messageTime(message.timestamp, language)}</code>
                </div>
                {renderStatusTag(message.role === 'user' ? '질문' : '답변', 'neutral')}
              </div>
              <p>{messagePreview(message.content)}</p>
            </div>
          ))
        ) : (
          <div className="komsco-ai__rail-empty">아직 질문·답변 타임라인이 없습니다.</div>
        )}
      </div>

      <div className="komsco-ai__rail-section">
        <div className="komsco-ai__rail-section-head">
          <strong>저장된 리포트</strong>
          <span>{conversationHistory.length}건</span>
        </div>
        {conversationHistory.length > 0 ? (
          conversationHistory.slice(0, 3).map((item) => (
            <div className="komsco-ai__rail-command" key={item.id}>
              <code>{formatHistoryTime(item.updatedAt, language)}</code>
              <p>{item.title}</p>
            </div>
          ))
        ) : (
          <div className="komsco-ai__rail-empty">
            저장된 분석 대화가 있으면 이곳에서 다시 확인합니다.
          </div>
        )}
      </div>
    </>
  );
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
  messages: Message[],
  conversationHistory: ConversationHistoryItem[],
  language: UiLanguage,
) => (
  <aside className="komsco-ai__insight-rail" aria-label="현재 분석 컨텍스트">
    <h2 className="komsco-ai__rail-title">현재 클러스터 컨텍스트</h2>
    <div
      className={`komsco-ai__connection-card${
        summary
          ? ' komsco-ai__connection-card--connected'
          : error || aiopsStatusError
            ? ' komsco-ai__connection-card--danger'
            : ''
      }`}
    >
      <div className="komsco-ai__connection-main">
        <span
          className={`komsco-ai__connection-dot${
            summary && aiopsStatus ? ' komsco-ai__connection-dot--connected' : ''
          }`}
        />
        <strong>
          {summary && aiopsStatus
            ? '회사 OCP 연결됨'
            : error || aiopsStatusError
              ? '연결 확인 필요'
              : loading
                ? '연결 확인 중'
                : '연결 대기'}
        </strong>
      </div>
      <div className="komsco-ai__connection-target">
        {summary?.apiUrl || 'console proxy / gateway'}
      </div>
      <div className="komsco-ai__connection-metrics">
        {summary
          ? `${summary.nodes.ready}/${summary.nodes.total} Ready · ${getClusterUsageSummary(summary)}`
          : error || aiopsStatusError
            ? error || aiopsStatusError
            : 'Gateway와 cluster summary를 가져오는 중입니다.'}
      </div>
    </div>
    {renderConversationSnapshot(messages, conversationHistory, language)}

    {renderRailSummaryBadges(summary, loading, error)}
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
      <div className="komsco-ai__rail-error">클러스터 요약을 가져오지 못했습니다. {error}</div>
    )}

    {aiopsStatusError && (
      <div className="komsco-ai__rail-error">
        AIOps 상태를 가져오지 못했습니다. {aiopsStatusError}
      </div>
    )}

    <div className="komsco-ai__rail-section">
      <div className="komsco-ai__rail-section-head">
        <strong>노드 상태</strong>
        <span>{getNodeCompactStatus(summary, loading, error).label}</span>
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
        <span>{getOperatorCompactStatus(summary, loading, error).label}</span>
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
      {renderExecutionCapabilityBadges(aiopsStatus, executionMode)}
      <div className="komsco-ai__scope-list komsco-ai__scope-list--secondary">
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
        <strong>답변 근거</strong>
        <span>{rcaStatusLabel(aiopsStatus?.spec.safetyContract?.rcaContextStatus?.status)}</span>
      </div>
      <div className="komsco-ai__scope-list">
        {renderStatusTag(`수집 ${rcaRailEvidenceCounts(aiopsStatus).collected}건`, 'ok')}
        {renderStatusTag(`추가 확인 ${rcaRailEvidenceCounts(aiopsStatus).missing}건`, 'warn')}
      </div>
      <div className="komsco-ai__rail-command">
        <p>
          {aiopsStatus?.spec.safetyContract?.rcaContextStatus?.latestContext
            ? '최근 답변에 사용한 근거가 연결되어 있습니다.'
            : '질문 실행 후 답변 근거가 연결됩니다.'}
        </p>
      </div>
    </div>

    <div className="komsco-ai__rail-section">
      <div className="komsco-ai__rail-section-head">
        <strong>최근 진단</strong>
        <span>
          {aiopsStatus ? `${aiopsStatus.spec.records.diagnosticRequests.length}건` : '대기'}
        </span>
      </div>
      {renderRecordRows(
        aiopsStatus?.spec.records.diagnosticRequests ?? [],
        '최근 진단 요청이 없습니다.',
      )}
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
      {renderActionLifecycle(aiopsStatus, executionMode)}
      {aiopsActionError && <div className="komsco-ai__rail-error">{aiopsActionError}</div>}
      {aiopsActionNotice && <div className="komsco-ai__rail-success">{aiopsActionNotice}</div>}
      {renderActionRecordRows(
        [
          ...(aiopsStatus?.spec.records.actionProposals ?? []),
          ...(aiopsStatus?.spec.records.sealedActionPlans ?? []),
          ...(aiopsStatus?.spec.records.approvalDecisions ?? []),
          ...(aiopsStatus?.spec.records.executionRecords ?? []),
        ].sort(
          (a, b) =>
            new Date(String(b.metadata?.createdAt ?? 0)).getTime() -
            new Date(String(a.metadata?.createdAt ?? 0)).getTime(),
        ),
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
  draftPrompt?: AssistantDraftPrompt;
  embedded?: boolean;
  lockOpen?: boolean;
  onRunComplete?: () => Promise<void> | void;
  overlayId?: string;
  closeOverlay?: () => void;
};

const AssistantSurfacePortal: React.FC<{
  active: boolean;
  children: React.ReactNode;
  wrapperClassName: string;
}> = ({
  active,
  children,
  wrapperClassName,
}) => {
  if (active && typeof document !== 'undefined') {
    return ReactDOM.createPortal(<div className={wrapperClassName}>{children}</div>, document.body);
  }

  return <>{children}</>;
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
  const [messages, setMessages] = React.useState<Message[]>(
    () => initialActiveConversation?.messages ?? [],
  );
  const [conversationId, setConversationId] = React.useState<string | undefined>(
    () => initialActiveConversation?.conversationId,
  );
  const [activeSessionId, setActiveSessionId] = React.useState(
    () => initialActiveConversation?.activeSessionId ?? createRunId(),
  );
  const [conversationHistory, setConversationHistory] = React.useState<ConversationHistoryItem[]>(
    readStoredConversationHistory,
  );
  const [historySidebarOpen, setHistorySidebarOpen] = React.useState(false);
  const [historyPanelView, setHistoryPanelView] = React.useState<HistoryPanelView>('chats');
  const [uploadedDocuments, setUploadedDocuments] = React.useState<RagUploadedDocument[]>([]);
  const [uploadedDocumentsError, setUploadedDocumentsError] = React.useState('');
  const [uploadedDocumentsLoading, setUploadedDocumentsLoading] = React.useState(false);
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
  const [uiLanguage, setUiLanguage] = React.useState<UiLanguage>(() => readStoredUiLanguage());
  const [loading, setLoading] = React.useState(false);
  const [copiedMessageIndex, setCopiedMessageIndex] = React.useState<number | null>(null);
  const [previewAttachment, setPreviewAttachment] = React.useState<ImageAttachment | null>(null);
  const [, setProgressTick] = React.useState(0);
  const surfaceRef = React.useRef<HTMLDivElement | null>(null);
  const bodyRef = React.useRef<HTMLDivElement | null>(null);
  const bodyEndRef = React.useRef<HTMLDivElement | null>(null);
  const fileInputRef = React.useRef<HTMLInputElement | null>(null);
  const consumedDraftPromptIdRef = React.useRef('');
  const quickPromptMenuRef = React.useRef<HTMLDivElement | null>(null);
  const taskModeMenuRef = React.useRef<HTMLDivElement | null>(null);
  const assistantTextQueueRef = React.useRef('');
  const assistantTypewriterTimerRef = React.useRef<number | undefined>();
  const assistantTextDrainResolversRef = React.useRef<Array<() => void>>([]);
  const chatAbortControllerRef = React.useRef<AbortController | null>(null);
  const stopRequestedRef = React.useRef(false);
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

  React.useEffect(() => {
    writeStoredActiveConversation({
      activeSessionId,
      conversationId,
      messages,
    });
  }, [activeSessionId, conversationId, messages]);

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
    if (!quickPromptMenuOpen && !taskModeMenuOpen) {
      return undefined;
    }

    const handleDocumentMouseDown = (event: MouseEvent) => {
      const target = event.target as Node | null;
      if (
        target &&
        (quickPromptMenuRef.current?.contains(target) || taskModeMenuRef.current?.contains(target))
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
      setAiopsActionError('');
      setExecutionMode(mode);
    },
    [],
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

      setConversationHistory((prev) =>
        [item, ...prev.filter((conversation) => conversation.id !== activeSessionId)].slice(
          0,
          MAX_STORED_CONVERSATIONS,
        ),
      );
    },
    [activeSessionId, conversationId, messages, uiLanguage],
  );

  React.useEffect(() => {
    if (!loading) {
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
    try {
      const status = await fetchAiopsStatus();

      setAiopsStatus(status);
      setAiopsStatusError('');
    } catch (error) {
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

        if (action.step === 'reject-plan') {
          const planId = getRecordName(record);
          const planDigest = getPlanDigest(record);
          if (!planId || !planDigest) {
            throw new Error('Action plan id 또는 digest가 없습니다.');
          }
          await rejectActionPlan(planId, planDigest);
          setAiopsActionNotice('Action plan을 거절 기록했습니다.');
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
          await executeApprovedAction(approvalId, planId, planDigest);
          setAiopsActionNotice('승인된 조치를 실행했습니다.');
        }

        await refreshAiopsRuntimeStatus();
      } catch (error) {
        setAiopsActionError(error instanceof Error ? error.message : 'AIOps action failed.');
      } finally {
        aiopsActionBusyIdRef.current = '';
        setAiopsActionBusyId('');
      }
    },
    [aiopsStatus, executionMode, refreshAiopsRuntimeStatus],
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
        await createActionCandidatePlan(candidate);
        setAiopsActionNotice('조치 계획을 생성했습니다.');
        await refreshAiopsRuntimeStatus();
      } catch (error) {
        setAiopsActionError(
          error instanceof Error ? error.message : '조치 계획 생성에 실패했습니다.',
        );
      } finally {
        busyActionCandidateIdRef.current = '';
        setBusyActionCandidateId('');
      }
    },
    [refreshAiopsRuntimeStatus],
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
    const redactedContent = redactSensitiveText(stripDefaultEvidenceAppendix(message.content).trim());
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
                namespace: 'komsco-ai-kugnus',
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
            detail: 'OpenShift Lightspeed가 답변 생성을 시작하기를 기다리는 중입니다.',
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
        setLoading(false);
      }
    },
    [
      enqueueAssistantText,
      assistantTaskMode,
      draftPageContext,
      executionMode,
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

    setHistorySidebarOpen(false);
    setHistoryDrawerBounds({});
    setOpen(false);
  }, [lockOpen]);

  const historySidebar = historySidebarOpen ? (
    <aside
      className="komsco-ai__history-sidebar"
      aria-label={historyPanelView === 'uploads' ? copy.uploadedDocs : copy.sidebar}
      style={historySidebarStyle}
    >
      <div
        className="komsco-ai__history-actions"
        aria-label={historyPanelView === 'uploads' ? copy.uploadedDocs : copy.sidebar}
      >
        <div className="komsco-ai__history-brand">
          <img alt="KOMSCO" className="komsco-ai__history-logo" src={komscoLogo} />
        </div>
        <div className="komsco-ai__history-actions-right">
          <button
            aria-label={copy.newChat}
            className="komsco-ai__history-action-button komsco-ai__history-action-button--primary"
            onClick={() => {
              startNewConversation();
              setHistoryPanelView('chats');
            }}
            title={copy.newChat}
            type="button"
          >
            <CoolComposeIcon />
          </button>
          <div className="komsco-ai__history-action-group" role="group" aria-label={copy.sidebar}>
            <button
              aria-label={copy.openHistoryPanel}
              aria-pressed={historyPanelView === 'chats'}
              className={`komsco-ai__history-action-button${
                historyPanelView === 'chats' ? ' komsco-ai__history-action-button--active' : ''
              }`}
              onClick={() => setHistoryPanelView('chats')}
              title={copy.openHistoryPanel}
              type="button"
            >
              <CoolClockIcon />
            </button>
            <button
              aria-label={copy.openUploadedDocs}
              aria-pressed={historyPanelView === 'uploads'}
              className={`komsco-ai__history-action-button${
                historyPanelView === 'uploads' ? ' komsco-ai__history-action-button--active' : ''
              }`}
              onClick={() => setHistoryPanelView('uploads')}
              title={copy.openUploadedDocs}
              type="button"
            >
              <CoolDocumentIcon />
            </button>
          </div>
        </div>
      </div>
      <div className="komsco-ai__history-title">
        {historyPanelView === 'uploads' ? <CoolDocumentIcon /> : <CoolClockIcon />}
        <span>{historyPanelView === 'uploads' ? copy.uploadedDocs : copy.history}</span>
      </div>
      {historyPanelView === 'uploads' ? (
        <div className="komsco-ai__history-list komsco-ai__history-list--uploads">
          {uploadedDocumentsLoading && uploadedDocuments.length === 0 ? (
            <div className="komsco-ai__history-empty">{copy.uploadedDocsLoading}</div>
          ) : uploadedDocumentsError && uploadedDocuments.length === 0 ? (
            <div className="komsco-ai__history-empty komsco-ai__history-empty--error">
              {uploadedDocumentsError}
            </div>
          ) : (
            renderUploadedDocumentRows(uploadedDocuments, copy.emptyUploadedDocs)
          )}
        </div>
      ) : (
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
                <small>{formatHistoryTime(conversation.updatedAt, uiLanguage)}</small>
              </button>
            ))
          )}
        </div>
      )}
      <div className="komsco-ai__history-user" aria-label="현재 OpenShift 사용자">
        <div className="komsco-ai__history-user-avatar">
          <CoolUserCircleIcon />
        </div>
        <div className="komsco-ai__history-user-main">
          <strong title={authSubject?.username || authSubjectError || '사용자 확인 중'}>
            {authSubject?.username || (authSubjectError ? '인증 확인 필요' : '확인 중')}
          </strong>
          <small title={clusterSummary?.apiUrl || ''}>
            {getClusterHost(clusterSummary?.apiUrl)}
          </small>
        </div>
      </div>
    </aside>
  ) : null;
  const assistantVisible = open || embedded || lockOpen;
  const historySidebarPortal =
    assistantVisible && historySidebar && !fullScreen && typeof document !== 'undefined'
      ? ReactDOM.createPortal(historySidebar, document.body)
      : null;

  const assistantRootClassName = `komsco-ai${embedded ? ' komsco-ai--embedded' : ''}${
    fullScreen ? ' komsco-ai--fullscreen-active' : ''
  }`;
  const assistantSurfacePortalActive = assistantVisible && !embedded;

  return (
    <div
      className={assistantRootClassName}
      data-ui-language={uiLanguage}
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

      {assistantVisible && (
        <AssistantSurfacePortal
          active={assistantSurfacePortalActive}
          wrapperClassName={`${assistantRootClassName} komsco-ai--portal`}
        >
          <div
            aria-label="Cywell AI assistant"
            ref={surfaceRef}
            className={`komsco-ai__surface${fullScreen ? ' komsco-ai__surface--fullscreen' : ''}${
              historySidebarOpen ? ' komsco-ai__surface--history-open' : ''
            }${panelResizeUnlocked ? ' komsco-ai__surface--resize-unlocked' : ''}${
              !panelResizeUnlocked ? ' komsco-ai__surface--resize-locked' : ''
            }`}
            style={surfaceStyle}
          >
            {fullScreen ? historySidebar : null}
            <Card
              className={`komsco-ai__panel${fullScreen ? ' komsco-ai__panel--fullscreen' : ''}`}
            >
              <div className="komsco-ai__header">
                <Button
                  aria-label={copy.openSidebar}
                  className="komsco-ai__icon-button komsco-ai__sidebar-toggle"
                  onClick={() => setHistorySidebarOpen((value) => !value)}
                  title={copy.openSidebar}
                  variant="plain"
                >
                  <CoolMenuIcon />
                </Button>
                <div className="komsco-ai__brand">
                  <span className="komsco-ai__title">KOMSCO AI Agent</span>
                </div>
                <div
                  className="komsco-ai__header-status"
                  aria-label="클러스터 운영 상태 및 실행 모드"
                >
                  {renderHeaderOpsStatus(
                    clusterSummary,
                    clusterSummaryLoading,
                    clusterSummaryError,
                  )}
                  <div className="komsco-ai__header-sep" aria-hidden="true" />
                  {renderExecutionModeToggle(
                    executionMode,
                    actionExecutionAvailable,
                    actionExecutionDisabledReason,
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
                    <CoolGlobeIcon />
                    <span className="komsco-ai__language-code">
                      {uiLanguage === 'ko' ? 'KR' : 'EN'}
                    </span>
                  </Button>
                  <Button
                    aria-label={fullScreen ? 'Exit full screen' : 'Open full screen'}
                    className="komsco-ai__icon-button"
                    onClick={() => setFullScreen((value) => !value)}
                    variant="plain"
                  >
                    {fullScreen ? <CoolShrinkIcon /> : <CoolExpandIcon />}
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
                    {panelResizeUnlocked ? <CoolLockOpenIcon /> : <CoolLockIcon />}
                  </Button>
                  {!lockOpen && (
                    <Button
                      aria-label="Close Cywell AI"
                      className="komsco-ai__icon-button"
                      onClick={closeAssistant}
                      variant="plain"
                    >
                      <CoolCloseIcon />
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
                          <div className="komsco-ai__empty-title">{emptyStateCopy.title}</div>
                          <div className="komsco-ai__empty-text">{emptyStateCopy.text}</div>
                        </div>
                      )}

                      {messages.map((message, index) => {
                        const hasProgress = (message.progressSteps?.length ?? 0) > 0;
                        const hasContent = message.content.trim().length > 0;
                        const activeMessage = loading && index === messages.length - 1;
                        const isLatestAssistantMessage =
                          message.role === 'assistant' && index === findLastAssistantIndex(messages);
                        const answerActionRecords =
                          isLatestAssistantMessage &&
                          hasContent &&
                          isActionAnswerContract(message.answerContract)
                            ? latestAnswerActionRecords(aiopsStatus, executionMode)
                            : [];
                        const matchedActionCandidates =
                          isLatestAssistantMessage && hasContent
                            ? matchActionCandidatesForMessage(message.content, actionCandidates)
                            : [];
                        const waitingForContent =
                          activeMessage && message.role === 'assistant' && !hasContent;
                        const messageTime = formatMessageTime(message.timestamp, uiLanguage);
                        const assistantSourceLabel =
                          message.role === 'assistant' && hasContent
                            ? message.fallbackAnswer
                              ? 'Gateway fallback'
                              : 'OpenShift Lightspeed (OLS)'
                            : '';
                        const assistantSourceTitle = message.fallbackAnswer
                          ? message.gatewayContextDigest
                            ? `Gateway context ${message.gatewayContextDigest}`
                            : 'Gateway fallback answer'
                          : 'OpenShift Lightspeed (OLS) answer';

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
                                  {getMessageLabel(message.role, uiLanguage)}
                                </div>
                                {assistantSourceLabel && (
                                  <span
                                    className={`komsco-ai__message-source ${
                                      message.fallbackAnswer
                                        ? 'komsco-ai__message-source--fallback'
                                        : 'komsco-ai__message-source--lightspeed'
                                    }`}
                                    title={assistantSourceTitle}
                                  >
                                    {assistantSourceLabel}
                                  </span>
                                )}
                                {message.role === 'assistant' && hasContent && (
                                  <button
                                    aria-label={copy.answerCopy}
                                    className="komsco-ai__message-copy"
                                    onClick={() => copyMessage(message, index)}
                                    title={copy.answerCopy}
                                    type="button"
                                  >
                                    <CoolCopyIcon />
                                    <span>
                                      {copiedMessageIndex === index
                                        ? copy.answerCopied
                                        : copy.answerCopy}
                                    </span>
                                  </button>
                                )}
                              </div>
                              {(hasContent || (!hasProgress && !waitingForContent)) && (
                                <div className="komsco-ai__message-content">
                                  {renderFormattedContent(message, setPreviewAttachment)}
                                </div>
                              )}
                              {message.role === 'assistant' &&
                                hasContent &&
                                renderEvidenceFooter(message.evidenceFooter, message.content)}
                              {message.role === 'assistant' &&
                                hasContent &&
                                renderToolPlanFooter(message.toolPlan)}
                              {message.role === 'assistant' &&
                                hasContent &&
                                renderCreateActionPlanButtons(
                                  matchedActionCandidates,
                                  busyActionCandidateId,
                                  handleCreateActionPlanFromChat,
                                )}
                              {message.role === 'assistant' &&
                                hasContent &&
                                renderAssistantAnswerActions(
                                  answerActionRecords,
                                  aiopsStatus,
                                  executionMode,
                                  aiopsActionBusyId,
                                  handleAiopsAction,
                                )}
                              {hasProgress && message.progressSteps && (
                                <ProgressTimeline
                                  active={activeMessage}
                                  steps={message.progressSteps}
                                />
                              )}
                              {messageTime && (
                                <div className="komsco-ai__message-time">{messageTime}</div>
                              )}
                            </div>
                          </div>
                        );
                      })}
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
                        aria-label={copy.scrollToLatest}
                        className="komsco-ai__scroll-bottom"
                        onClick={() => {
                          setStickToBottom(true);
                          setShowScrollToBottom(false);
                          scrollToBottom('auto');
                        }}
                        variant="secondary"
                      >
                        <CoolArrowDownIcon />
                      </Button>
                    )}
                    <div className="komsco-ai__input">
                      <input
                        accept={FILE_INPUT_ACCEPT}
                        aria-label={copy.fileAttach}
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
                                  <CoolCloseIcon />
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
                                <CoolPlusIcon />
                              </Button>
                              {quickPromptMenuOpen && (
                                <div className="komsco-ai__quick-menu-panel" role="menu">
                                  {executionMode === 'execute' && (
                                    <div
                                      aria-checked={autoProposeActions}
                                      className="komsco-ai__quick-menu-item komsco-ai__quick-menu-item--toggle"
                                      role="menuitemcheckbox"
                                    >
                                      <span className="komsco-ai__quick-prompt-icon">
                                        <CoolShieldCheckIcon />
                                      </span>
                                      <span className="komsco-ai__quick-menu-copy">
                                        <strong>조치 계획 기본 제공</strong>
                                        <small>
                                          질문마다 조치 계획을 먼저 보여줍니다. 끄면 요청할 때만
                                          만듭니다.
                                        </small>
                                      </span>
                                      <Switch
                                        aria-label="답변 후 조치 계획 기본 제공"
                                        id="komsco-ai-auto-propose-toggle"
                                        isChecked={autoProposeActions}
                                        onChange={(_event, checked) =>
                                          setAutoProposeActions(checked)
                                        }
                                      />
                                    </div>
                                  )}
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
                                      <span className="komsco-ai__quick-prompt-icon">
                                        {item.icon}
                                      </span>
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
                              aria-label="파일 첨부"
                              className="komsco-ai__tool-button komsco-ai__attach"
                              isDisabled={loading}
                              onClick={() => fileInputRef.current?.click()}
                              variant="plain"
                            >
                              <CoolPaperclipIcon />
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
                                <span className="komsco-ai__task-mode-icon">
                                  {selectedTaskMode.icon}
                                </span>
                                <span className="komsco-ai__task-mode-label">
                                  {selectedTaskMode.label}
                                </span>
                                <CoolCaretDownIcon />
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
                            isDisabled={
                              !loading && !input.trim() && pendingAttachments.length === 0
                            }
                            onClick={() => {
                              if (loading) {
                                cancelAssistantResponse();
                                return;
                              }
                              void send();
                            }}
                            variant="plain"
                          >
                            {loading ? <CoolStopIcon /> : <CoolPaperPlaneIcon />}
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
                  messages,
                  conversationHistory,
                  uiLanguage,
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
        </AssistantSurfacePortal>
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
                <CoolCloseIcon />
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
