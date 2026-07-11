import * as React from 'react';
import type { LightspeedStatusUpdate } from './assistant.types';
import {
  createPendingAiopsStatus,
  mergeAiopsRecordsIntoStatus,
  mergeAiopsRecordUpdates,
  type AiopsRuntimeRecordUpdates,
} from './assistant.aiopsRuntimeStatus';
import {
  type AiopsRuntimeStatus,
  type AuthSubject,
  fetchAiopsStatus,
  fetchConsoleUserSubject,
} from '../services/aiGateway';

type UseAssistantAiopsRuntimeStatusOptions = {
  open: boolean;
  refreshIntervalMs: number;
};

const errorMessage = (error: unknown, fallback: string): string =>
  error instanceof Error ? error.message : fallback;

export const useAssistantAiopsRuntimeStatus = ({
  open,
  refreshIntervalMs,
}: UseAssistantAiopsRuntimeStatusOptions) => {
  const [aiopsStatus, setAiopsStatus] = React.useState<AiopsRuntimeStatus | null>(null);
  const [aiopsStatusError, setAiopsStatusError] = React.useState('');
  const [authSubject, setAuthSubject] = React.useState<AuthSubject | null>(null);
  const [authSubjectError, setAuthSubjectError] = React.useState('');
  const optimisticRecordsRef = React.useRef<AiopsRuntimeRecordUpdates>({});
  const requestSequenceRef = React.useRef(0);

  const applyFetchedStatus = React.useCallback((status: AiopsRuntimeStatus) => {
    const mergedStatus = mergeAiopsRecordsIntoStatus(status, optimisticRecordsRef.current, false);
    setAiopsStatus(mergedStatus);
    setAiopsStatusError('');
    return mergedStatus;
  }, []);

  const refreshAiopsRuntimeStatus = React.useCallback(async () => {
    const sequence = ++requestSequenceRef.current;
    try {
      const status = await fetchAiopsStatus();
      if (sequence !== requestSequenceRef.current) {
        return null;
      }
      return applyFetchedStatus(status);
    } catch (error) {
      if (sequence !== requestSequenceRef.current) {
        return null;
      }
      setAiopsStatusError(errorMessage(error, 'AIOps status request failed.'));
      return null;
    }
  }, [applyFetchedStatus]);

  React.useEffect(() => {
    if (!open) {
      return undefined;
    }

    let disposed = false;
    const loadRuntimeContext = async () => {
      const sequence = ++requestSequenceRef.current;
      const [statusResult, consoleUserResult] = await Promise.allSettled([
        fetchAiopsStatus(),
        fetchConsoleUserSubject(),
      ]);
      if (disposed || sequence !== requestSequenceRef.current) {
        return;
      }

      if (statusResult.status === 'fulfilled') {
        applyFetchedStatus(statusResult.value);
        const subject = statusResult.value.spec.subject;
        if (subject) {
          setAuthSubject(subject);
          setAuthSubjectError('');
        } else if (consoleUserResult.status === 'fulfilled') {
          setAuthSubject(consoleUserResult.value);
          setAuthSubjectError('');
        } else {
          setAuthSubject(null);
          setAuthSubjectError('Subject not returned by status endpoint.');
        }
      } else {
        const statusError = errorMessage(statusResult.reason, 'AIOps status request failed.');
        setAiopsStatusError(statusError);
        if (consoleUserResult.status === 'fulfilled') {
          setAuthSubject(consoleUserResult.value);
          setAuthSubjectError('');
        } else {
          setAuthSubject(null);
          setAuthSubjectError(statusError);
        }
      }
    };

    void loadRuntimeContext();
    const timer = window.setInterval(() => {
      void loadRuntimeContext();
    }, refreshIntervalMs);

    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, [applyFetchedStatus, open, refreshIntervalMs]);

  const updateLightspeedStatus = React.useCallback((updates: LightspeedStatusUpdate) => {
    setAiopsStatus((current) => {
      const base = current ?? createPendingAiopsStatus();
      const safetyContract =
        base.spec.safetyContract ?? createPendingAiopsStatus().spec.safetyContract!;
      return {
        ...base,
        spec: {
          ...base.spec,
          safetyContract: {
            ...safetyContract,
            lightspeedStatus: {
              ...(safetyContract.lightspeedStatus ?? {}),
              ...updates,
            },
          },
        },
      };
    });
  }, []);

  const upsertAiopsRuntimeRecords = React.useCallback((updates: AiopsRuntimeRecordUpdates) => {
    optimisticRecordsRef.current = mergeAiopsRecordUpdates(optimisticRecordsRef.current, updates);
    setAiopsStatus((current) =>
      mergeAiopsRecordsIntoStatus(current ?? createPendingAiopsStatus(), updates),
    );
  }, []);

  return {
    aiopsStatus,
    aiopsStatusError,
    authSubject,
    authSubjectError,
    refreshAiopsRuntimeStatus,
    setAiopsStatus,
    updateLightspeedStatus,
    upsertAiopsRuntimeRecords,
  };
};
