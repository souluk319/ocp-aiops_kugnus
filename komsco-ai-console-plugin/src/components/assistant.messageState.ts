import { MAX_RECENT_CONTEXT_MESSAGES } from './assistant.constants';
import { languageLocale } from './assistant.storage';
import type { EvidenceFooter, Message, ToolPlanFooter, UiLanguage } from './assistant.types';
import type { AiopsRuntimeStatus, ChatContextMessage, ClusterSummary } from '../services/aiGateway';

export const findLastAssistantIndex = (messages: Message[]): number => {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index].role === 'assistant') {
      return index;
    }
  }

  return -1;
};

export const setLastAssistantContentIfEmpty = (
  messages: Message[],
  content: string,
): Message[] => {
  const assistantIndex = findLastAssistantIndex(messages);
  if (assistantIndex < 0 || messages[assistantIndex].content.trim()) {
    return messages;
  }

  const next = [...messages];
  next[assistantIndex] = {
    ...next[assistantIndex],
    content,
    evidenceFooter: undefined,
    timestamp: next[assistantIndex].timestamp ?? Date.now(),
  };

  return next;
};

export const markLastAssistantStreaming = (
  messages: Message[],
  streaming: boolean,
): Message[] => {
  const assistantIndex = findLastAssistantIndex(messages);
  if (assistantIndex < 0) {
    return messages;
  }

  const next = [...messages];
  next[assistantIndex] = {
    ...next[assistantIndex],
    streaming,
    timestamp: next[assistantIndex].timestamp ?? Date.now(),
  };

  return next;
};

export const attachEvidenceFooterToLastAssistant = (
  messages: Message[],
  evidenceFooter: EvidenceFooter | undefined,
): Message[] => {
  if (!evidenceFooter) {
    return messages;
  }

  const assistantIndex = findLastAssistantIndex(messages);
  if (assistantIndex < 0) {
    return messages;
  }

  const next = [...messages];
  next[assistantIndex] = {
    ...next[assistantIndex],
    evidenceFooter,
  };

  return next;
};

export const attachToolPlanToLastAssistant = (
  messages: Message[],
  toolPlan: ToolPlanFooter | undefined,
): Message[] => {
  if (!toolPlan) {
    return messages;
  }

  const assistantIndex = findLastAssistantIndex(messages);
  if (assistantIndex < 0) {
    return messages;
  }

  const next = [...messages];
  next[assistantIndex] = {
    ...next[assistantIndex],
    toolPlan,
  };

  return next;
};

export const markLastAssistantFallback = (
  messages: Message[],
  gatewayContextDigest?: string,
): Message[] => {
  const assistantIndex = findLastAssistantIndex(messages);
  if (assistantIndex < 0) {
    return messages;
  }

  const next = [...messages];
  next[assistantIndex] = {
    ...next[assistantIndex],
    answerSource: 'gateway_fallback',
    fallbackAnswer: true,
    gatewayContextDigest: gatewayContextDigest || next[assistantIndex].gatewayContextDigest,
  };

  return next;
};

export const markLastAssistantSource = (
  messages: Message[],
  answerSource: NonNullable<Message['answerSource']>,
  gatewayContextDigest?: string,
): Message[] => {
  const assistantIndex = findLastAssistantIndex(messages);
  if (assistantIndex < 0) {
    return messages;
  }

  const next = [...messages];
  next[assistantIndex] = {
    ...next[assistantIndex],
    answerSource,
    gatewayContextDigest: gatewayContextDigest || next[assistantIndex].gatewayContextDigest,
  };

  return next;
};

export const markLastAssistantAnswerContract = (
  messages: Message[],
  answerContract?: string,
): Message[] => {
  if (!answerContract) {
    return messages;
  }

  const assistantIndex = findLastAssistantIndex(messages);
  if (assistantIndex < 0) {
    return messages;
  }

  const next = [...messages];
  next[assistantIndex] = {
    ...next[assistantIndex],
    answerContract,
  };

  return next;
};

export const buildRecentContextMessages = (messages: Message[]): ChatContextMessage[] =>
  messages
    .filter((message) => message.content.trim())
    .slice(-MAX_RECENT_CONTEXT_MESSAGES)
    .map((message) => ({
      role: message.role,
      content: message.content.slice(0, 4000),
    }));

export const formatMessageTime = (
  timestamp: number | undefined,
  language: UiLanguage,
): string => {
  if (!timestamp) {
    return '';
  }

  return new Intl.DateTimeFormat(languageLocale(language), {
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(timestamp));
};

export const getAssistantConnectionState = (
  summary: ClusterSummary | null,
  summaryLoading: boolean,
  summaryError: string,
  status: AiopsRuntimeStatus | null,
  statusError: string,
): { label: string; tone: 'connected' | 'danger' | 'pending' } => {
  if (summaryError || statusError) {
    return {
      label: 'Gateway 또는 cluster 상태 확인 필요',
      tone: 'danger',
    };
  }

  if (summary && status) {
    return {
      label: `${summary.apiUrl || 'console proxy'} · Gateway 연결됨`,
      tone: 'connected',
    };
  }

  if (summary || status) {
    return {
      label: `${summary?.apiUrl || 'cluster'} · 연결 일부 확인됨`,
      tone: 'pending',
    };
  }

  return {
    label: summaryLoading ? '연결 확인 중' : 'Gateway 연결 대기',
    tone: 'pending',
  };
};
