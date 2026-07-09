import * as React from 'react';
import { fetchAiopsEvents, fetchAiopsStatus, fetchClusterSummary } from './api';
import type { AiopsEventFeed, AiopsRuntimeStatus, ClusterSummary } from './types';

export type RuntimeState = {
  readonly error: string;
  readonly events: AiopsEventFeed;
  readonly isLive: boolean;
  readonly loading: boolean;
  readonly refresh: (options?: { readonly silent?: boolean }) => Promise<void>;
  readonly status: AiopsRuntimeStatus;
  readonly summary: ClusterSummary;
};

const emptySummary: ClusterSummary = {
  aiopsWorkloads: {
    daemonsets: [],
    deployments: [],
    issues: 0,
    namespaces: [],
    total: 0,
  },
  healthScore: 0,
  nodes: {
    total: 0,
    ready: 0,
    notReady: 0,
    pressureCount: 0,
    metricsAvailable: false,
    items: [],
  },
  operators: {
    available: 0,
    degraded: 0,
    progressing: 0,
    total: 0,
    unavailable: 0,
    issues: [],
  },
  resources: {
    issues: 0,
    items: [],
    total: 0,
  },
  updatedAt: '',
  version: {
    updateAvailable: false,
  },
};

const emptyStatus: AiopsRuntimeStatus = {
  spec: {
    capabilities: {
      actionExecutorConfigured: false,
      diagnosticsControllerConfigured: false,
      diagnosticsEnabled: false,
      mutationsEnabled: false,
      recordStoreEnabled: false,
      unrestrictedCommandsEnabled: false,
    },
    records: {
      actionProposals: [],
      auditRecords: [],
      approvalDecisions: [],
      chatFeedback: [],
      diagnosticRequests: [],
      executionRecords: [],
      sealedActionPlans: [],
    },
  },
};

const emptyEventFeed: AiopsEventFeed = {
  metadata: {
    name: 'activity-feed',
  },
  spec: {
    items: [],
    pollIntervalSeconds: 30,
    sources: [],
  },
};

export const useLiveClock = (): string => {
  const [clock, setClock] = React.useState(() =>
    new Date().toLocaleTimeString('ko-KR', { hour12: false }),
  );

  React.useEffect(() => {
    const timer = window.setInterval(() => {
      setClock(new Date().toLocaleTimeString('ko-KR', { hour12: false }));
    }, 1000);

    return () => window.clearInterval(timer);
  }, []);

  return clock;
};

export const usePortalRuntime = (): RuntimeState => {
  const [summary, setSummary] = React.useState<ClusterSummary>(emptySummary);
  const [status, setStatus] = React.useState<AiopsRuntimeStatus>(emptyStatus);
  const [events, setEvents] = React.useState<AiopsEventFeed>(emptyEventFeed);
  const [loading, setLoading] = React.useState(true);
  const [isLive, setIsLive] = React.useState(false);
  const [error, setError] = React.useState('');

  const refresh = React.useCallback(async (options?: { readonly silent?: boolean }) => {
    const silent = options?.silent ?? false;
    if (!silent) {
      setLoading(true);
    }

    const [summaryResult, statusResult, eventResult] = await Promise.allSettled([
      fetchClusterSummary(),
      fetchAiopsStatus(),
      fetchAiopsEvents(),
    ]);

    if (summaryResult.status === 'fulfilled') {
      setSummary(summaryResult.value);
    }

    if (statusResult.status === 'fulfilled') {
      setStatus(statusResult.value);
    }

    if (eventResult.status === 'fulfilled') {
      setEvents(eventResult.value);
    }

    const errors = [summaryResult, statusResult, eventResult]
      .filter((result): result is PromiseRejectedResult => result.status === 'rejected')
      .map((result) => (result.reason instanceof Error ? result.reason.message : String(result.reason)));

    setIsLive(errors.length === 0);
    setError(errors.join('\n'));
    if (!silent) {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  React.useEffect(() => {
    const timer = window.setInterval(() => {
      void refresh({ silent: true });
    }, 30000);

    return () => window.clearInterval(timer);
  }, [refresh]);

  return { error, events, isLive, loading, refresh, status, summary };
};
