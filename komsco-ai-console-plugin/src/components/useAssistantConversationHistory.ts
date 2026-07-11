import * as React from 'react';
import type { ConversationHistoryItem } from './assistant.types';

type UseAssistantConversationHistoryOptions = {
  readonly activeSessionId: string;
  readonly setConversationHistory: React.Dispatch<
    React.SetStateAction<ConversationHistoryItem[]>
  >;
  readonly startNewConversation: () => void;
};

type UseAssistantConversationHistoryResult = {
  readonly deleteConversation: (conversationHistoryId: string) => void;
  readonly renameConversation: (conversationHistoryId: string, title: string) => void;
  readonly toggleConversationPinned: (conversationHistoryId: string) => void;
};

export const useAssistantConversationHistory = ({
  activeSessionId,
  setConversationHistory,
  startNewConversation,
}: UseAssistantConversationHistoryOptions): UseAssistantConversationHistoryResult => {
  const deleteConversation = React.useCallback(
    (conversationHistoryId: string) => {
      setConversationHistory((prev) =>
        prev.filter((conversation) => conversation.id !== conversationHistoryId),
      );
      if (conversationHistoryId === activeSessionId) {
        startNewConversation();
      }
    },
    [activeSessionId, setConversationHistory, startNewConversation],
  );

  const renameConversation = React.useCallback(
    (conversationHistoryId: string, title: string) => {
      const trimmed = title.trim();
      if (!trimmed) {
        return;
      }
      setConversationHistory((prev) =>
        prev.map((conversation) =>
          conversation.id === conversationHistoryId
            ? { ...conversation, title: trimmed }
            : conversation,
        ),
      );
    },
    [setConversationHistory],
  );

  const toggleConversationPinned = React.useCallback(
    (conversationHistoryId: string) => {
      setConversationHistory((prev) =>
        prev.map((conversation) =>
          conversation.id === conversationHistoryId
            ? { ...conversation, pinned: !conversation.pinned }
            : conversation,
        ),
      );
    },
    [setConversationHistory],
  );

  return {
    deleteConversation,
    renameConversation,
    toggleConversationPinned,
  };
};
