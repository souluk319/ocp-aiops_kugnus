import type { AiopsRecord, ImageAttachment } from '../services/aiGateway';

export type HistoryPanelView = 'chats' | 'uploads';

export type Message = {
  role: 'user' | 'assistant' | 'system';
  answerContract?: string;
  answerSource?: 'ols' | 'gateway_direct' | 'gateway_fallback' | 'copilot_clarification';
  attachments?: ImageAttachment[];
  content: string;
  evidenceFooter?: EvidenceFooter;
  fallbackAnswer?: boolean;
  feedback?: 'up' | 'down';
  feedbackAt?: number;
  feedbackComment?: string;
  gatewayContextDigest?: string;
  progressSteps?: ProgressStep[];
  timestamp?: number;
  toolPlan?: ToolPlanFooter;
};

export type ToolPlanStep = {
  adapter?: string;
  evidenceType?: string;
  reason?: string;
  step?: number | string;
  tool?: string;
  verb?: string;
};

export type ToolPlanMissingEvidence = {
  reason?: string;
  type?: string;
};

export type ToolPlanFooter = {
  executionPolicyMode?: string;
  missingEvidence: ToolPlanMissingEvidence[];
  plannerLabel?: string;
  plannerSource?: string;
  plannerSummary?: string;
  rawPlanJson?: string;
  steps: ToolPlanStep[];
  targetNamespace?: string;
  targetResourceKind?: string;
  targetResourceName?: string;
  taskType?: string;
  validationOk?: boolean;
  validationViolations: string[];
};

export type EvidenceFooterRef = {
  contentDigest?: string;
  evidenceId?: string;
  sourceType?: string;
  status?: string;
  summary?: string;
  type?: string;
};

export type EvidenceFooterMissing = {
  contentDigest?: string;
  evidenceId?: string;
  reason?: string;
  type?: string;
};

export type EvidenceFooterQueryStep = {
  adapter?: string;
  evidenceType?: string;
  reason?: string;
  status?: string;
  step?: string;
  tool?: string;
};

export type RagAppendixRef = {
  sourceUri?: string;
  title: string;
};

export type EvidenceFooter = {
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

export type AiopsExecutionMode = 'read-only' | 'execute' | 'unrestricted';
export type AssistantTaskMode = 'ask' | 'troubleshooting';
export type UiLanguage = 'ko' | 'en';
export type PanelResizeDirection = 'n' | 'ne' | 'e' | 'se' | 's' | 'sw' | 'w' | 'nw';

export type AssistantDraftPrompt = {
  id: string;
  pageContext?: Record<string, unknown>;
  prompt: string;
  taskMode?: AssistantTaskMode;
};

export type AssistantLaunchContext = {
  actionType?: string;
  evidenceRefs?: string[];
  kind?: string;
  name?: string;
  namespace?: string;
  promptDraft: string;
  reason?: string;
  severity?: string;
  source: string;
};

export type ProgressStatus = 'running' | 'completed' | 'failed';

export type ProgressStep = {
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

export type ConversationActionStage = 'proposal' | 'plan' | 'approval' | 'execution';

export type ConversationActionRef = {
  candidateId?: string;
  createdAt?: string;
  id: string;
  label: string;
  messageAnchor?: string;
  planDigest?: string;
  recordKind?: string;
  recordName?: string;
  stage: ConversationActionStage;
  targetKey: string;
  toolName?: string;
  updatedAt: number;
};

export type ConversationHistoryItem = {
  id: string;
  title: string;
  updatedAt: number;
  conversationId?: string;
  messages: Message[];
  actionRefs?: ConversationActionRef[];
  actionTargetKeys?: string[];
};

export type ToolStreamEvent = {
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

export type RunStatusEvent = {
  type: 'run_status';
  elapsedMs?: number;
  gatewayContextDigest?: string;
  message: string;
  rcaContextDigest?: string;
  runId?: string;
  stage: string;
};

export type LightspeedStatusUpdate = {
  fallbackActive?: boolean;
  lastContextDigest?: string | undefined;
  lastError?: string | undefined;
  lastStatus?: string | undefined;
  streamProbe?: string | undefined;
};

export type StoredActiveConversation = {
  activeSessionId: string;
  actionRefs?: ConversationActionRef[];
  actionTargetKeys?: string[];
  conversationId?: string;
  messages: Message[];
};

export type AiopsRecordView = AiopsRecord;
export type AiopsActionStep =
  | 'create-plan'
  | 'approve-plan'
  | 'approve-execute-plan'
  | 'reject-plan'
  | 'execute-approval';
export type AiopsLifecycleStage = ConversationActionStage;
export type UiTone = 'ok' | 'warn' | 'danger' | 'review' | 'neutral';

export type AiopsRecordAction = {
  disabledReason?: string;
  label: string;
  step: AiopsActionStep;
};

export type PlanSummary = {
  risk: string;
  riskLabel: string;
  riskTone: 'ok' | 'warn' | 'danger' | 'neutral';
  rollbackDescription: string;
  rollbackPossible: boolean;
  toolLabel: string;
};

export interface ExecutionOutcomeSummary {
  tone: 'ok' | 'warn' | 'danger';
  title: string;
  detail: string;
}

export type AssistantLauncherProps = {
  defaultOpen?: boolean;
  draftPrompt?: AssistantDraftPrompt;
  embedded?: boolean;
  lockOpen?: boolean;
  onRunComplete?: () => Promise<void> | void;
  overlayId?: string;
  closeOverlay?: () => void;
};
