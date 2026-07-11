import type { AiopsEventFeed, AiopsRuntimeStatus, ClusterSummary } from '../types';

export type V2Runtime = {
  error: string;
  events: AiopsEventFeed;
  isLive: boolean;
  loading: boolean;
  refresh: (options?: { silent?: boolean }) => Promise<void>;
  status: AiopsRuntimeStatus;
  summary: ClusterSummary;
};
