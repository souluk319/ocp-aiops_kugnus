import { consoleFetch } from '@openshift-console/dynamic-plugin-sdk';

import type { AiopsEventFeed, AiopsRuntimeStatus, ClusterSummary } from './types';

const GATEWAY_PROXY_BASE =
  '/api/proxy/plugin/cywell-aiops-console-plugin/ai-gateway';

async function requestJson<T>(path: string): Promise<T> {
  const response = await consoleFetch(`${GATEWAY_PROXY_BASE}${path}`, {
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`${path} failed: ${response.status} ${detail.slice(0, 180)}`);
  }

  return (await response.json()) as T;
}

export async function fetchClusterSummary(): Promise<ClusterSummary> {
  return requestJson<ClusterSummary>('/v1/cluster/summary');
}

export async function fetchAiopsStatus(): Promise<AiopsRuntimeStatus> {
  return requestJson<AiopsRuntimeStatus>('/v1/aiops/status');
}

export async function fetchAiopsEvents(): Promise<AiopsEventFeed> {
  return requestJson<AiopsEventFeed>('/v1/aiops/events');
}
