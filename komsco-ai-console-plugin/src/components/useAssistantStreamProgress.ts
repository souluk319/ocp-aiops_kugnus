import * as React from 'react';
import type { Message, ProgressStep } from './assistant.types';

type AssistantProgressAction =
  | { type: 'upsert'; step: ProgressStep }
  | { type: 'fail-running'; summary: string }
  | { type: 'finalize-running'; summary: string };

type UseAssistantStreamProgressOptions = {
  loading: boolean;
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>;
};

const findLastAssistantIndex = (messages: Message[]): number => {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index].role === 'assistant') {
      return index;
    }
  }

  return -1;
};

const reduceAssistantProgress = (
  messages: Message[],
  action: AssistantProgressAction,
): Message[] => {
  const assistantIndex = findLastAssistantIndex(messages);
  if (assistantIndex < 0) {
    return messages;
  }

  const next = [...messages];
  const message = next[assistantIndex];

  if (action.type === 'upsert') {
    const progressSteps = [...(message.progressSteps ?? [])];
    const existingIndex = progressSteps.findIndex((item) => item.id === action.step.id);

    if (existingIndex >= 0) {
      progressSteps[existingIndex] = {
        ...progressSteps[existingIndex],
        ...action.step,
        startedAt: progressSteps[existingIndex].startedAt,
      };
    } else {
      progressSteps.push(action.step);
    }

    next[assistantIndex] = {
      ...message,
      progressSteps,
    };
    return next;
  }

  next[assistantIndex] = {
    ...message,
    progressSteps: message.progressSteps?.map((step) => {
      if (step.status !== 'running') {
        return step;
      }

      const endedAt = Date.now();

      if (action.type === 'fail-running') {
        return {
          ...step,
          detail: step.detail || action.summary,
          elapsedMs: endedAt - step.startedAt,
          endedAt,
          status: 'failed',
          summary: action.summary,
        };
      }

      return {
        ...step,
        detail: step.detail || action.summary,
        elapsedMs: endedAt - step.startedAt,
        endedAt,
        status: 'completed',
        summary: action.summary,
      };
    }),
  };

  return next;
};

export const useAssistantStreamProgress = ({
  loading,
  setMessages,
}: UseAssistantStreamProgressOptions) => {
  const [, setProgressTick] = React.useState(0);

  React.useEffect(() => {
    if (!loading) {
      return undefined;
    }

    const timer = window.setInterval(() => {
      setProgressTick((value) => value + 1);
    }, 1000);

    return () => window.clearInterval(timer);
  }, [loading]);

  const upsertProgressStep = React.useCallback(
    (step: ProgressStep) => {
      setMessages((messages) => reduceAssistantProgress(messages, { type: 'upsert', step }));
    },
    [setMessages],
  );

  const markRunningProgressFailed = React.useCallback(
    (summary: string) => {
      setMessages((messages) =>
        reduceAssistantProgress(messages, { type: 'fail-running', summary }),
      );
    },
    [setMessages],
  );

  const finalizeRunningProgressSteps = React.useCallback(
    (summary = '응답 완료') => {
      setMessages((messages) =>
        reduceAssistantProgress(messages, { type: 'finalize-running', summary }),
      );
    },
    [setMessages],
  );

  return {
    finalizeRunningProgressSteps,
    markRunningProgressFailed,
    upsertProgressStep,
  } as const;
};
