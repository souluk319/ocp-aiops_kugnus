export type NavView =
  | 'dashboard'
  | 'executions'
  | 'rca'
  | 'service-map'
  | 'endpoints'
  | 'alerts'
  | 'wiki'
  | 'reports'
  | 'settings';

export type Severity = 'ok' | 'warn' | 'risk';

export type ClusterSummary = {
  aiopsWorkloads?: {
    daemonsets: AiopsWorkload[];
    deployments: AiopsWorkload[];
    issues: number;
    namespaces?: string[];
    total: number;
  };
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
  resources?: {
    issues: number;
    items: Array<{
      detail: string;
      id: string;
      issues: number;
      kind: string;
      name: string;
      ready: number | string;
      score: string;
      severity: Severity;
      total: number;
    }>;
    total: number;
  };
  updatedAt: string;
  version: {
    availableUpdates?: string[];
    channel?: string;
    conditionalUpdates?: string[];
    updateAvailable: boolean;
    upgradeable?: boolean | null;
    upgradeableMessage?: string;
    upgradeableReason?: string;
    version?: string;
  };
};

export type AiopsWorkload = {
  available: number;
  createdAt?: string;
  desired: number;
  detail: string;
  kind: 'Deployment' | 'DaemonSet';
  name: string;
  namespace: string;
  ready: number;
  severity: Severity;
  updated: number;
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
      rag?: Record<string, unknown>;
      recordStoreConfigMap?: string;
      recordStoreEnabled: boolean;
      safetyContract?: Record<string, unknown>;
      unrestrictedCommandsEnabled?: boolean;
    };
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
    accessReviewStatus?: Record<string, unknown>;
    productAccessReview?: Record<string, unknown>;
    subject?: Record<string, unknown>;
  };
};

export type AiopsEventItem = {
  category: string;
  detail: string;
  id: string;
  namespace?: string;
  severity: Severity;
  source: string;
  target?: string;
  time?: string;
  title: string;
};

export type AiopsEventFeed = {
  metadata?: {
    generatedAt?: string;
    name?: string;
  };
  spec: {
    items: AiopsEventItem[];
    pollIntervalSeconds?: number;
    sources?: string[];
  };
};

export type ScopeItem = {
  detailRows?: Array<{
    label: string;
    value: string;
  }>;
  id: string;
  keywords?: string[];
  name: string;
  detail: string;
  score: string;
  severity: Severity;
};

export type QueueItem = {
  id: string;
  title: string;
  detail: string;
  evidence: string[];
  category?: string;
  source?: string;
  target?: string;
  updatedAt?: string;
  severity: Exclude<Severity, 'ok'>;
};

export type Endpoint = {
  id: string;
  name: string;
  type: string;
  group: string;
  severity: Severity;
  cpu: string;
  memory: string;
  latency: string;
  lastEvent: string;
  path: string;
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

export type RagUploadedDocumentList = {
  apiVersion?: string;
  kind?: 'RagUploadedDocumentList' | string;
  metadata?: {
    generatedAt?: string;
    name?: string;
  };
  spec: {
    backend?: AiopsRuntimeStatus['spec']['capabilities']['rag'];
    documents?: RagUploadedDocument[];
    items?: RagUploadedDocument[];
    reason?: string;
    status?: 'collected' | 'empty' | 'not_configured' | 'unavailable' | string;
    totals?: {
      documents?: number;
    };
  };
};

export type RagSearchResultItem = {
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

export type RagSearchResult = {
  apiVersion?: string;
  kind?: 'RagSearchResult' | string;
  metadata?: {
    generatedAt?: string;
    name?: string;
  };
  spec: {
    query?: string;
    reason?: string;
    results?: RagSearchResultItem[];
    safety?: Record<string, unknown>;
    status?: 'collected' | 'empty' | 'not_configured' | 'unavailable' | string;
    topK?: number;
  };
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
      chunkId?: string;
      chunkIndex?: number;
      sourceUri?: string;
      textHash?: string;
    }>;
    document: RagUploadedDocument;
    ingestionReport?: Record<string, unknown>;
    reason?: string;
    safety?: Record<string, unknown>;
    status?: 'persisted' | 'not_configured' | 'unavailable' | string;
  };
};

export type AlertItem = {
  id: string;
  title: string;
  target: string;
  severity: Exclude<Severity, 'ok'>;
  time: string;
};

export type ActivityItem = {
  category?: string;
  id: string;
  title: string;
  detail: string;
  source?: string;
  target?: string;
  time?: string;
  tone: 'red' | 'orange' | 'green' | 'blue' | 'violet';
};

export type PortalData = {
  activities: ActivityItem[];
  alerts: AlertItem[];
  endpoints: Endpoint[];
  queues: QueueItem[];
  scopes: ScopeItem[];
};
