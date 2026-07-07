import { consoleFetch } from '@openshift-console/dynamic-plugin-sdk';

import type {
  AiopsEventFeed,
  AiopsRuntimeStatus,
  ClusterSummary,
  RagSearchResult,
  RagUploadedDocumentList,
  RagUploadIngestionResult,
} from './types';

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

export async function fetchRagUploadedDocuments(): Promise<RagUploadedDocumentList> {
  return requestJson<RagUploadedDocumentList>('/v1/rag/uploads');
}

export async function searchRagDocuments(query: string): Promise<RagSearchResult> {
  const response = await consoleFetch(`${GATEWAY_PROXY_BASE}/v1/rag/search`, {
    body: JSON.stringify({
      includeContent: false,
      query,
      topK: 3,
    }),
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    method: 'POST',
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`/v1/rag/search failed: ${response.status} ${detail.slice(0, 180)}`);
  }

  return (await response.json()) as RagSearchResult;
}

export async function uploadRagDocumentFile(file: File): Promise<RagUploadIngestionResult> {
  const formData = new FormData();
  formData.append('file', file, file.name);
  formData.append('labels', JSON.stringify({ source: 'portal-wiki-upload' }));
  formData.append('customer', 'komsco');
  formData.append('namespace', 'cywell-aiops');
  formData.append('source_type', 'user-upload');
  formData.append('version', 'v0.2.9');

  const response = await consoleFetch(`${GATEWAY_PROXY_BASE}/v1/rag/uploads/file`, {
    body: formData,
    headers: {
      Accept: 'application/json',
    },
    method: 'POST',
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`/v1/rag/uploads/file failed: ${response.status} ${detail.slice(0, 180)}`);
  }

  return (await response.json()) as RagUploadIngestionResult;
}
