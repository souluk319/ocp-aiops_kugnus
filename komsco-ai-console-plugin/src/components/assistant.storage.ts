import {
  MAX_STORED_CONVERSATIONS,
  STORED_ACTIVE_CONVERSATION_KEY,
  STORED_CONVERSATION_HISTORY_KEY,
  STORED_UI_LANGUAGE_KEY,
} from './assistant.constants';
import type {
  ConversationActionRef,
  ConversationHistoryItem,
  Message,
  StoredActiveConversation,
  UiLanguage,
} from './assistant.types';

export const createRunId = (): string =>
  `run-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;

export const getConversationTitle = (messages: Message[], language: UiLanguage): string => {
  const firstUserMessage = messages.find((message) => message.role === 'user');
  const content = firstUserMessage?.content.trim();

  if (!content && firstUserMessage?.attachments?.length) {
    return language === 'ko' ? '이미지 첨부 대화' : 'Image conversation';
  }

  if (!content) {
    return language === 'ko' ? '새 대화' : 'New conversation';
  }

  return content.length > 34 ? `${content.slice(0, 34)}...` : content;
};

const getAssistantStorage = (): Storage | null => {
  if (typeof window === 'undefined') {
    return null;
  }

  try {
    return window.localStorage;
  } catch {
    return null;
  }
};

const isStorageRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const readStoredJson = (key: string): unknown => {
  const storage = getAssistantStorage();
  if (!storage) {
    return undefined;
  }

  try {
    const raw = storage.getItem(key);
    return raw ? JSON.parse(raw) : undefined;
  } catch {
    return undefined;
  }
};

const writeStoredJson = (key: string, value: unknown): void => {
  const storage = getAssistantStorage();
  if (!storage) {
    return;
  }

  try {
    storage.setItem(key, JSON.stringify(value));
  } catch {
    // Browser storage is best-effort UI state. Gateway JSONL remains the audit source.
  }
};

const sanitizeMessageForStorage = (message: Message): Message => {
  const { attachments: _attachments, ...storedMessage } = message;
  return storedMessage;
};

const normalizeStoredMessage = (value: unknown): Message | undefined => {
  if (!isStorageRecord(value)) {
    return undefined;
  }

  const { role, content } = value;
  if (
    (role !== 'user' && role !== 'assistant' && role !== 'system') ||
    typeof content !== 'string'
  ) {
    return undefined;
  }

  return sanitizeMessageForStorage({
    ...(value as Message),
    content,
    role,
  });
};

const normalizeStoredMessages = (value: unknown): Message[] =>
  Array.isArray(value)
    ? value.flatMap((message) => {
        const normalized = normalizeStoredMessage(message);
        return normalized ? [normalized] : [];
      })
    : [];

const normalizeStoredActionRefs = (value: unknown): ConversationActionRef[] =>
  Array.isArray(value)
    ? value.flatMap((item) => {
        if (!isStorageRecord(item)) {
          return [];
        }

        const stage = String(item.stage || '');
        const targetKey = typeof item.targetKey === 'string' ? item.targetKey : '';
        const label = typeof item.label === 'string' ? item.label : '';
        const id = typeof item.id === 'string' ? item.id : '';
        if (
          !id ||
          !targetKey ||
          !label ||
          !['proposal', 'plan', 'approval', 'execution'].includes(stage)
        ) {
          return [];
        }

        return [
          {
            candidateId: typeof item.candidateId === 'string' ? item.candidateId : undefined,
            createdAt: typeof item.createdAt === 'string' ? item.createdAt : undefined,
            id,
            label,
            messageAnchor: typeof item.messageAnchor === 'string' ? item.messageAnchor : undefined,
            planDigest: typeof item.planDigest === 'string' ? item.planDigest : undefined,
            recordKind: typeof item.recordKind === 'string' ? item.recordKind : undefined,
            recordName: typeof item.recordName === 'string' ? item.recordName : undefined,
            reviewOnly: item.reviewOnly === true,
            stage: stage as ConversationActionRef['stage'],
            targetKey,
            toolName: typeof item.toolName === 'string' ? item.toolName : undefined,
            updatedAt:
              typeof item.updatedAt === 'number' && Number.isFinite(item.updatedAt)
                ? item.updatedAt
                : Date.now(),
          },
        ];
      })
    : [];

const normalizeStoredConversation = (value: unknown): ConversationHistoryItem | undefined => {
  if (!isStorageRecord(value)) {
    return undefined;
  }

  const messages = normalizeStoredMessages(value.messages);
  if (messages.length === 0) {
    return undefined;
  }

  const id = typeof value.id === 'string' && value.id ? value.id : createRunId();
  const title =
    typeof value.title === 'string' && value.title.trim()
      ? value.title
      : getConversationTitle(messages, 'ko');
  const updatedAt =
    typeof value.updatedAt === 'number' && Number.isFinite(value.updatedAt)
      ? value.updatedAt
      : Date.now();
  const conversationId =
    typeof value.conversationId === 'string' && value.conversationId
      ? value.conversationId
      : undefined;
  const actionTargetKeys = Array.isArray(value.actionTargetKeys)
    ? value.actionTargetKeys.filter((key): key is string => typeof key === 'string')
    : undefined;
  const actionRefs = normalizeStoredActionRefs(value.actionRefs);
  const pinned = value.pinned === true;

  return {
    actionRefs,
    actionTargetKeys,
    conversationId,
    id,
    messages,
    pinned,
    title,
    updatedAt,
  };
};

export const readStoredConversationHistory = (): ConversationHistoryItem[] => {
  const stored = readStoredJson(STORED_CONVERSATION_HISTORY_KEY);
  if (!Array.isArray(stored)) {
    return [];
  }

  return stored
    .flatMap((conversation) => {
      const normalized = normalizeStoredConversation(conversation);
      return normalized ? [normalized] : [];
    })
    .slice(0, MAX_STORED_CONVERSATIONS);
};

export const writeStoredConversationHistory = (
  conversationHistory: ConversationHistoryItem[],
): void => {
  writeStoredJson(
    STORED_CONVERSATION_HISTORY_KEY,
    conversationHistory.slice(0, MAX_STORED_CONVERSATIONS).map((conversation) => ({
      ...conversation,
      messages: conversation.messages.map(sanitizeMessageForStorage),
    })),
  );
};

export const readStoredActiveConversation = (): StoredActiveConversation | undefined => {
  const stored = readStoredJson(STORED_ACTIVE_CONVERSATION_KEY);
  if (!isStorageRecord(stored)) {
    return undefined;
  }

  const messages = normalizeStoredMessages(stored.messages);
  const activeSessionId =
    typeof stored.activeSessionId === 'string' && stored.activeSessionId
      ? stored.activeSessionId
      : createRunId();
  const conversationId =
    typeof stored.conversationId === 'string' && stored.conversationId
      ? stored.conversationId
      : undefined;
  const actionTargetKeys = Array.isArray(stored.actionTargetKeys)
    ? stored.actionTargetKeys.filter((key): key is string => typeof key === 'string')
    : undefined;
  const actionRefs = normalizeStoredActionRefs(stored.actionRefs);

  return {
    activeSessionId,
    actionRefs,
    actionTargetKeys,
    conversationId,
    messages,
  };
};

export const writeStoredActiveConversation = (snapshot: StoredActiveConversation): void => {
  writeStoredJson(STORED_ACTIVE_CONVERSATION_KEY, {
    ...snapshot,
    messages: snapshot.messages.map(sanitizeMessageForStorage),
  });
};

const normalizeUiLanguage = (value: unknown): UiLanguage =>
  value === 'en' || value === 'ko' ? value : 'ko';

export const readStoredUiLanguage = (): UiLanguage =>
  normalizeUiLanguage(readStoredJson(STORED_UI_LANGUAGE_KEY));

export const writeStoredUiLanguage = (language: UiLanguage): void => {
  writeStoredJson(STORED_UI_LANGUAGE_KEY, language);
};

export const languageLocale = (language: UiLanguage): string =>
  language === 'ko' ? 'ko-KR' : 'en-US';

export const formatHistoryTime = (timestamp: number, language: UiLanguage): string =>
  new Date(timestamp).toLocaleTimeString(languageLocale(language), {
    hour: '2-digit',
    minute: '2-digit',
  });
