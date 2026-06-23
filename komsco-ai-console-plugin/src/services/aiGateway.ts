import { consoleFetch } from '@openshift-console/dynamic-plugin-sdk';

type ChatRequest = {
  message: string;
  attachments?: ImageAttachment[];
  pageContext?: Record<string, unknown>;
  conversationId?: string;
  runId?: string;
  recentMessages?: ChatContextMessage[];
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

export type AiopsRecord = {
  kind?: string;
  metadata?: {
    createdAt?: string;
    name?: string;
  };
  spec?: Record<string, unknown>;
};

export type AiopsRuntimeStatus = {
  spec: {
    capabilities: {
      actionExecutorConfigured: boolean;
      diagnosticsControllerConfigured: boolean;
      diagnosticsEnabled: boolean;
      mutationsEnabled: boolean;
      recordStoreConfigMap?: string;
      recordStoreEnabled: boolean;
      unrestrictedCommandsEnabled?: boolean;
    };
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
  | { type: 'text'; content: string }
  | {
      type: 'run_status';
      elapsedMs?: number;
      message: string;
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
      result?: unknown;
      serverName?: string;
      status?: string;
      summary?: string;
    }
  | { type: 'end'; conversationId?: string }
  | { type: 'error'; message: string };

const GATEWAY_STREAM_URL = '/api/proxy/plugin/komsco-ai-console-plugin/ai-gateway/v1/chat/stream';
const GATEWAY_CLUSTER_SUMMARY_URL =
  '/api/proxy/plugin/komsco-ai-console-plugin/ai-gateway/v1/cluster/summary';
const GATEWAY_AIOPS_STATUS_URL =
  '/api/proxy/plugin/komsco-ai-console-plugin/ai-gateway/v1/aiops/status';
const GATEWAY_ACTIONS_URL = '/api/proxy/plugin/komsco-ai-console-plugin/ai-gateway/v1/actions';
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

export async function* streamChat(payload: ChatRequest): AsyncGenerator<StreamEvent> {
  const response = await consoleFetch(
    GATEWAY_STREAM_URL,
    {
      method: 'POST',
      headers: {
        Accept: 'text/event-stream',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
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
