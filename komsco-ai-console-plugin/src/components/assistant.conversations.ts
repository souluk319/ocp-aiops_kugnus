import * as React from 'react';
import { MAX_STORED_CONVERSATIONS } from './assistant.constants';
import {
  createRunId,
  getConversationTitle,
  readStoredActiveConversation,
  readStoredConversationHistory,
  readStoredUiLanguage,
  writeStoredActiveConversation,
  writeStoredConversationHistory,
  writeStoredUiLanguage,
} from './assistant.storage';
import type {
  ConversationActionRef,
  ConversationHistoryItem,
  Message,
  UiLanguage,
} from './assistant.types';

type SaveConversationOptions = {
  readonly preserveUpdatedAt?: boolean;
  readonly promote?: boolean;
  readonly snapshotConversationId?: string;
  readonly snapshotMessages?: Message[];
};

type UseAssistantConversationsOptions = {
  readonly loading: boolean;
  readonly mergeActionRefs: (
    refs: ConversationActionRef[],
    ref: ConversationActionRef,
  ) => ConversationActionRef[];
};

export const mergeStoredActiveConversationIntoHistory = (
  history: ConversationHistoryItem[],
  activeConversation: ReturnType<typeof readStoredActiveConversation>,
  language: UiLanguage,
): ConversationHistoryItem[] => {
  if (!activeConversation?.messages.length) {
    return history;
  }

  const existing = history.find((conversation) => conversation.id === activeConversation.activeSessionId);
  const activeHistoryItem: ConversationHistoryItem = {
    id: activeConversation.activeSessionId,
    title: existing?.title || getConversationTitle(activeConversation.messages, language),
    updatedAt: Date.now(),
    conversationId: activeConversation.conversationId,
    messages: activeConversation.messages,
    pinned: existing?.pinned,
    actionRefs: activeConversation.actionRefs,
    actionTargetKeys: activeConversation.actionTargetKeys,
  };

  return [
    activeHistoryItem,
    ...history.filter((conversation) => conversation.id !== activeConversation.activeSessionId),
  ].slice(0, MAX_STORED_CONVERSATIONS);
};

export const useAssistantConversations = ({
  loading,
  mergeActionRefs,
}: UseAssistantConversationsOptions) => {
  const initialActiveConversation = React.useMemo(readStoredActiveConversation, []);
  const initialUiLanguage = React.useMemo(readStoredUiLanguage, []);
  const initialConversationHistory = React.useMemo(
    () =>
      mergeStoredActiveConversationIntoHistory(
        readStoredConversationHistory(),
        initialActiveConversation,
        initialUiLanguage,
      ),
    [initialActiveConversation, initialUiLanguage],
  );
  const [messages, setMessages] = React.useState<Message[]>([]);
  const [conversationId, setConversationId] = React.useState<string | undefined>(undefined);
  const [activeSessionId, setActiveSessionId] = React.useState(createRunId);
  const [conversationHistory, setConversationHistory] = React.useState<ConversationHistoryItem[]>(
    initialConversationHistory,
  );
  const [sessionActionTargetKeys, setSessionActionTargetKeys] = React.useState<Set<string>>(
    () => new Set(),
  );
  const [sessionActionRefs, setSessionActionRefs] = React.useState<ConversationActionRef[]>([]);
  const [uiLanguage, setUiLanguage] = React.useState<UiLanguage>(initialUiLanguage);
  const messagesRef = React.useRef<Message[]>(messages);
  const suppressNextHistoryAutosaveRef = React.useRef(false);

  React.useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  React.useEffect(() => {
    writeStoredActiveConversation({
      activeSessionId,
      actionRefs: sessionActionRefs,
      actionTargetKeys: Array.from(sessionActionTargetKeys),
      conversationId,
      messages,
    });
  }, [activeSessionId, conversationId, messages, sessionActionRefs, sessionActionTargetKeys]);

  React.useEffect(() => {
    writeStoredConversationHistory(conversationHistory);
  }, [conversationHistory]);

  React.useEffect(() => {
    writeStoredUiLanguage(uiLanguage);
  }, [uiLanguage]);

  const upsertSessionActionRef = React.useCallback((ref: ConversationActionRef) => {
    setSessionActionRefs((prev) => mergeActionRefs(prev, ref));

    const snapshotMessages = messagesRef.current;
    if (snapshotMessages.length === 0) {
      return;
    }

    setConversationHistory((prev) => {
      const existing = prev.find((conversation) => conversation.id === activeSessionId);
      const actionTargetKeys = Array.from(
        new Set(
          [
            ...(existing?.actionTargetKeys ?? []),
            ref.targetKey,
          ].filter((targetKey): targetKey is string => Boolean(targetKey)),
        ),
      );
      const item: ConversationHistoryItem = {
        id: activeSessionId,
        title: existing?.title || getConversationTitle(snapshotMessages, uiLanguage),
        updatedAt: Date.now(),
        conversationId,
        messages: snapshotMessages,
        pinned: existing?.pinned,
        actionRefs: mergeActionRefs(existing?.actionRefs ?? [], ref),
        actionTargetKeys,
      };

      return [item, ...prev.filter((conversation) => conversation.id !== activeSessionId)].slice(
        0,
        MAX_STORED_CONVERSATIONS,
      );
    });
  }, [activeSessionId, conversationId, mergeActionRefs, uiLanguage]);

  const saveCurrentConversation = React.useCallback(
    (options: SaveConversationOptions = {}) => {
      const snapshotMessages = options.snapshotMessages ?? messages;
      const snapshotConversationId = options.snapshotConversationId ?? conversationId;

      if (snapshotMessages.length === 0) {
        return;
      }

      setConversationHistory((prev) => {
        const existing = prev.find((conversation) => conversation.id === activeSessionId);
        const mergedActionRefs = sessionActionRefs.reduce(
          (refs, ref) => mergeActionRefs(refs, ref),
          existing?.actionRefs ?? [],
        );
        const mergedActionTargetKeys = Array.from(
          new Set([
            ...(existing?.actionTargetKeys ?? []),
            ...Array.from(sessionActionTargetKeys),
          ]),
        );
        const item: ConversationHistoryItem = {
          id: activeSessionId,
          title: getConversationTitle(snapshotMessages, uiLanguage),
          updatedAt:
            options.preserveUpdatedAt && existing ? existing.updatedAt : Date.now(),
          conversationId: snapshotConversationId,
          messages: snapshotMessages,
          pinned: existing?.pinned,
          actionRefs: mergedActionRefs,
          actionTargetKeys: mergedActionTargetKeys,
        };

        if (existing && options.promote === false) {
          return prev.map((conversation) =>
            conversation.id === activeSessionId ? item : conversation,
          );
        }

        return [item, ...prev.filter((conversation) => conversation.id !== activeSessionId)].slice(
          0,
          MAX_STORED_CONVERSATIONS,
        );
      });
    },
    [
      activeSessionId,
      conversationId,
      mergeActionRefs,
      messages,
      sessionActionRefs,
      sessionActionTargetKeys,
      uiLanguage,
    ],
  );

  React.useEffect(() => {
    if (!loading) {
      if (suppressNextHistoryAutosaveRef.current) {
        suppressNextHistoryAutosaveRef.current = false;
        return;
      }
      saveCurrentConversation();
    }
  }, [loading, saveCurrentConversation]);

  return {
    activeSessionId,
    conversationHistory,
    conversationId,
    messages,
    messagesRef,
    saveCurrentConversation,
    sessionActionRefs,
    sessionActionTargetKeys,
    setActiveSessionId,
    setConversationHistory,
    setConversationId,
    setMessages,
    setSessionActionRefs,
    setSessionActionTargetKeys,
    setUiLanguage,
    suppressNextHistoryAutosaveRef,
    uiLanguage,
    upsertSessionActionRef,
  };
};
