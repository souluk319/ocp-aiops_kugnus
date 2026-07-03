import type { AiopsEventFeed, AiopsRuntimeStatus, ClusterSummary } from './types';

const API_BASE_URL = (import.meta.env.VITE_AIOPS_API_BASE_URL ?? '').replace(/\/$/, '');

const readAuthHeader = (): string => {
  const token = window.localStorage.getItem('komsco-ai-portal-token');
  return token ? `Bearer ${token}` : '';
};

async function requestJson<T>(path: string): Promise<T> {
  const headers: HeadersInit = {
    Accept: 'application/json',
  };
  const authorization = readAuthHeader();

  if (authorization) {
    headers.Authorization = authorization;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers,
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
