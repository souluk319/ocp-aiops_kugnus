import * as React from 'react';
import { Card, CardBody } from '@patternfly/react-core';
import * as ReactDOM from 'react-dom';
import AssistantAnswerActions from './AssistantActionRecords';
import AssistantComposer from './AssistantComposer';
import AssistantCreateActionPlanButtons from './AssistantCreateActionPlanButtons';
import AssistantEvidenceFooter from './AssistantEvidenceFooter';
import AssistantEmptyState from './AssistantEmptyState';
import AssistantFollowupMessageContent from './AssistantFollowupChoices';
import AssistantHeader from './AssistantHeader';
import AssistantHistoryPanel from './AssistantHistoryPanel';
import AssistantImageLightbox from './AssistantImageLightbox';
import AssistantInsightRail from './AssistantInsightRail';
import AssistantMessageHeader from './AssistantMessageHeader';
import {
  feedbackExcerpt,
  MessageActionFooter,
  MessageFeedbackComment,
  type MessageFeedbackChoice,
  previousUserMessageForFeedback,
  publicFeedbackAnswerContract,
  publicFeedbackSource,
  removeStoredMessageFeedback,
  writeStoredMessageFeedback,
} from './AssistantMessageFeedback';
import AssistantResizeHandles from './AssistantResizeHandles';
import AssistantSurfacePortal from './AssistantSurfacePortal';
import AssistantToolPlanFooter from './AssistantToolPlanFooter';
import ProgressTimeline from './AssistantProgressTimeline';
import {
  ASSISTANT_TASK_MODES,
  ASSISTANT_TYPEWRITER_CHARS,
  ASSISTANT_TYPEWRITER_INTERVAL_MS,
  CLUSTER_SUMMARY_REFRESH_MS,
  DEFAULT_AIOPS_EXECUTION_MODE,
  MIN_STOP_BUTTON_VISIBLE_MS,
  SCROLL_BOTTOM_THRESHOLD_PX,
} from './assistant.constants';
import {
  actionRecordInlineKey,
  actionRecordsForMatchedCandidates,
  groupActionRecordsByCandidateId,
  latestAnswerActionRecords,
} from './assistant.actionDisplay';
import {
  dedupeActionCandidates,
  matchActionCandidatesForMessage,
} from './assistant.actionCandidates';
import { TASK_MODE_EMPTY_COPY, UI_COPY } from './assistant.copy';
import { useAssistantConversations } from './assistant.conversations';
import { buildEvidenceCopyText } from './assistant.evidence';
import {
  actionAnchorForMessageIndex,
  conversationActionRefFromRecord,
  getRecordTargetLabel,
} from './assistant.actionRecords';
import {
  canUseActionExecution,
  getAiopsRecordAction,
  getActionExecutionDisabledReason,
} from './assistant.actionState';
import { getClusterHost } from './assistant.insightRailHelpers';
import {
  createRunId,
  formatHistoryTime,
} from './assistant.storage';
import {
  buildRecentContextMessages,
  findLastAssistantIndex,
  formatMessageTime,
  getAssistantConnectionState,
  markLastAssistantStreaming,
  setLastAssistantContentIfEmpty,
} from './assistant.messageState';
import { buildConsolePageContext } from './assistant.pageContext';
import {
  conversationActionRefFromCandidate,
  groupActionRefsByCandidateId,
  mergeConversationActionRefs,
  pendingActionCandidatesForRefs,
  sortConversationActionRefsForDisplay,
  targetKeyFromParts,
} from './assistant.sessionActions';
import { useAssistantUploads } from './assistant.uploads';
import { useAssistantAttachmentInteractions } from './useAssistantAttachmentInteractions';
import { useAssistantActionPlanRuntime } from './useAssistantActionPlanRuntime';
import { useAssistantAiopsRuntimeStatus } from './useAssistantAiopsRuntimeStatus';
import { useAssistantConversationHistory } from './useAssistantConversationHistory';
import { useAssistantPanelGeometry } from './useAssistantPanelGeometry';
import { useAssistantStreamProgress } from './useAssistantStreamProgress';
import { runAssistantStream } from './assistant.streamController';
import {
  stripDefaultEvidenceAppendix,
} from './assistant.render';
import type {
  AiopsExecutionMode,
  AssistantLauncherProps,
  AssistantTaskMode,
  ConversationActionRef,
  ConversationHistoryItem,
  HistoryPanelView,
  Message,
} from './assistant.types';
import {
  type AiopsActionCandidate,
  type ChatFeedbackPayload,
  type ClusterSummary,
  fetchClusterSummary,
  submitChatFeedback,
} from '../services/aiGateway';
import { redactSensitiveText } from '../utils/evidenceDisplay';
import aiopsIcon from '../assets/aiops_icon.svg';
import './assistant.css';
import './assistant.followups.css';

const conversationHistoryMergeFns = {
  actionRefs: mergeConversationActionRefs,
} as const;

const draftExecutionMode = (pageContext?: Record<string, unknown>): AiopsExecutionMode | null => {
  const value = String(pageContext?.aiopsExecutionMode ?? '')
    .trim()
    .toLowerCase();
  if (
    value === 'read-only' ||
    value === 'read_only' ||
    value === 'evidence-check' ||
    value === 'evidence_check'
  ) {
    return 'read-only';
  }
  if (value === 'execute' || value === 'unrestricted') {
    return value;
  }
  return null;
};

const flushReactSync = (callback: () => void) => {
  const flushSync = (ReactDOM as unknown as { flushSync?: (syncCallback: () => void) => void })
    .flushSync;

  if (flushSync) {
    flushSync(callback);
    return;
  }

  callback();
};

const writeClipboardText = async (text: string): Promise<boolean> => {
  if (!text) {
    return false;
  }

  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // Fall through to the textarea copy path for local console/browser contexts.
    }
  }

  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.setAttribute('readonly', 'true');
  textarea.style.position = 'fixed';
  textarea.style.inset = '0 auto auto 0';
  textarea.style.opacity = '0';
  document.body.appendChild(textarea);
  textarea.select();
  try {
    return document.execCommand('copy');
  } finally {
    document.body.removeChild(textarea);
  }
};

const AssistantLauncher: React.FC<AssistantLauncherProps> = ({
  ambientPageContext,
  defaultOpen = false,
  draftPrompt,
  embedded = false,
  lockOpen = false,
  onRunComplete,
}) => {
  const [open, setOpen] = React.useState(defaultOpen || embedded || lockOpen);
  const [fullScreen, setFullScreen] = React.useState(false);
  const [input, setInput] = React.useState('');
  const [draftPageContext, setDraftPageContext] = React.useState<
    Record<string, unknown> | undefined
  >();
  const [clusterSummary, setClusterSummary] = React.useState<ClusterSummary | null>(null);
  const [clusterSummaryError, setClusterSummaryError] = React.useState('');
  const [clusterSummaryLoading, setClusterSummaryLoading] = React.useState(false);
  const {
    aiopsStatus,
    aiopsStatusError,
    authSubject,
    authSubjectError,
    refreshAiopsRuntimeStatus,
    setAiopsStatus,
    updateLightspeedStatus,
    upsertAiopsRuntimeRecords,
  } = useAssistantAiopsRuntimeStatus({
    open,
    refreshIntervalMs: CLUSTER_SUMMARY_REFRESH_MS,
  });
  const [autoProposeActions, setAutoProposeActions] = React.useState(false);
  const autoProposeActionsAllowedRef = React.useRef(false);
  const [executionMode, setExecutionMode] = React.useState<AiopsExecutionMode>(
    DEFAULT_AIOPS_EXECUTION_MODE,
  );
  React.useEffect(() => {
    autoProposeActionsAllowedRef.current = executionMode === 'execute' && autoProposeActions;
  }, [executionMode, autoProposeActions]);
  const [loading, setLoading] = React.useState(false);
  const {
    activeSessionId,
    conversationHistory,
    conversationId,
    messages,
    messagesRef,
    saveCurrentConversation,
    sessionActionRefs,
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
  } = useAssistantConversations({
    loading,
    mergeActionRefs: conversationHistoryMergeFns.actionRefs,
  });
  const [historySidebarOpen, setHistorySidebarOpen] = React.useState(false);
  const [historyPanelView, setHistoryPanelView] = React.useState<HistoryPanelView>('chats');
  const copy = UI_COPY[uiLanguage];
  const {
    addImageFiles,
    attachmentError,
    dragActive,
    pendingAttachments,
    removeAttachment,
    setAttachmentError,
    setDragActive,
    setPendingAttachments,
    uploadedDocuments,
    uploadedDocumentsError,
    uploadedDocumentsLoading,
  } = useAssistantUploads({
    activeSessionId,
    historyPanelView,
    historySidebarOpen,
    open,
    setHistoryPanelView,
    setHistorySidebarOpen,
    uploadedDocsErrorLabel: copy.uploadedDocsError,
  });
  const {
    closeAttachmentPreview,
    fileInputRef,
    handleDragEnter: handleAttachmentDragEnter,
    handleDragLeave: handleAttachmentDragLeave,
    handleDragOver: handleAttachmentDragOver,
    handleDrop: handleAttachmentDrop,
    handleFileInputChange,
    handlePaste,
    openAttachmentPreview,
    previewAttachment,
  } = useAssistantAttachmentInteractions({
    addImageFiles,
    setDragActive,
  });
  const [quickPromptMenuOpen, setQuickPromptMenuOpen] = React.useState(false);
  const [taskModeMenuOpen, setTaskModeMenuOpen] = React.useState(false);
  const [openHistoryMenuId, setOpenHistoryMenuId] = React.useState<string | null>(null);
  const [historyMenuAnchor, setHistoryMenuAnchor] = React.useState<{
    right: number;
    top: number;
  } | null>(null);
  const [renamingHistoryId, setRenamingHistoryId] = React.useState<string | null>(null);
  const [renamingHistoryTitle, setRenamingHistoryTitle] = React.useState('');
  const [assistantTaskMode, setAssistantTaskMode] = React.useState<AssistantTaskMode>('ask');
  const [stickToBottom, setStickToBottom] = React.useState(true);
  const [showScrollToBottom, setShowScrollToBottom] = React.useState(false);
  const [copiedMessageIndex, setCopiedMessageIndex] = React.useState<number | null>(null);
  const surfaceRef = React.useRef<HTMLDivElement | null>(null);
  const fabButtonRef = React.useRef<HTMLButtonElement | null>(null);
  const bodyRef = React.useRef<HTMLDivElement | null>(null);
  const bodyEndRef = React.useRef<HTMLDivElement | null>(null);
  const consumedDraftPromptIdRef = React.useRef('');
  const quickPromptMenuRef = React.useRef<HTMLDivElement | null>(null);
  const taskModeMenuRef = React.useRef<HTMLDivElement | null>(null);
  const historyMenuRef = React.useRef<HTMLDivElement | null>(null);
  const historyMenuPanelRef = React.useRef<HTMLDivElement | null>(null);
  const assistantTextQueueRef = React.useRef('');
  const assistantTypewriterTimerRef = React.useRef<number | undefined>();
  const assistantTextDrainResolversRef = React.useRef<Array<() => void>>([]);
  const chatAbortControllerRef = React.useRef<AbortController | null>(null);
  const stopRequestedRef = React.useRef(false);
  const {
    historySidebarStyle,
    panelDragActive,
    panelResizeUnlocked,
    resetPanelGeometry,
    startPanelDrag,
    startPanelResize,
    surfaceStyle,
    togglePanelResizeLock,
  } = useAssistantPanelGeometry({
    embedded,
    fullScreen,
    historySidebarOpen,
    surfaceRef,
  });
  const actionExecutionAvailable = canUseActionExecution(aiopsStatus);
  const actionExecutionDisabledReason = getActionExecutionDisabledReason(aiopsStatus, uiLanguage);
  const assistantConnection = getAssistantConnectionState(
    clusterSummary,
    clusterSummaryLoading,
    clusterSummaryError,
    aiopsStatus,
    aiopsStatusError,
  );
  const selectedTaskMode =
    ASSISTANT_TASK_MODES.find((item) => item.value === assistantTaskMode) ||
    ASSISTANT_TASK_MODES[0];
  const emptyStateCopy =
    TASK_MODE_EMPTY_COPY[assistantTaskMode]?.[uiLanguage] ?? TASK_MODE_EMPTY_COPY.ask[uiLanguage];

  const openAssistant = React.useCallback(() => {
    setOpen(true);
  }, []);

  React.useEffect(() => {
    const button = fabButtonRef.current;
    if (!button || embedded) {
      return undefined;
    }

    button.addEventListener('click', openAssistant);

    return () => {
      button.removeEventListener('click', openAssistant);
    };
  }, [embedded, openAssistant]);

  React.useEffect(() => {
    if (!draftPrompt || consumedDraftPromptIdRef.current === draftPrompt.id) {
      return;
    }

    consumedDraftPromptIdRef.current = draftPrompt.id;
    setInput(draftPrompt.prompt);
    setDraftPageContext(draftPrompt.pageContext);
    setAssistantTaskMode(draftPrompt.taskMode ?? 'troubleshooting');
    const requestedExecutionMode = draftExecutionMode(draftPrompt.pageContext);
    if (requestedExecutionMode) {
      setExecutionMode(requestedExecutionMode);
    }
    setQuickPromptMenuOpen(false);
    setTaskModeMenuOpen(false);
    setOpen(true);
    window.setTimeout(() => {
      surfaceRef.current?.querySelector<HTMLTextAreaElement>('textarea')?.focus();
    }, 0);
  }, [draftPrompt]);

  React.useEffect(() => {
    if (!quickPromptMenuOpen && !taskModeMenuOpen && !openHistoryMenuId) {
      return undefined;
    }

    const handleDocumentMouseDown = (event: MouseEvent) => {
      const target = event.target as Node | null;
      if (
        target &&
        (quickPromptMenuRef.current?.contains(target) ||
          taskModeMenuRef.current?.contains(target) ||
          historyMenuRef.current?.contains(target) ||
          historyMenuPanelRef.current?.contains(target))
      ) {
        return;
      }

      setQuickPromptMenuOpen(false);
      setTaskModeMenuOpen(false);
      setOpenHistoryMenuId(null);
    };

    const handleDocumentKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') {
        return;
      }

      setQuickPromptMenuOpen(false);
      setTaskModeMenuOpen(false);
      setOpenHistoryMenuId(null);
    };

    document.addEventListener('mousedown', handleDocumentMouseDown);
    document.addEventListener('keydown', handleDocumentKeyDown);

    return () => {
      document.removeEventListener('mousedown', handleDocumentMouseDown);
      document.removeEventListener('keydown', handleDocumentKeyDown);
    };
  }, [openHistoryMenuId, quickPromptMenuOpen, taskModeMenuOpen]);

  const getLatestAssistantMessageAnchor = React.useCallback((): string | undefined => {
    const index = findLastAssistantIndex(messagesRef.current);
    return index >= 0 ? actionAnchorForMessageIndex(index) : undefined;
  }, []);

  const {
    actionCandidateFeedback,
    actionCandidates,
    aiopsActionBusyId,
    aiopsActionError,
    aiopsActionNotice,
    busyActionCandidateId,
    clearActionCandidateFeedback,
    clearActionError,
    handleAiopsAction,
    handleCreateActionPlanFromChat,
    refreshAiopsActionCandidates,
    resetActionActivity,
  } = useAssistantActionPlanRuntime({
    aiopsStatus,
    executionMode,
    getLatestAssistantMessageAnchor,
    onActionPlanCreated: (source, plan, messageAnchor) => {
      const targetKey = getRecordTargetLabel(source);
      setSessionActionTargetKeys((prev) => new Set(prev).add(targetKey));
      upsertSessionActionRef(
        conversationActionRefFromRecord(plan, executionMode, messageAnchor),
      );
    },
    onActionRecordCreated: (record, messageAnchor) => {
      upsertSessionActionRef(
        conversationActionRefFromRecord(record, executionMode, messageAnchor),
      );
    },
    onCandidatePlanCreated: (candidate, plan, messageAnchor) => {
      const targetKey = targetKeyFromParts(candidate.target?.namespace, candidate.target?.name);
      setSessionActionTargetKeys((prev) => new Set(prev).add(targetKey));
      upsertSessionActionRef(
        plan
          ? {
              ...conversationActionRefFromRecord(plan, executionMode, messageAnchor),
              candidateId: candidate.id,
            }
          : conversationActionRefFromCandidate(candidate, messageAnchor),
      );
    },
    open,
    refreshAiopsRuntimeStatus: () => refreshAiopsRuntimeStatus(),
    upsertAiopsRuntimeRecords: (updates) => upsertAiopsRuntimeRecords(updates),
  });

  const handleExecutionModeChange = React.useCallback(
    (mode: AiopsExecutionMode) => {
      clearActionError();
      setExecutionMode(mode);
    },
    [clearActionError],
  );

  const startNewConversation = React.useCallback(() => {
    if (loading && chatAbortControllerRef.current) {
      stopRequestedRef.current = true;
      chatAbortControllerRef.current.abort();
      chatAbortControllerRef.current = null;
      assistantTextQueueRef.current = '';
      setLoading(false);
    }

    saveCurrentConversation();
    setActiveSessionId(createRunId());
    setConversationId(undefined);
    setMessages([]);
    setSessionActionTargetKeys(new Set());
    setSessionActionRefs([]);
    setInput('');
    setPendingAttachments([]);
    setAttachmentError('');
    resetActionActivity();
    setQuickPromptMenuOpen(false);
    setTaskModeMenuOpen(false);
  }, [loading, saveCurrentConversation]);

  const loadConversation = React.useCallback(
    (conversation: ConversationHistoryItem) => {
      if (loading) {
        return;
      }

      saveCurrentConversation({ preserveUpdatedAt: true, promote: false });
      suppressNextHistoryAutosaveRef.current = true;
      setActiveSessionId(conversation.id);
      setConversationId(conversation.conversationId);
      setMessages(conversation.messages);
      setSessionActionTargetKeys(
        new Set([
          ...(conversation.actionTargetKeys ?? []),
          ...(conversation.actionRefs ?? []).map((actionRef) => actionRef.targetKey),
        ]),
      );
      setSessionActionRefs(conversation.actionRefs ?? []);
      setInput('');
      setPendingAttachments([]);
      setAttachmentError('');
      clearActionCandidateFeedback();
      setQuickPromptMenuOpen(false);
      setTaskModeMenuOpen(false);
    },
    [loading, saveCurrentConversation],
  );

  const scrollToActionAnchor = React.useCallback((messageAnchor?: string) => {
    if (!messageAnchor) {
      return;
    }

    window.setTimeout(() => {
      const surface = surfaceRef.current;
      const target = Array.from(
        surface?.querySelectorAll<HTMLElement>('[data-action-anchor]') ?? [],
      ).find((element) => element.getAttribute('data-action-anchor') === messageAnchor);

      if (!target) {
        return;
      }

      target.scrollIntoView({ block: 'center', behavior: 'smooth' });
      target.classList.add('komsco-ai__message--action-highlight');
      window.setTimeout(() => {
        target.classList.remove('komsco-ai__message--action-highlight');
      }, 1800);
    }, 120);
  }, []);

  const handleHistoryActionRefSelect = React.useCallback(
    (conversation: ConversationHistoryItem, actionRef: ConversationActionRef) => {
      if (loading) {
        return;
      }

      setOpenHistoryMenuId(null);
      setHistoryPanelView('chats');
      setSessionActionRefs(conversation.actionRefs ?? []);
      setSessionActionTargetKeys(new Set(conversation.actionTargetKeys ?? []));

      if (conversation.id !== activeSessionId) {
        loadConversation(conversation);
      }

      scrollToActionAnchor(actionRef.messageAnchor);
    },
    [activeSessionId, loadConversation, loading, scrollToActionAnchor],
  );

  const {
    deleteConversation,
    renameConversation,
    toggleConversationPinned,
  } = useAssistantConversationHistory({
    activeSessionId,
    setConversationHistory,
    startNewConversation,
  });

  const scrollToBottom = React.useCallback((behavior: ScrollBehavior = 'smooth') => {
    const body = bodyRef.current;
    if (body) {
      body.scrollTo({ top: body.scrollHeight, behavior });
    }
    bodyEndRef.current?.scrollIntoView({ block: 'end', behavior });
  }, []);

  const handleConversationScroll = React.useCallback((event: React.UIEvent<HTMLDivElement>) => {
    const target = event.currentTarget;
    const distanceToBottom = target.scrollHeight - target.scrollTop - target.clientHeight;
    const nearBottom = distanceToBottom <= SCROLL_BOTTOM_THRESHOLD_PX;

    setStickToBottom(nearBottom);
    setShowScrollToBottom(!nearBottom);
  }, []);

  React.useEffect(() => {
    if (stickToBottom) {
      scrollToBottom('auto');
      setShowScrollToBottom(false);
    } else {
      setShowScrollToBottom(true);
    }
  }, [loading, messages, scrollToBottom, stickToBottom]);

  React.useEffect(() => {
    if (!open) {
      return undefined;
    }

    let disposed = false;

    const loadSummary = async () => {
      setClusterSummaryLoading(true);
      const [summaryResult] = await Promise.allSettled([fetchClusterSummary()]);
      if (disposed) {
        return;
      }

      if (summaryResult.status === 'fulfilled') {
        setClusterSummary(summaryResult.value);
        setClusterSummaryError('');
      } else {
        setClusterSummaryError(
          summaryResult.reason instanceof Error
            ? summaryResult.reason.message
            : 'Cluster summary request failed.',
        );
      }

      setClusterSummaryLoading(false);
    };

    void loadSummary();
    const timer = window.setInterval(() => {
      void loadSummary();
    }, CLUSTER_SUMMARY_REFRESH_MS);

    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, [open]);

  const appendAssistantText = React.useCallback((content: string) => {
    setMessages((prev) => {
      const assistantIndex = findLastAssistantIndex(prev);
      if (assistantIndex < 0) {
        return [...prev, { role: 'assistant', content, streaming: true, timestamp: Date.now() }];
      }

      const next = [...prev];
      next[assistantIndex] = {
        ...next[assistantIndex],
        content: next[assistantIndex].content + content,
        streaming: true,
        timestamp: next[assistantIndex].timestamp ?? Date.now(),
      };

      return next;
    });
  }, []);

  const clearAssistantTypewriterTimer = React.useCallback(() => {
    if (assistantTypewriterTimerRef.current === undefined) {
      return;
    }

    window.clearTimeout(assistantTypewriterTimerRef.current);
    assistantTypewriterTimerRef.current = undefined;
  }, []);

  const flushAssistantTextQueueNow = React.useCallback(() => {
    clearAssistantTypewriterTimer();

    const queuedText = assistantTextQueueRef.current;
    if (!queuedText) {
      return;
    }

    assistantTextQueueRef.current = '';
    appendAssistantText(queuedText);
    const resolvers = assistantTextDrainResolversRef.current;
    assistantTextDrainResolversRef.current = [];
    resolvers.forEach((resolve) => resolve());
  }, [appendAssistantText, clearAssistantTypewriterTimer]);

  const scheduleAssistantTextDrain = React.useCallback(() => {
    if (assistantTypewriterTimerRef.current !== undefined) {
      return;
    }

    const drain = () => {
      const queuedText = assistantTextQueueRef.current;
      if (!queuedText) {
        assistantTypewriterTimerRef.current = undefined;
        const resolvers = assistantTextDrainResolversRef.current;
        assistantTextDrainResolversRef.current = [];
        resolvers.forEach((resolve) => resolve());
        return;
      }

      const chunk = queuedText.slice(0, ASSISTANT_TYPEWRITER_CHARS);
      assistantTextQueueRef.current = queuedText.slice(chunk.length);
      appendAssistantText(chunk);
      assistantTypewriterTimerRef.current = window.setTimeout(
        drain,
        ASSISTANT_TYPEWRITER_INTERVAL_MS,
      );
    };

    assistantTypewriterTimerRef.current = window.setTimeout(drain, 0);
  }, [appendAssistantText]);

  const enqueueAssistantText = React.useCallback(
    (content: string) => {
      assistantTextQueueRef.current += content;
      scheduleAssistantTextDrain();
    },
    [scheduleAssistantTextDrain],
  );

  const waitForAssistantTextQueue = React.useCallback(async () => {
    if (!assistantTextQueueRef.current && assistantTypewriterTimerRef.current === undefined) {
      return;
    }

    await new Promise<void>((resolve) => {
      assistantTextDrainResolversRef.current.push(resolve);
      scheduleAssistantTextDrain();
    });
  }, [scheduleAssistantTextDrain]);

  React.useEffect(
    () => () => {
      clearAssistantTypewriterTimer();
      const resolvers = assistantTextDrainResolversRef.current;
      assistantTextDrainResolversRef.current = [];
      resolvers.forEach((resolve) => resolve());
    },
    [clearAssistantTypewriterTimer],
  );

  const copyMessage = React.useCallback(
    (message: Message, index: number) => {
      const redactedContent = redactSensitiveText(
        stripDefaultEvidenceAppendix(message.content).trim(),
      );
      const text = `${redactedContent}${buildEvidenceCopyText(
        message.evidenceFooter,
        uiLanguage,
      )}`.trim();
      if (!text) {
        return;
      }

      void writeClipboardText(text).then((copied) => {
        if (!copied) {
          return;
        }
        setCopiedMessageIndex(index);
        window.setTimeout(() => {
          setCopiedMessageIndex((current) => (current === index ? null : current));
        }, 1400);
      });
    },
    [uiLanguage],
  );

  const editMessageForResend = React.useCallback((message: Message) => {
    const draft = stripDefaultEvidenceAppendix(message.content).trim();
    if (!draft) {
      return;
    }
    setInput(draft);
    setPendingAttachments(message.attachments ?? []);
    window.setTimeout(() => {
      surfaceRef.current?.querySelector<HTMLTextAreaElement>('textarea')?.focus();
    }, 0);
  }, []);

  const persistMessageFeedback = React.useCallback(
    (
      index: number,
      message: Message,
      feedback: MessageFeedbackChoice,
      optionalComment?: string,
	    ) => {
	      const messageId = `${activeSessionId}:${index}:${message.timestamp ?? 'pending'}`;
      const submittedAt = new Date().toISOString();
      const feedbackSource = publicFeedbackSource(message);
      const userMessage = previousUserMessageForFeedback(messagesRef.current, index);
      const assistantAnswer = feedbackExcerpt(stripDefaultEvidenceAppendix(message.content), 2000);
      const userMessageExcerpt = feedbackExcerpt(userMessage ?? '', 1200);
      if (!userMessageExcerpt || !assistantAnswer) {
        // Runbook-reviewable feedback must include both sides of the conversation.
        return;
      }
      const payload: ChatFeedbackPayload = {
        answerContract: publicFeedbackAnswerContract(message),
        assistantAnswer,
        answerSource: feedbackSource,
        conversationId: conversationId ?? activeSessionId,
        feedbackId: `feedback-${messageId.replace(/[^a-zA-Z0-9-]+/g, '-')}-${feedback}`,
        intent: message.toolPlan?.taskType,
        messageId,
        mode: executionMode,
        optionalComment: optionalComment?.trim() || undefined,
        rating: feedback,
        route: window.location.pathname,
        source: feedbackSource,
        timestamp: submittedAt,
        userMessage: userMessageExcerpt,
      };

      writeStoredMessageFeedback(payload);
      void submitChatFeedback(payload)
        .then(() => {
          void refreshAiopsRuntimeStatus();
          void onRunComplete?.();
        })
        .catch((error) => {
          // Feedback is already kept locally; gateway persistence is best-effort during local tests.
          // eslint-disable-next-line no-console
          console.warn('AIOps feedback persistence failed', error);
        });
    },
    [activeSessionId, conversationId, executionMode, onRunComplete, refreshAiopsRuntimeStatus],
  );

  const toggleMessageFeedback = React.useCallback(
    (index: number, feedback: MessageFeedbackChoice) => {
      const currentMessage = messagesRef.current[index];
      const messageId = `${activeSessionId}:${index}:${currentMessage?.timestamp ?? 'pending'}`;
      const clearingFeedback =
        currentMessage?.role === 'assistant' && currentMessage.feedback === feedback;

      setMessages((prev) => {
        const message = prev[index];
        if (!message || message.role !== 'assistant') {
          return prev;
        }
        const next = [...prev];
        const nextMessage = { ...message };
        if (nextMessage.feedback === feedback) {
          delete nextMessage.feedback;
          delete nextMessage.feedbackAt;
          delete nextMessage.feedbackComment;
        } else {
          const previousFeedback = nextMessage.feedback;
          nextMessage.feedback = feedback;
          nextMessage.feedbackAt = Date.now();
          if (previousFeedback && previousFeedback !== feedback) {
            delete nextMessage.feedbackComment;
          }
        }
        next[index] = nextMessage;
        return next;
      });

      if (!currentMessage || currentMessage.role !== 'assistant') {
        return;
      }

      if (clearingFeedback) {
        removeStoredMessageFeedback(messageId, feedback);
        return;
      }

      // Selecting thumbs up/down only opens the tester comment form. Persisting
      // happens after the user writes the note and presses save, so the UI does
      // not claim "saved" for an empty review.
    },
    [activeSessionId],
  );

  const submitMessageFeedbackComment = React.useCallback(
    (index: number, comment: string) => {
      const currentMessage = messagesRef.current[index];
      if (!currentMessage || currentMessage.role !== 'assistant' || !currentMessage.feedback) {
        return;
      }

      const normalizedComment = comment.trim();
      setMessages((prev) => {
        const message = prev[index];
        if (!message || message.role !== 'assistant') {
          return prev;
        }
        const next = [...prev];
        next[index] = {
          ...message,
          feedbackComment: normalizedComment || undefined,
        };
        return next;
      });

      persistMessageFeedback(index, currentMessage, currentMessage.feedback, normalizedComment);
    },
    [persistMessageFeedback],
  );

  const {
    finalizeRunningProgressSteps,
    markRunningProgressFailed,
    upsertProgressStep,
  } = useAssistantStreamProgress({ loading, setMessages });

  const send = React.useCallback(
    async (prompt?: string) => {
      const question = (prompt ?? input).trim();
      const attachments = [...pendingAttachments];
      const activeAmbientPageContext = ambientPageContext;
      const activeDraftPageContext = draftPageContext;
      const requestExecutionMode = executionMode;

      if ((!question && attachments.length === 0) || loading) {
        return;
      }

      setStickToBottom(true);
      setShowScrollToBottom(false);
      setInput('');
      setPendingAttachments([]);
      setDraftPageContext(undefined);
      setAttachmentError('');
      clearActionCandidateFeedback();
      setQuickPromptMenuOpen(false);
      setTaskModeMenuOpen(false);
      flushReactSync(() => setLoading(true));
      const loadingStartedAt = Date.now();
      flushAssistantTextQueueNow();
      window.setTimeout(() => scrollToBottom('auto'), 0);
      const recentMessages = buildRecentContextMessages(messages);
      const messageTimestamp = Date.now();
      setMessages((prev) => [
        ...prev,
        { role: 'user', attachments, content: question, timestamp: messageTimestamp },
        { role: 'assistant', content: '', progressSteps: [], streaming: true },
      ]);

      const abortController = new AbortController();
      chatAbortControllerRef.current = abortController;
      stopRequestedRef.current = false;

      try {
        await new Promise((resolve) => window.setTimeout(resolve, 0));
        const runId = createRunId();
        const pageContext = {
          ...buildConsolePageContext(),
          ...activeAmbientPageContext,
          aiopsExecutionMode: requestExecutionMode,
          aiopsDemoCycle: activeDraftPageContext,
          aiopsTaskMode: assistantTaskMode,
          aiopsTaskModeLabel: selectedTaskMode.label,
          aiopsUiLanguage: uiLanguage,
        };
        const { finishAnswerStreamStep, runCompleted } = await runAssistantStream({
          attachments,
          conversationId,
          enqueueAssistantText,
          flushAssistantTextQueueNow,
          markRunningProgressFailed,
          pageContext,
          question,
          recentMessages,
          runId,
          setAiopsStatus,
          setConversationId,
          setMessages,
          signal: abortController.signal,
          uiLanguage,
          updateLightspeedStatus,
          upsertProgressStep,
        });
        await waitForAssistantTextQueue();
        setMessages((prev) => markLastAssistantStreaming(prev, false));
        finishAnswerStreamStep();
        finalizeRunningProgressSteps('답변 완료');
        await refreshAiopsRuntimeStatus();
        const refreshedActionCandidates = await refreshAiopsActionCandidates();
        let matchedActionCandidatesForAnswer: AiopsActionCandidate[] = [];
        setMessages((prev) => {
          const assistantIndex = findLastAssistantIndex(prev);
          if (assistantIndex < 0) {
            return prev;
          }

          const latestAssistantContent = prev[assistantIndex].content;
          matchedActionCandidatesForAnswer = matchActionCandidatesForMessage(
            latestAssistantContent,
            refreshedActionCandidates,
          );
          if (matchedActionCandidatesForAnswer.length === 0) {
            return prev;
          }

          const next = [...prev];
          next[assistantIndex] = {
            ...next[assistantIndex],
            actionCandidates: matchedActionCandidatesForAnswer,
          };
          return next;
        });
        if (autoProposeActionsAllowedRef.current) {
          matchedActionCandidatesForAnswer
            .filter((candidate) => !candidate.planDisabledReason)
            .forEach((candidate) => {
              void handleCreateActionPlanFromChat(candidate);
            });
        }
        if (runCompleted) {
          void onRunComplete?.();
        }
      } catch (error) {
        const stopped =
          stopRequestedRef.current || (error instanceof Error && error.name === 'AbortError');

        flushAssistantTextQueueNow();
        if (stopped) {
          markRunningProgressFailed('사용자가 응답 생성을 중지했습니다.');
          setMessages((prev) =>
            markLastAssistantStreaming(
              setLastAssistantContentIfEmpty(prev, '응답 생성을 중지했습니다.'),
              false,
            ),
          );
        } else {
          markRunningProgressFailed(error instanceof Error ? error.message : 'AI response failed.');
          setMessages((prev) => markLastAssistantStreaming(prev, false));
          setMessages((prev) => [
            ...prev,
            {
              role: 'system',
              content: error instanceof Error ? error.message : 'AI response failed.',
              timestamp: Date.now(),
            },
          ]);
        }
      } finally {
        const loadingElapsedMs = Date.now() - loadingStartedAt;
        if (loadingElapsedMs < MIN_STOP_BUTTON_VISIBLE_MS) {
          await new Promise((resolve) =>
            window.setTimeout(resolve, MIN_STOP_BUTTON_VISIBLE_MS - loadingElapsedMs),
          );
        }
        chatAbortControllerRef.current = null;
        stopRequestedRef.current = false;
        finalizeRunningProgressSteps('응답 흐름 정리 완료');
        setLoading(false);
      }
    },
    [
      enqueueAssistantText,
      ambientPageContext,
      assistantTaskMode,
      draftPageContext,
      executionMode,
      finalizeRunningProgressSteps,
      flushAssistantTextQueueNow,
      handleCreateActionPlanFromChat,
      input,
      loading,
      markRunningProgressFailed,
      onRunComplete,
      scrollToBottom,
      conversationId,
      messages,
      pendingAttachments,
      refreshAiopsActionCandidates,
      refreshAiopsRuntimeStatus,
      selectedTaskMode.label,
      updateLightspeedStatus,
      upsertProgressStep,
      waitForAssistantTextQueue,
    ],
  );

  const sendFollowupChoice = React.useCallback(
    (prompt: string): boolean => {
      if (loading || !prompt.trim()) {
        return false;
      }
      void send(prompt);
      return true;
    },
    [loading, send],
  );

  const cancelAssistantResponse = React.useCallback(() => {
    if (!loading || !chatAbortControllerRef.current) {
      return;
    }

    stopRequestedRef.current = true;
    chatAbortControllerRef.current.abort();
    flushAssistantTextQueueNow();
    setLoading(false);
  }, [flushAssistantTextQueueNow, loading]);

  const closeAssistant = React.useCallback(() => {
    if (lockOpen) {
      return;
    }

    startNewConversation();
    setHistorySidebarOpen(false);
    resetPanelGeometry();
    setFullScreen(false);
    setOpen(false);
  }, [lockOpen, resetPanelGeometry, startNewConversation]);

  const effectiveSessionActionRefs = React.useMemo(() => {
    const activeHistoryRefs =
      conversationHistory.find((conversation) => conversation.id === activeSessionId)?.actionRefs ??
      [];

    return activeHistoryRefs.reduce(
      (refs, ref) => mergeConversationActionRefs(refs, ref),
      sessionActionRefs,
    );
  }, [activeSessionId, conversationHistory, sessionActionRefs]);

  const historySidebar = historySidebarOpen ? (
    <AssistantHistoryPanel
      activeSessionId={activeSessionId}
      authSubject={authSubject}
      authSubjectError={authSubjectError}
      clusterSummary={clusterSummary}
      conversationHistory={conversationHistory}
      copy={copy}
      deleteConversation={deleteConversation}
      formatHistoryTime={formatHistoryTime}
      getClusterHost={getClusterHost}
      historyMenuAnchor={historyMenuAnchor}
      historyMenuPanelRef={historyMenuPanelRef}
      historyMenuRef={historyMenuRef}
      historyPanelView={historyPanelView}
      historySidebarStyle={historySidebarStyle}
      productIcon={aiopsIcon}
      loadConversation={loadConversation}
	      loading={loading}
	      onActionRefSelect={handleHistoryActionRefSelect}
	      openHistoryMenuId={openHistoryMenuId}
	      renameConversation={renameConversation}
      renamingHistoryId={renamingHistoryId}
      renamingHistoryTitle={renamingHistoryTitle}
      setHistoryMenuAnchor={setHistoryMenuAnchor}
      setHistoryPanelView={setHistoryPanelView}
      setOpenHistoryMenuId={setOpenHistoryMenuId}
	      setRenamingHistoryId={setRenamingHistoryId}
	      setRenamingHistoryTitle={setRenamingHistoryTitle}
	      startNewConversation={startNewConversation}
	      toggleConversationPinned={toggleConversationPinned}
	      uiLanguage={uiLanguage}
      uploadedDocuments={uploadedDocuments}
      uploadedDocumentsError={uploadedDocumentsError}
      uploadedDocumentsLoading={uploadedDocumentsLoading}
    />
  ) : null;
  const assistantVisible = open || embedded || lockOpen;

  const assistantRootClassName = `komsco-ai${embedded ? ' komsco-ai--embedded' : ''}${
    fullScreen ? ' komsco-ai--fullscreen-active' : ''
  }`;
  const assistantSurfacePortalActive = assistantVisible && !embedded;

  return (
    <div className={assistantRootClassName} data-ui-language={uiLanguage}>
      {!open && !embedded && (
        <button
          aria-label="Open AIOps for OCP"
          className="komsco-ai__fab"
          onMouseDown={openAssistant}
          onClick={openAssistant}
          onPointerDown={openAssistant}
          ref={fabButtonRef}
          type="button"
        >
          <img alt="" className="komsco-ai__fab-logo" src={aiopsIcon} />
          <span
            className={`komsco-ai__fab-status komsco-ai__fab-status--${assistantConnection.tone}`}
          />
        </button>
      )}

      {assistantVisible && (
        <AssistantSurfacePortal
          active={assistantSurfacePortalActive}
          wrapperClassName={`${assistantRootClassName} komsco-ai--portal`}
        >
          <div
            aria-label="AIOps for OCP"
            ref={surfaceRef}
            className={`komsco-ai__surface${fullScreen ? ' komsco-ai__surface--fullscreen' : ''}${
              historySidebarOpen ? ' komsco-ai__surface--history-open' : ''
            }${panelResizeUnlocked ? ' komsco-ai__surface--resize-unlocked' : ''}${
              !panelResizeUnlocked ? ' komsco-ai__surface--resize-locked' : ''
            }${loading ? ' komsco-ai__surface--responding' : ''}${
              panelDragActive ? ' komsco-ai__surface--dragging' : ''
            }`}
            style={surfaceStyle}
          >
            {historySidebar}
            <Card
              className={`komsco-ai__panel${fullScreen ? ' komsco-ai__panel--fullscreen' : ''}`}
            >
              <AssistantHeader
                actionExecutionAvailable={actionExecutionAvailable}
                actionExecutionDisabledReason={actionExecutionDisabledReason}
                clusterSummary={clusterSummary}
                clusterSummaryError={clusterSummaryError}
                clusterSummaryLoading={clusterSummaryLoading}
                copy={copy}
                executionMode={executionMode}
                fullScreen={fullScreen}
                lockOpen={lockOpen}
                onClose={closeAssistant}
                onExecutionModeChange={handleExecutionModeChange}
                onMouseDown={startPanelDrag}
                onToggleFullScreen={() => setFullScreen((value) => !value)}
                onToggleLanguage={() => setUiLanguage((value) => (value === 'ko' ? 'en' : 'ko'))}
                onToggleResizeLock={togglePanelResizeLock}
                onToggleSidebar={() => setHistorySidebarOpen((value) => !value)}
                panelResizeUnlocked={panelResizeUnlocked}
                uiLanguage={uiLanguage}
              />

              <div className="komsco-ai__workspace">
                <div className="komsco-ai__chat-column">
                  <CardBody
                    className="komsco-ai__body"
                    aria-live="polite"
                    onScroll={handleConversationScroll}
                    ref={bodyRef}
                  >
                    <div className="komsco-ai__conversation-inner">
                      {messages.length === 0 && (
                        <AssistantEmptyState
                          iconSrc={aiopsIcon}
                          text={emptyStateCopy.text}
                          title={emptyStateCopy.title}
                        />
                      )}

                      {messages.map((message, index) => {
                        const hasProgress = (message.progressSteps?.length ?? 0) > 0;
                        const hasContent = message.content.trim().length > 0;
                        const activeMessage = loading && index === messages.length - 1;
                        const isLatestAssistantMessage =
                          message.role === 'assistant' &&
                          index === findLastAssistantIndex(messages);
                        const isAssistantMessageWithContent =
                          message.role === 'assistant' && hasContent;
                        const messageActionAnchor =
                          message.role === 'assistant' ? actionAnchorForMessageIndex(index) : undefined;
                        const storedActionCandidates = message.actionCandidates ?? [];
                        const matched =
                          isAssistantMessageWithContent
                            ? storedActionCandidates.length > 0
                              ? storedActionCandidates
                              : isLatestAssistantMessage
                                ? matchActionCandidatesForMessage(message.content, actionCandidates)
                                : []
                            : [];
                        const matchedActionCandidates = dedupeActionCandidates(matched);
                        const createPlanDisabledReason = '';
                        const answerActionRecords =
                          isAssistantMessageWithContent
                            ? latestAnswerActionRecords({
                                actionRefs: effectiveSessionActionRefs,
                                aiopsStatus,
                                executionMode,
                                messageAnchor: messageActionAnchor,
                                messageContent: message.content,
                              })
                            : [];
                        const exactAnswerActionRefs =
                          isAssistantMessageWithContent && messageActionAnchor
                            ? effectiveSessionActionRefs.filter(
                                (ref) => ref.messageAnchor === messageActionAnchor,
                              )
                            : [];
                        const answerActionRefs =
                          exactAnswerActionRefs.length > 0
                            ? sortConversationActionRefsForDisplay(exactAnswerActionRefs).slice(0, 3)
                            : isLatestAssistantMessage && hasContent
                              ? sortConversationActionRefsForDisplay(effectiveSessionActionRefs).slice(0, 3)
                              : [];
                        const pendingActionCandidates = pendingActionCandidatesForRefs(
                          matchedActionCandidates,
                          answerActionRefs,
                        );
                        const candidateActionRecords =
                          isLatestAssistantMessage &&
                          hasContent &&
                          answerActionRecords.length === 0 &&
                          answerActionRefs.length === 0
                            ? actionRecordsForMatchedCandidates(
                                aiopsStatus,
                                executionMode,
                                matchedActionCandidates,
                              )
                            : [];
                        const resolvedAnswerActionRecords =
                          answerActionRecords.length > 0 ? answerActionRecords : candidateActionRecords;
                        const candidateActionRefsById =
                          groupActionRefsByCandidateId(answerActionRefs);
                        const candidateActionRecordsById = groupActionRecordsByCandidateId(
                          resolvedAnswerActionRecords,
                          answerActionRefs,
                        );
                        const visibleActionCandidates =
                          Object.keys(candidateActionRefsById).length > 0
                            ? matchedActionCandidates
                            : pendingActionCandidates;
                        const inlineActionRecordKeys = new Set(
                          Object.values(candidateActionRecordsById)
                            .flat()
                            .map(actionRecordInlineKey),
                        );
                        const inlineActionActivityVisible = visibleActionCandidates.some(
                          (candidate) =>
                            (candidateActionRecordsById[candidate.id]?.length ?? 0) > 0 ||
                            (candidateActionRefsById[candidate.id]?.length ?? 0) > 0,
                        );
                        const remainingAnswerActionRecords = resolvedAnswerActionRecords.filter(
                          (record) => !inlineActionRecordKeys.has(actionRecordInlineKey(record)),
                        );
                        const remainingAnswerActionRefs = answerActionRefs.filter(
                          (ref) => !ref.candidateId,
                        );
                        const showCreateActionPlanButtons =
                          visibleActionCandidates.length > 0;
                        const showActionPrepGroup =
                          Boolean(message.toolPlan) && showCreateActionPlanButtons;
                        const waitingForContent =
                          activeMessage && message.role === 'assistant' && !hasContent;
                        const assistantStillStreaming =
                          message.role === 'assistant' && message.streaming === true;
                        const canShowAssistantPostAnswer =
                          message.role === 'assistant' && hasContent && !assistantStillStreaming;
                        const messageTime = formatMessageTime(message.timestamp, uiLanguage);
                        return (
                          <div
                            className={`komsco-ai__message komsco-ai__message--${message.role}`}
                            data-action-anchor={
                              messageActionAnchor
                            }
                            data-message-index={index}
                            key={`${message.role}-${index}`}
                          >
                            <div className="komsco-ai__message-stack">
                              <AssistantMessageHeader
                                hasContent={hasContent}
                                language={uiLanguage}
                                message={message}
                              />
                              {(hasContent || (!hasProgress && !waitingForContent)) && (
                                <div className="komsco-ai__message-content">
                                  <AssistantFollowupMessageContent
                                    enabled={
                                      canShowAssistantPostAnswer && isLatestAssistantMessage
                                    }
                                    language={uiLanguage}
                                    message={message}
                                    onPreviewAttachment={openAttachmentPreview}
                                    onSelect={sendFollowupChoice}
                                    visible={isLatestAssistantMessage && hasContent}
                                  />
                                </div>
                              )}
                              {canShowAssistantPostAnswer &&
                                (
                                  <AssistantEvidenceFooter
                                    footer={message.evidenceFooter}
                                    language={uiLanguage}
                                    messageContent={message.content}
                                  />
                                )}
                              {canShowAssistantPostAnswer &&
                                showActionPrepGroup &&
                                (
                                  <div className="komsco-ai__action-prep" data-aiops-action-prep>
                                    <AssistantToolPlanFooter
                                      executionMode={executionMode}
                                      language={uiLanguage}
                                      toolPlan={message.toolPlan}
                                    />
                                    <AssistantCreateActionPlanButtons
                                      actionFeedback={actionCandidateFeedback}
                                      actionRecordsByCandidateId={candidateActionRecordsById}
                                      actionRefsByCandidateId={candidateActionRefsById}
                                      aiopsStatus={aiopsStatus}
                                      busyActionId={aiopsActionBusyId}
		                                    busyCandidateId={busyActionCandidateId}
		                                    candidates={visibleActionCandidates}
                                      createDisabledReason={createPlanDisabledReason}
                                      executionMode={executionMode}
		                                    language={uiLanguage}
                                      onAction={handleAiopsAction}
		                                    onCreatePlan={handleCreateActionPlanFromChat}
                                      resolveAction={getAiopsRecordAction}
		                                  />
                                  </div>
                                )}
                              {canShowAssistantPostAnswer &&
                                !showActionPrepGroup &&
                                <AssistantToolPlanFooter
                                  executionMode={executionMode}
                                  language={uiLanguage}
                                  toolPlan={message.toolPlan}
                                />}
                              {canShowAssistantPostAnswer &&
                                !showActionPrepGroup &&
                                showCreateActionPlanButtons &&
                                (
	                                  <AssistantCreateActionPlanButtons
	                                      actionFeedback={actionCandidateFeedback}
                                      actionRecordsByCandidateId={candidateActionRecordsById}
                                      actionRefsByCandidateId={candidateActionRefsById}
                                      aiopsStatus={aiopsStatus}
                                      busyActionId={aiopsActionBusyId}
		                                    busyCandidateId={busyActionCandidateId}
		                                    candidates={visibleActionCandidates}
                                      createDisabledReason={createPlanDisabledReason}
                                      executionMode={executionMode}
		                                    language={uiLanguage}
                                      onAction={handleAiopsAction}
		                                    onCreatePlan={handleCreateActionPlanFromChat}
                                      resolveAction={getAiopsRecordAction}
		                                  />
                                )}
                              {canShowAssistantPostAnswer &&
                                (
                                  <AssistantAnswerActions
                                    aiopsActionError={aiopsActionError}
                                    aiopsActionNotice={
                                      inlineActionActivityVisible ? '' : aiopsActionNotice
                                    }
                                    aiopsStatus={aiopsStatus}
                                    busyActionId={aiopsActionBusyId}
                                    executionMode={executionMode}
                                    fallbackRefs={remainingAnswerActionRefs}
                                    language={uiLanguage}
                                    onAction={handleAiopsAction}
                                    records={remainingAnswerActionRecords}
                                    resolveAction={getAiopsRecordAction}
                                  />
                                )}
                              {hasProgress && message.progressSteps && (
                                <ProgressTimeline
                                  active={activeMessage}
                                  language={uiLanguage}
                                  steps={message.progressSteps}
                                />
                              )}
                              {messageTime && (
                                <div className="komsco-ai__message-time">{messageTime}</div>
                              )}
                              {hasContent &&
                                (message.role === 'user' ||
                                  (message.role === 'assistant' && !assistantStillStreaming)) && (
                                  <MessageActionFooter
                                    copied={copiedMessageIndex === index}
                                    copiedLabel={copy.answerCopied}
                                    copyLabel={copy.answerCopy}
                                    feedback={message.feedback}
                                    feedbackComment={message.feedbackComment}
                                    language={uiLanguage}
                                    onCopy={() => copyMessage(message, index)}
                                    onEditForResend={
                                      message.role === 'user'
                                        ? () => editMessageForResend(message)
                                        : undefined
                                    }
                                    onFeedback={
                                      message.role === 'assistant'
                                        ? (feedback) => toggleMessageFeedback(index, feedback)
                                        : undefined
                                    }
                                    role={message.role}
                                  />
                                )}
                              {hasContent &&
                                message.role === 'assistant' &&
                                !assistantStillStreaming &&
                                message.feedback && (
                                <MessageFeedbackComment
                                  comment={message.feedbackComment}
                                  feedback={message.feedback}
                                  key={`${index}-${message.feedback}`}
                                  language={uiLanguage}
                                  onSubmit={(comment) => submitMessageFeedbackComment(index, comment)}
                                />
                              )}
                            </div>
                          </div>
                        );
                      })}
                      <div ref={bodyEndRef} />
                    </div>
                  </CardBody>

                  <AssistantComposer
                    assistantTaskMode={assistantTaskMode}
                    attachmentError={attachmentError}
                    autoProposeActions={autoProposeActions}
                    cancelAssistantResponse={cancelAssistantResponse}
                    copy={copy}
                    dragActive={dragActive}
                    executionMode={executionMode}
                    fileInputRef={fileInputRef}
                    input={input}
                    loading={loading}
                    onDragEnter={handleAttachmentDragEnter}
                    onDragLeave={handleAttachmentDragLeave}
                    onDragOver={handleAttachmentDragOver}
                    onDrop={handleAttachmentDrop}
                    onFileInputChange={handleFileInputChange}
                    onInputChange={setInput}
                    onPaste={handlePaste}
                    onPreviewAttachment={openAttachmentPreview}
                    onRemoveAttachment={removeAttachment}
                    onScrollToBottom={() => {
                      setStickToBottom(true);
                      setShowScrollToBottom(false);
                      scrollToBottom('auto');
                    }}
                    onSend={send}
                    pendingAttachments={pendingAttachments}
                    quickPromptMenuOpen={quickPromptMenuOpen}
                    quickPromptMenuRef={quickPromptMenuRef}
                    setAssistantTaskMode={setAssistantTaskMode}
                    setAutoProposeActions={setAutoProposeActions}
                    setQuickPromptMenuOpen={setQuickPromptMenuOpen}
                    setTaskModeMenuOpen={setTaskModeMenuOpen}
                    showScrollToBottom={showScrollToBottom}
                    taskModeMenuOpen={taskModeMenuOpen}
                    taskModeMenuRef={taskModeMenuRef}
                    uiLanguage={uiLanguage}
                  />
                </div>
                <AssistantInsightRail
                  aiopsActionBusyId={aiopsActionBusyId}
                  aiopsActionError={aiopsActionError}
                  aiopsActionNotice={aiopsActionNotice}
                  aiopsStatus={aiopsStatus}
                  aiopsStatusError={aiopsStatusError}
                  conversationHistory={conversationHistory}
                  error={clusterSummaryError}
                  executionMode={executionMode}
                  language={uiLanguage}
                  loading={clusterSummaryLoading}
                  messages={messages}
                  onAiopsAction={handleAiopsAction}
                  summary={clusterSummary}
                />
              </div>
            </Card>
            {panelResizeUnlocked && !fullScreen && (
              <AssistantResizeHandles copy={copy} onResizeStart={startPanelResize} />
            )}
          </div>
        </AssistantSurfacePortal>
      )}
      {previewAttachment && (
        <AssistantImageLightbox
          attachment={previewAttachment}
          language={uiLanguage}
          onClose={closeAttachmentPreview}
        />
      )}
    </div>
  );
};

export default AssistantLauncher;
