import { consoleFetch } from '@openshift-console/dynamic-plugin-sdk';

type ChatRequest = {
  message: string;
  attachments?: ImageAttachment[];
  pageContext?: Record<string, unknown>;
  conversationId?: string;
  runId?: string;
};

export type ImageAttachment = {
  data: string;
  id: string;
  mimeType: string;
  name: string;
  size: number;
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
    throw new Error(`Cluster summary request failed: ${response.status}`);
  }

  return (await response.json()) as ClusterSummary;
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
    throw new Error(`AI Gateway request failed: ${response.status}`);
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
