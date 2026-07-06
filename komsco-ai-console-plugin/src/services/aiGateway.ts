import { consoleFetch } from '@openshift-console/dynamic-plugin-sdk';

type ChatRequest = {
  message: string;
  attachments?: ImageAttachment[];
  pageContext?: Record<string, unknown>;
  conversationId?: string;
  runId?: string;
  recentMessages?: ChatContextMessage[];
};

type StreamChatOptions = {
  signal?: AbortSignal;
};

export type ChatFeedbackPayload = {
  answerContract?: string;
  answerSource?: string;
  conversationId?: string;
  feedbackId?: string;
  intent?: string;
  messageId: string;
  mode: string;
  optionalComment?: string;
  rating: 'up' | 'down';
  route?: string;
  source?: string;
  timestamp: string;
};

export type ChatFeedbackResult = {
  apiVersion?: string;
  kind?: 'ChatFeedback' | string;
  metadata?: {
    createdAt?: string;
    name?: string;
  };
  spec?: Record<string, unknown>;
};

export type ImageAttachment = {
  data: string;
  id: string;
  mimeType: string;
  name: string;
  size: number;
};

export type ChatContextMessage = {
  role: 'user' | 'assistant' | 'system';
  content: string;
};

export type ClusterSummary = {
  apiUrl?: string;
  healthScore: number;
  nodes: {
    total: number;
    ready: number;
    notReady: number;
    pressureCount: number;
    metricsAvailable: boolean;
    items: Array<{
      kubeletVersion?: string;
      name: string;
      osImage?: string;
      pressures: {
        disk: boolean;
        memory: boolean;
        pid: boolean;
      };
      ready: boolean;
      roles: string[];
      usage: {
        cpu?: string;
        memory?: string;
      };
    }>;
  };
  operators: {
    available: number;
    degraded: number;
    progressing: number;
    total: number;
    unavailable: number;
    issues: Array<{
      available: boolean;
      degraded: boolean;
      message?: string;
      name: string;
      progressing: boolean;
      reason?: string;
      upgradeable?: string;
    }>;
  };
  updatedAt: string;
  version: {
    channel?: string;
    updateAvailable: boolean;
    upgradeable?: boolean | null;
    upgradeableMessage?: string;
    upgradeableReason?: string;
    version?: string;
  };
};

export type AiopsDataSourceStatus = {
  httpStatus?: number;
  label: string;
  name: string;
  path: string;
  reason?: string;
  required?: boolean;
  status: 'available' | 'unavailable' | 'error' | string;
};

export type AiopsAnomalyFinding = {
  candidateCause?: string;
  category?: string;
  evidence?: string;
  id: string;
  impact?: string;
  lastObservedAt?: string;
  message?: string;
  namespace?: string;
  nextCheck?: string;
  priority: number;
  reason?: string;
  resource?: {
    kind?: string;
    name?: string;
    namespace?: string;
  };
  severity: '정상' | '주의' | '확인 필요' | '위험' | string;
  source: string;
  status?: string;
  statusLabel?: string;
  title: string;
  type: string;
};

export type AiopsAnomalySummary = {
  apiVersion?: string;
  kind?: 'AIOpsAnomalySummary' | string;
  metadata?: {
    generatedAt?: string;
    name?: string;
  };
  spec?: {
    dataSources?: AiopsDataSourceStatus[];
    excludedAlerts?: Array<Record<string, unknown>>;
    findings?: AiopsAnomalyFinding[];
    normalSignals?: string[];
    query?: {
      limit?: number;
      namespace?: string;
      sinceMinutes?: number;
    };
    safety?: {
      methodsUsed?: string[];
      mode?: string;
      mutationsEnabled?: boolean;
      unrestrictedCommandsEnabled?: boolean;
    };
    status?: 'normal' | 'warning' | 'attention' | 'risk' | 'error' | 'unknown' | string;
    statusLabel?: string;
    totals?: {
      attention?: number;
      danger?: number;
      total?: number;
      warning?: number;
    };
  };
};

export type AiopsActionCandidate = {
  approvalRequired?: boolean;
  blockedActions?: string[];
  blockedReasons?: string[];
  confidence?: string;
  evidence?: string;
  evidenceRefs?: Array<Record<string, unknown>>;
  executable?: boolean;
  executionPolicy?: {
    executionEnabled?: boolean;
    mode?: string;
    mutationVerbsDisabled?: boolean;
    proposalOnly?: boolean;
  };
  expectedImpact?: string;
  id: string;
  mutationSubmitted?: boolean;
  priority?: number;
  prerequisiteChecks?: string[];
  recommendationSteps?: string[];
  riskLabel?: string;
  riskLevel?: 'high' | 'medium' | 'low' | string;
  severity?: string;
  sourceFindingId?: string;
  sourceType?: string;
  statusLabel?: string;
  target?: {
    apiVersion?: string;
    kind?: string;
    name?: string;
    namespace?: string;
    uid?: string;
  };
  title: string;
  verificationChecks?: string[];
};

export type AiopsActionCandidatePlanResult = {
  apiVersion?: string;
  kind?: 'ActionCandidatePlan' | string;
  metadata?: {
    createdAt?: string;
    name?: string;
  };
  spec?: {
    candidateId?: string;
    plan?: AiopsRecord;
    planDigest?: string;
    planId?: string;
    proposal?: AiopsRecord;
    proposalId?: string;
    status?: string;
    target?: {
      apiVersion?: string;
      kind?: string;
      name?: string;
      namespace?: string;
      uid?: string;
    };
    title?: string;
  };
};

export type AiopsActionCandidateSummary = {
  apiVersion?: string;
  kind?: 'AIOpsActionCandidateSummary' | string;
  metadata?: {
    generatedAt?: string;
    name?: string;
  };
  spec?: {
    candidates?: AiopsActionCandidate[];
    dataSources?: AiopsDataSourceStatus[];
    safety?: {
      forbiddenMutationVerbs?: string[];
      methodsUsed?: string[];
      mode?: string;
      mutationsEnabled?: boolean;
      proposalOnly?: boolean;
      unrestrictedCommandsEnabled?: boolean;
    };
    source?: {
      anomalySummaryName?: string;
      requiredDataSourceGaps?: AiopsDataSourceStatus[];
    };
    status?: 'normal' | 'candidates' | 'blocked' | 'unknown' | string;
    statusLabel?: string;
    totals?: {
      approvalRequired?: number;
      blockedByRequiredSourceGap?: number;
      highRisk?: number;
      shown?: number;
      total?: number;
    };
  };
};

export type AiopsOverview = {
  apiVersion?: string;
  kind?: 'AIOpsOverview' | string;
  metadata?: {
    generatedAt?: string;
    name?: string;
  };
  spec: {
    clusterSummary: ClusterSummary;
    controlTower: {
      attentionCount: number;
      healthScore: number;
      mode: 'evidence-check' | string;
      name: string;
      status: 'healthy' | 'attention' | 'risk' | 'error' | string;
      statusLabel: string;
      target?: string;
    };
    anomalies?: AiopsAnomalySummary;
    actionCandidates?: AiopsActionCandidateSummary;
    dataSources: AiopsDataSourceStatus[];
    monitoring?: {
      probe?: {
        httpStatus?: number;
        query?: string;
        reason?: string;
        resultCount?: number;
        status?: string;
      };
      urls?: {
        alertmanagerConfigured?: boolean;
        prometheusConfigured?: boolean;
        thanosConfigured?: boolean;
      };
    };
    safety?: {
      mutationsEnabled?: boolean;
      executionDefault?: boolean;
      unrestrictedCommandsEnabled?: boolean;
    };
  };
};

export type AuthSubject = {
  authenticatedByCluster?: boolean;
  groups?: string[];
  groupsDigest?: string;
  uid?: string;
  username: string;
};

export type AiopsRecord = {
  kind?: string;
  metadata?: {
    createdAt?: string;
    name?: string;
  };
  spec?: Record<string, unknown>;
};

export type EvidenceStatusItem = {
  count: number;
  reason?: string;
  status: 'collected' | 'missing' | string;
  type: string;
};

export type RagUploadedDocument = {
  aclGroups?: string[];
  checksum?: string;
  chunkCount?: number;
  contentBytes?: number;
  customer?: string;
  documentId: string;
  ingestedAt?: string;
  labels?: Record<string, string>;
  mimeType?: string;
  namespace?: string;
  runId?: string;
  sourceType?: string;
  sourceUri?: string;
  title: string;
  updatedAt?: string;
  uploadedBy?: string;
  version?: string;
};

export type RagSearchResultItem = {
  content?: string;
  contentPreview?: string;
  customer?: string;
  documentId?: string;
  evidenceRef?: Record<string, unknown>;
  id?: string;
  metadata?: Record<string, unknown>;
  namespace?: string;
  score?: number;
  sourceType?: string;
  sourceUri?: string;
  title?: string;
  version?: string;
};

export type RagSearchRequest = {
  filters?: {
    aclGroups?: string[];
    customers?: string[];
    labels?: Record<string, string>;
    namespaces?: string[];
    runbookIds?: string[];
    sourceTypes?: string[];
    versions?: string[];
  };
  includeContent?: boolean;
  query: string;
  runId?: string;
  topK?: number;
};

export type RagSearchResult = {
  apiVersion?: string;
  kind?: 'RagSearchResult' | string;
  metadata?: {
    generatedAt?: string;
    name?: string;
  };
  spec: {
    evidence?: Record<string, unknown>;
    filters?: Record<string, unknown>;
    includeContent?: boolean;
    query?: string;
    reason?: string;
    results: RagSearchResultItem[];
    safety?: Record<string, unknown>;
    status: 'collected' | 'empty' | 'not_configured' | 'unavailable' | string;
    topK?: number;
  };
};

export type RagDocumentUploadRequest = {
  aclGroups?: string[];
  content: string;
  customer?: string;
  labels?: Record<string, string>;
  mimeType?: string;
  name: string;
  namespace?: string;
  runId?: string;
  sourceType?: string;
  sourceUri?: string;
  version?: string;
};

export type RagDocumentUploadFileMetadata = {
  customer?: string;
  labels?: Record<string, string>;
  namespace?: string;
  runId?: string;
  sourceType?: string;
  sourceUri?: string;
  version?: string;
};

export type RagUploadIngestionResult = {
  apiVersion?: string;
  kind?: 'RagUploadIngestionResult' | string;
  metadata?: {
    generatedAt?: string;
    name?: string;
  };
  spec: {
    backend?: AiopsRuntimeStatus['spec']['capabilities']['rag'];
    chunks?: Array<{
      charLength?: number;
      checksum?: string;
      chunkId?: string;
      chunkIndex?: number;
      sourceUri?: string;
      textHash?: string;
    }>;
    document: RagUploadedDocument;
    ingestionReport?: Record<string, unknown>;
    reason?: string;
    safety?: Record<string, unknown>;
    status: 'persisted' | 'not_configured' | 'unavailable' | string;
  };
};

export type RagUploadedDocumentList = {
  apiVersion?: string;
  kind?: 'RagUploadedDocumentList' | string;
  metadata?: {
    generatedAt?: string;
    name?: string;
  };
  spec: {
    backend?: AiopsRuntimeStatus['spec']['capabilities']['rag'];
    documents: RagUploadedDocument[];
    reason?: string;
    status: 'collected' | 'empty' | 'not_configured' | 'unavailable' | string;
    totals?: {
      documents?: number;
    };
  };
};

export type AiopsRuntimeStatus = {
  spec: {
    capabilities: {
      actionExecutorConfigured: boolean;
      diagnosticsControllerConfigured: boolean;
      diagnosticsEnabled: boolean;
      mutationsEnabled: boolean;
      rag?: {
        accessPath?: string;
        aclRequired?: boolean;
        backendType?: string;
        collection?: string;
        directDatabaseAccess?: boolean;
        embeddingModel?: string;
        endpointConfigured?: boolean;
        reason?: string;
        requiredMetadata?: string[];
        status?: string;
        vectorDimensions?: number;
      };
      recordStoreConfigMap?: string;
      recordStoreEnabled: boolean;
      unrestrictedCommandsEnabled?: boolean;
    };
    safetyContract?: {
      adapterStatus?: Array<{
        disabledReason?: string;
        detail?: string;
        name: string;
        nextAction?: string;
        reason?: string;
        requirements?: string[];
        status: string;
        supportedTools?: Array<{
          description?: string;
          disabledReason?: string;
          evidenceTypes?: string[];
          status?: string;
          tool: string;
          verbs?: string[];
        }>;
        type?: string;
      }>;
      allowedReadOnlyVerbs: string[];
      capabilityGates: Record<string, boolean>;
      evidenceStatus: EvidenceStatusItem[];
      forbiddenActions: string[];
      lightspeedStatus?: {
        baseService?: string;
        fallbackActive?: boolean;
        lastCompletedAt?: string;
        lastContextDigest?: string;
        lastError?: string;
        lastStartedAt?: string;
        lastStatus?: string;
        status?: string;
        streamProbe?: string;
      };
      mode: 'controlled_execution' | 'evidence_check' | string;
      product: {
        mission?: string;
        mode?: string;
        name?: string;
      };
      toolPlanStatus?: {
        adapterResolution?: Array<{
          adapter?: string;
          capability?: string;
          evidenceType?: string;
          reason?: string;
          resolved?: boolean;
          status?: string;
          step?: number;
          tool?: string;
          verb?: string;
        }>;
        latestRuntimePlan?: unknown;
        source?: string;
        status?: string;
      };
      rcaContextStatus?: {
        digest?: string;
        latestContext?: unknown;
        source?: string;
        status?: string;
      };
    };
    subject?: AuthSubject;
    records: {
      actionProposals: AiopsRecord[];
      auditRecords?: AiopsRecord[];
      approvalDecisions: AiopsRecord[];
      chatFeedback?: AiopsRecord[];
      chatTranscripts?: AiopsRecord[];
      diagnosticRequests: AiopsRecord[];
      executionRecords: AiopsRecord[];
      sealedActionPlans: AiopsRecord[];
    };
  };
};

type StreamEvent =
  | { type: 'tool_plan'; plan: unknown; runId?: string; status?: string }
  | {
      type: 'rca_context';
      context: unknown;
      evidenceStatus?: EvidenceStatusItem[];
      phase?: string;
      runId?: string;
      status?: string;
    }
  | {
      type: 'run_status';
      elapsedMs?: number;
      gatewayContextDigest?: string;
      message: string;
      rcaContextDigest?: string;
      runId?: string;
      stage: 'started' | 'lightspeed' | 'waiting' | 'completed' | 'failed' | string;
    }
  | {
      type: 'tool_call';
      name: string;
      id?: string;
      args?: unknown;
      detail?: string;
      serverName?: string;
      summary?: string;
    }
  | {
      type: 'tool_result';
      name: string;
      id?: string;
      detail?: string;
      fallbackAnswer?: boolean;
      gatewayContextDigest?: string;
      result?: unknown;
      serverName?: string;
      status?: string;
      summary?: string;
    }
  | {
      type: 'text';
      content: string;
      answerContract?: string;
      fallbackAnswer?: boolean;
      gatewayContextDigest?: string;
      source?: string;
      streamProbe?: string;
    }
  | { type: 'end'; conversationId?: string }
  | { type: 'error'; message: string };

const GATEWAY_STREAM_URL =
  '/api/proxy/plugin/cywell-aiops-console-plugin/ai-gateway/v1/chat/stream';
const GATEWAY_CHAT_FEEDBACK_URL =
  '/api/proxy/plugin/cywell-aiops-console-plugin/ai-gateway/v1/chat/feedback';
const GATEWAY_CLUSTER_SUMMARY_URL =
  '/api/proxy/plugin/cywell-aiops-console-plugin/ai-gateway/v1/cluster/summary';
const GATEWAY_AIOPS_OVERVIEW_URL =
  '/api/proxy/plugin/cywell-aiops-console-plugin/ai-gateway/v1/aiops/overview';
const GATEWAY_AIOPS_STATUS_URL =
  '/api/proxy/plugin/cywell-aiops-console-plugin/ai-gateway/v1/aiops/status';
const GATEWAY_AIOPS_ACTION_CANDIDATES_URL =
  '/api/proxy/plugin/cywell-aiops-console-plugin/ai-gateway/v1/aiops/action-candidates';
const GATEWAY_RAG_UPLOADS_URL =
  '/api/proxy/plugin/cywell-aiops-console-plugin/ai-gateway/v1/rag/uploads';
const GATEWAY_RAG_SEARCH_URL =
  '/api/proxy/plugin/cywell-aiops-console-plugin/ai-gateway/v1/rag/search';
const GATEWAY_AUTH_SUBJECT_URL =
  '/api/proxy/plugin/cywell-aiops-console-plugin/ai-gateway/v1/auth/subject';
const GATEWAY_ACTIONS_URL =
  '/api/proxy/plugin/cywell-aiops-console-plugin/ai-gateway/v1/actions';
const CONSOLE_SELF_USER_URL = '/api/kubernetes/apis/user.openshift.io/v1/users/~';
const GATEWAY_AUTH_ERROR_MESSAGE =
  'OpenShift 콘솔 사용자 인증이 만료되었거나 Gateway로 사용자 토큰이 전달되지 않았습니다. 콘솔을 새로고침하거나 다시 로그인한 뒤 다시 시도하세요.';

async function gatewayErrorMessage(
  response: Response,
  prefix: string,
  includeBody = false,
): Promise<string> {
  if (response.status === 401) {
    return GATEWAY_AUTH_ERROR_MESSAGE;
  }

  if (!includeBody) {
    return `${prefix}: ${response.status}`;
  }

  const detail = await gatewayResponseDetail(response);
  return `${prefix}: ${detail || `${response.status} ${response.statusText}`}`;
}

async function gatewayResponseDetail(response: Response): Promise<string> {
  const body = (await response.text()).trim();
  if (!body) {
    return '';
  }

  try {
    const payload = JSON.parse(body) as Record<string, unknown>;
    const detail = payload.detail ?? payload.message ?? payload.error;
    if (typeof detail === 'string') {
      if (detail === 'separation of duties requires requester and approver to differ') {
        return '승인 실패: 요청자와 승인자는 달라야 합니다. 다른 운영자 계정으로 승인하거나 새 승인 절차를 시작하세요.';
      }
      if (detail === 'Action plan already has an active approval') {
        return '승인 실패: 이미 활성 승인 기록이 있습니다. 실행 기록에서 현재 승인 상태를 확인하세요.';
      }
      if (detail === 'Action plan has been rejected') {
        return '승인 실패: 이미 거절된 계획입니다. 새 조치 계획을 다시 생성하세요.';
      }
      if (detail === 'expectedPlanDigest does not match the sealed plan') {
        return '승인 실패: 화면의 계획 digest가 현재 sealed plan과 다릅니다. 새로고침 후 다시 확인하세요.';
      }
      if (detail === 'lab-auto-unrestricted approval requires unrestricted command gate') {
        return '실행 무제한 승인 실패: Gateway가 실행 무제한 capability를 허용하지 않았습니다.';
      }
      return detail.slice(0, 240);
    }
  } catch {
    // Fall through to the plain body. Gateway errors are often JSON, proxies are not.
  }

  if (body.includes('separation of duties requires requester and approver to differ')) {
    return '승인 실패: 요청자와 승인자는 달라야 합니다. 다른 운영자 계정으로 승인하거나 새 승인 절차를 시작하세요.';
  }

  return body.slice(0, 240);
}

async function postGatewayJson<TResponse>(
  path: string,
  payload: Record<string, unknown>,
): Promise<TResponse> {
  const response = await consoleFetch(
    `${GATEWAY_ACTIONS_URL}${path}`,
    {
      body: JSON.stringify(payload),
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      method: 'POST',
    },
    60 * 1000,
  );

  if (!response.ok) {
    throw new Error(await gatewayErrorMessage(response, 'AIOps action request failed', true));
  }

  return (await response.json()) as TResponse;
}

export async function fetchClusterSummary(): Promise<ClusterSummary> {
  const response = await consoleFetch(
    GATEWAY_CLUSTER_SUMMARY_URL,
    {
      headers: {
        Accept: 'application/json',
      },
      method: 'GET',
    },
    30 * 1000,
  );

  if (!response.ok) {
    throw new Error(await gatewayErrorMessage(response, 'Cluster summary request failed'));
  }

  return (await response.json()) as ClusterSummary;
}

export async function fetchAiopsOverview(): Promise<AiopsOverview> {
  const response = await consoleFetch(
    GATEWAY_AIOPS_OVERVIEW_URL,
    {
      headers: {
        Accept: 'application/json',
      },
      method: 'GET',
    },
    30 * 1000,
  );

  if (!response.ok) {
    throw new Error(await gatewayErrorMessage(response, 'AIOps overview request failed'));
  }

  return (await response.json()) as AiopsOverview;
}

export async function submitChatFeedback(
  payload: ChatFeedbackPayload,
): Promise<ChatFeedbackResult> {
  const response = await consoleFetch(
    GATEWAY_CHAT_FEEDBACK_URL,
    {
      body: JSON.stringify(payload),
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      method: 'POST',
    },
    30 * 1000,
  );

  if (!response.ok) {
    throw new Error(await gatewayErrorMessage(response, 'Chat feedback request failed', true));
  }

  return (await response.json()) as ChatFeedbackResult;
}

export async function fetchActionCandidates(): Promise<AiopsActionCandidateSummary> {
  const response = await consoleFetch(
    GATEWAY_AIOPS_ACTION_CANDIDATES_URL,
    {
      headers: {
        Accept: 'application/json',
      },
      method: 'GET',
    },
    30 * 1000,
  );

  if (!response.ok) {
    throw new Error(await gatewayErrorMessage(response, 'AIOps action candidates request failed'));
  }

  return (await response.json()) as AiopsActionCandidateSummary;
}

export async function fetchAiopsStatus(): Promise<AiopsRuntimeStatus> {
  const response = await consoleFetch(
    GATEWAY_AIOPS_STATUS_URL,
    {
      headers: {
        Accept: 'application/json',
      },
      method: 'GET',
    },
    30 * 1000,
  );

  if (!response.ok) {
    throw new Error(await gatewayErrorMessage(response, 'AIOps status request failed'));
  }

  return (await response.json()) as AiopsRuntimeStatus;
}

export async function uploadRagDocument(
  payload: RagDocumentUploadRequest,
): Promise<RagUploadIngestionResult> {
  const response = await consoleFetch(
    GATEWAY_RAG_UPLOADS_URL,
    {
      body: JSON.stringify(payload),
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      method: 'POST',
    },
    60 * 1000,
  );

  if (!response.ok) {
    throw new Error(await gatewayErrorMessage(response, 'RAG document upload failed', true));
  }

  return (await response.json()) as RagUploadIngestionResult;
}

export async function uploadRagDocumentFile(
  file: File,
  metadata: RagDocumentUploadFileMetadata = {},
): Promise<RagUploadIngestionResult> {
  const formData = new FormData();
  formData.append('file', file, file.name);
  formData.append('labels', JSON.stringify(metadata.labels ?? {}));
  formData.append('customer', metadata.customer ?? 'komsco');
  formData.append('namespace', metadata.namespace ?? 'cywell-aiops');
  formData.append('source_type', metadata.sourceType ?? 'user-upload');
  formData.append('version', metadata.version ?? 'v0.1.5');

  if (metadata.runId) {
    formData.append('run_id', metadata.runId);
  }
  if (metadata.sourceUri) {
    formData.append('source_uri', metadata.sourceUri);
  }

  const response = await consoleFetch(
    `${GATEWAY_RAG_UPLOADS_URL}/file`,
    {
      body: formData,
      headers: {
        Accept: 'application/json',
      },
      method: 'POST',
    },
    120 * 1000,
  );

  if (!response.ok) {
    throw new Error(await gatewayErrorMessage(response, 'RAG document file upload failed', true));
  }

  return (await response.json()) as RagUploadIngestionResult;
}

export async function fetchUploadedRagDocuments(): Promise<RagUploadedDocumentList> {
  const response = await consoleFetch(
    GATEWAY_RAG_UPLOADS_URL,
    {
      headers: {
        Accept: 'application/json',
      },
      method: 'GET',
    },
    30 * 1000,
  );

  if (!response.ok) {
    throw new Error(await gatewayErrorMessage(response, 'Uploaded RAG document request failed'));
  }

  return (await response.json()) as RagUploadedDocumentList;
}

export async function searchRagDocuments(payload: RagSearchRequest): Promise<RagSearchResult> {
  const response = await consoleFetch(
    GATEWAY_RAG_SEARCH_URL,
    {
      body: JSON.stringify(payload),
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      method: 'POST',
    },
    30 * 1000,
  );

  if (!response.ok) {
    throw new Error(await gatewayErrorMessage(response, 'RAG document search failed'));
  }

  return (await response.json()) as RagSearchResult;
}

export async function fetchAuthSubject(): Promise<AuthSubject> {
  const response = await consoleFetch(
    GATEWAY_AUTH_SUBJECT_URL,
    {
      headers: {
        Accept: 'application/json',
      },
      method: 'GET',
    },
    30 * 1000,
  );

  if (!response.ok) {
    throw new Error(await gatewayErrorMessage(response, 'Auth subject request failed'));
  }

  return (await response.json()) as AuthSubject;
}

export async function fetchConsoleUserSubject(): Promise<AuthSubject> {
  const response = await consoleFetch(
    CONSOLE_SELF_USER_URL,
    {
      headers: {
        Accept: 'application/json',
      },
      method: 'GET',
    },
    30 * 1000,
  );

  if (!response.ok) {
    throw new Error(await gatewayErrorMessage(response, 'Console user request failed'));
  }

  const payload = (await response.json()) as {
    groups?: string[];
    identities?: string[];
    metadata?: {
      name?: string;
      uid?: string;
    };
  };

  return {
    groups: payload.groups ?? [],
    uid: payload.metadata?.uid,
    username: payload.metadata?.name || payload.identities?.[0] || 'unknown',
  };
}

export async function createActionPlan(proposalId: string): Promise<AiopsRecord> {
  return postGatewayJson<AiopsRecord>('/plans', { proposalId });
}

export async function createActionCandidatePlan(
  candidate: AiopsActionCandidate,
  context?: { incidentId?: string; runId?: string },
): Promise<AiopsActionCandidatePlanResult> {
  const target = candidate.target ?? {};
  return postGatewayJson<AiopsActionCandidatePlanResult>('/candidate-plans', {
    candidateId: candidate.id,
    evidenceRefs: candidate.evidenceRefs ?? [],
    incidentId: context?.incidentId,
    runId: context?.runId,
    sourceFindingId: candidate.sourceFindingId,
    sourceType: candidate.sourceType,
    target: {
      apiVersion:
        target.apiVersion ??
        (target.kind === 'Namespace'
          ? 'v1'
          : target.kind === 'Pod'
          ? 'v1'
          : target.kind === 'HorizontalPodAutoscaler'
            ? 'autoscaling/v2'
            : 'apps/v1'),
      kind: target.kind ?? 'Deployment',
      name: target.name ?? candidate.title,
      namespace: target.namespace,
    },
    title: candidate.title,
  });
}

export async function approveActionPlan(
  planId: string,
  expectedPlanDigest: string,
  approvalScope = 'single-target',
): Promise<AiopsRecord> {
  return postGatewayJson<AiopsRecord>('/approvals', {
    approvalScope,
    expectedPlanDigest,
    planId,
  });
}

export async function rejectActionPlan(
  planId: string,
  expectedPlanDigest: string,
  reason = 'operator rejected the proposed action',
): Promise<AiopsRecord> {
  return postGatewayJson<AiopsRecord>('/rejections', {
    expectedPlanDigest,
    planId,
    reason,
  });
}

export async function executeApprovedAction(
  approvalId: string,
  planId: string,
  expectedPlanDigest: string,
): Promise<AiopsRecord> {
  return postGatewayJson<AiopsRecord>('/execute', {
    approvalId,
    expectedPlanDigest,
    planId,
  });
}

export async function* streamChat(
  payload: ChatRequest,
  options: StreamChatOptions = {},
): AsyncGenerator<StreamEvent> {
  const response = await consoleFetch(
    GATEWAY_STREAM_URL,
    {
      method: 'POST',
      headers: {
        Accept: 'text/event-stream',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
      signal: options.signal,
    },
    5 * 60 * 1000,
  );

  if (!response.ok) {
    throw new Error(await gatewayErrorMessage(response, 'AI Gateway request failed'));
  }

  if (!response.body) {
    throw new Error('AI Gateway streaming response body is empty.');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });

    const frames = buffer.split('\n\n');
    buffer = frames.pop() || '';

    for (const frame of frames) {
      const dataLines = frame
        .split('\n')
        .filter((line) => line.startsWith('data:'))
        .map((line) => line.slice('data:'.length).trim());

      if (dataLines.length === 0) {
        continue;
      }

      const raw = dataLines.join('\n');
      if (raw === '[DONE]') {
        yield { type: 'end' };
        return;
      }

      yield JSON.parse(raw) as StreamEvent;
    }
  }
}
