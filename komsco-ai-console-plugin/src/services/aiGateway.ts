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
    kind?: string;
    name?: string;
    namespace?: string;
  };
  title: string;
  verificationChecks?: string[];
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
      mode: 'read-only' | string;
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
      readOnlyDefault?: boolean;
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
      mode: 'controlled_execution' | 'read_only' | string;
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
      fallbackAnswer?: boolean;
      gatewayContextDigest?: string;
      source?: string;
      streamProbe?: string;
    }
  | { type: 'end'; conversationId?: string }
  | { type: 'error'; message: string };

const GATEWAY_STREAM_URL = '/api/proxy/plugin/komsco-ai-console-plugin-kugnus/ai-gateway/v1/chat/stream';
const GATEWAY_CLUSTER_SUMMARY_URL =
  '/api/proxy/plugin/komsco-ai-console-plugin-kugnus/ai-gateway/v1/cluster/summary';
const GATEWAY_AIOPS_OVERVIEW_URL =
  '/api/proxy/plugin/komsco-ai-console-plugin-kugnus/ai-gateway/v1/aiops/overview';
const GATEWAY_AIOPS_STATUS_URL =
  '/api/proxy/plugin/komsco-ai-console-plugin-kugnus/ai-gateway/v1/aiops/status';
const GATEWAY_AUTH_SUBJECT_URL =
  '/api/proxy/plugin/komsco-ai-console-plugin-kugnus/ai-gateway/v1/auth/subject';
const GATEWAY_ACTIONS_URL = '/api/proxy/plugin/komsco-ai-console-plugin-kugnus/ai-gateway/v1/actions';
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

  const detail = await response.text();
  return `${prefix}: ${response.status} ${detail.slice(0, 240)}`;
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

export async function approveActionPlan(
  planId: string,
  expectedPlanDigest: string,
): Promise<AiopsRecord> {
  return postGatewayJson<AiopsRecord>('/approvals', {
    approvalScope: 'single-target',
    expectedPlanDigest,
    planId,
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
