import type { AiopsEventFeed, AiopsRuntimeStatus, ClusterSummary } from './types';

const API_BASE_URL = (import.meta.env.VITE_AIOPS_API_BASE_URL ?? '').replace(/\/$/, '');
const PORTAL_TOKEN_STORAGE_KEY = 'komsco-ai-portal-token';
export const usesProxyAuth = (import.meta.env.VITE_AIOPS_AUTH_MODE ?? 'token') === 'proxy';

const readAuthHeader = (): string => {
  if (usesProxyAuth) {
    return '';
  }
  const token = window.localStorage.getItem(PORTAL_TOKEN_STORAGE_KEY);
  return token ? `Bearer ${token}` : '';
};

const normalizeBearerToken = (value: string): string => value.trim().replace(/^Bearer\s+/i, '');

export async function connectOpenShiftToken(value: string): Promise<void> {
  if (usesProxyAuth) {
    throw new Error('배포 포털은 OpenShift OAuth 로그인을 사용합니다.');
  }
  const token = normalizeBearerToken(value);
  if (!token) {
    throw new Error('OpenShift 토큰을 입력하세요.');
  }

  const response = await fetch(`${API_BASE_URL}/v1/aiops/status`, {
    headers: {
      Accept: 'application/json',
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    throw new Error('토큰을 확인할 수 없습니다. OpenShift에서 새 토큰을 복사해 다시 입력하세요.');
  }

  window.localStorage.setItem(PORTAL_TOKEN_STORAGE_KEY, token);
}

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
