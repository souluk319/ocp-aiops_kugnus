import * as React from 'react';
import { CoolCopyIcon, CoolPencilIcon, CoolThumbsDownIcon, CoolThumbsUpIcon } from './coolicons';
import { STORED_MESSAGE_FEEDBACK_KEY } from './assistant.constants';
import type { Message, UiLanguage } from './assistant.types';
import type { ChatFeedbackPayload } from '../services/aiGateway';

export type MessageFeedbackChoice = 'up' | 'down';

export type MessageActionFooterProps = {
  copied: boolean;
  copiedLabel: string;
  copyLabel: string;
  feedback?: MessageFeedbackChoice;
  feedbackComment?: string;
  language: UiLanguage;
  onCopy: () => void;
  onEditForResend?: () => void;
  onFeedback?: (feedback: MessageFeedbackChoice) => void;
  role: Message['role'];
};

const messageActionLabels = (language: UiLanguage) =>
  language === 'en'
    ? {
        copy: 'Copy',
        copied: 'Copied',
        dislike: 'Bad response',
        edit: 'Edit and resend',
        feedbackCommentSaved: 'Saved',
        feedbackCommentSubmit: 'Save',
        dislikeSaved: 'Needs work saved',
        dislikeSelected: 'Needs work selected',
        like: 'Good response',
        likeSaved: 'Good response saved',
        likeSelected: 'Good response selected',
      }
    : {
        copy: '복사',
        copied: '복사됨',
        dislike: '좋지 않은 답변',
        edit: '수정해서 다시 보내기',
        feedbackCommentSaved: '저장됨',
        feedbackCommentSubmit: '저장',
        dislikeSaved: '싫어요 저장됨',
        dislikeSelected: '싫어요 선택됨',
        like: '좋은 답변',
        likeSaved: '좋아요 저장됨',
        likeSelected: '좋아요 선택됨',
      };

const feedbackCommentPlaceholder = (
  language: UiLanguage,
  feedback: MessageFeedbackChoice,
): string =>
  language === 'en'
    ? feedback === 'down'
      ? 'Note what was wrong or confusing'
      : 'Note what should stay this good'
    : feedback === 'down'
      ? '틀렸거나 불편한 점을 짧게 입력'
      : '유지할 만한 좋은 점을 짧게 입력';

const readStoredMessageFeedback = (): ChatFeedbackPayload[] => {
  if (typeof window === 'undefined') {
    return [];
  }

  try {
    const parsed = JSON.parse(window.localStorage.getItem(STORED_MESSAGE_FEEDBACK_KEY) || '[]');
    return Array.isArray(parsed) ? (parsed as ChatFeedbackPayload[]) : [];
  } catch {
    return [];
  }
};

const storedFeedbackKey = (
  payload: Pick<ChatFeedbackPayload, 'feedbackId' | 'messageId' | 'rating'>,
): string => payload.feedbackId || `${payload.messageId}:${payload.rating}`;

export const publicFeedbackAnswerContract = (message: Message): string | undefined => {
  const contract = message.answerContract?.trim();
  if (!contract) {
    return undefined;
  }

  return /fixture|local/i.test(contract) ? 'v0281-gateway-answer-contract' : contract;
};

export const publicFeedbackSource = (message: Message): NonNullable<Message['answerSource']> => {
  if (message.answerSource) {
    return message.answerSource;
  }
  if (message.fallbackAnswer) {
    return 'gateway_fallback';
  }
  if (message.toolPlan || message.evidenceFooter) {
    return 'gateway_direct';
  }
  return 'copilot_reply';
};

export const feedbackExcerpt = (value: string, maxLength: number): string | undefined => {
  const normalized = value.replace(/\s+/g, ' ').trim();
  if (!normalized) {
    return undefined;
  }
  return normalized.length > maxLength
    ? `${normalized.slice(0, maxLength - 1).trim()}…`
    : normalized;
};

export const previousUserMessageForFeedback = (
  messages: Message[],
  assistantIndex: number,
): string | undefined => {
  for (let index = assistantIndex - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message?.role === 'user') {
      return message.content;
    }
  }
  return undefined;
};

export const writeStoredMessageFeedback = (payload: ChatFeedbackPayload): void => {
  if (typeof window === 'undefined') {
    return;
  }

  const existing = readStoredMessageFeedback();
  const payloadKey = storedFeedbackKey(payload);
  const next = [
    payload,
    ...existing.filter((item) => storedFeedbackKey(item) !== payloadKey),
  ].slice(0, 200);
  window.localStorage.setItem(STORED_MESSAGE_FEEDBACK_KEY, JSON.stringify(next));
};

export const removeStoredMessageFeedback = (
  messageId: string,
  rating?: MessageFeedbackChoice,
): void => {
  if (typeof window === 'undefined') {
    return;
  }

  const next = readStoredMessageFeedback().filter(
    (item) => item.messageId !== messageId || (rating ? item.rating !== rating : false),
  );
  window.localStorage.setItem(STORED_MESSAGE_FEEDBACK_KEY, JSON.stringify(next));
};

const MessageActionButton: React.FC<{
  active?: boolean;
  children: React.ReactNode;
  label: string;
  onClick: () => void;
  pressed?: boolean;
}> = ({ active = false, children, label, onClick, pressed }) => (
  <button
    aria-label={label}
    aria-pressed={pressed}
    className="komsco-ai__message-action-button"
    data-active={active ? 'true' : undefined}
    onClick={onClick}
    title={label}
    type="button"
  >
    {children}
  </button>
);

export const MessageActionFooter: React.FC<MessageActionFooterProps> = ({
  copied,
  copiedLabel,
  copyLabel,
  feedback,
  feedbackComment,
  language,
  onCopy,
  onEditForResend,
  onFeedback,
  role,
}) => {
  const labels = messageActionLabels(language);
  const copyButtonLabel = copied ? copiedLabel || labels.copied : copyLabel || labels.copy;
  const feedbackHasSavedComment = Boolean(feedbackComment?.trim());
  const feedbackStatus =
    feedback === 'up'
      ? feedbackHasSavedComment
        ? labels.likeSaved
        : labels.likeSelected
      : feedback === 'down'
        ? feedbackHasSavedComment
          ? labels.dislikeSaved
          : labels.dislikeSelected
        : '';
  const statusLabel = copied ? copiedLabel || labels.copied : feedbackStatus;

  if (role === 'user') {
    return (
      <div className="komsco-ai__message-actions" data-message-actions="user">
        {statusLabel && (
          <span className="komsco-ai__message-action-status" role="status">
            {statusLabel}
          </span>
        )}
        {onEditForResend && (
          <MessageActionButton label={labels.edit} onClick={onEditForResend}>
            <CoolPencilIcon />
          </MessageActionButton>
        )}
        <MessageActionButton active={copied} label={copyButtonLabel} onClick={onCopy}>
          <CoolCopyIcon />
        </MessageActionButton>
      </div>
    );
  }

  if (role !== 'assistant') {
    return null;
  }

  return (
    <div className="komsco-ai__message-actions" data-message-actions="assistant">
      <MessageActionButton active={copied} label={copyButtonLabel} onClick={onCopy}>
        <CoolCopyIcon />
      </MessageActionButton>
      {onFeedback && (
        <>
          <MessageActionButton
            active={feedback === 'up'}
            label={labels.like}
            onClick={() => onFeedback('up')}
            pressed={feedback === 'up'}
          >
            <CoolThumbsUpIcon />
          </MessageActionButton>
          <MessageActionButton
            active={feedback === 'down'}
            label={labels.dislike}
            onClick={() => onFeedback('down')}
            pressed={feedback === 'down'}
          >
            <CoolThumbsDownIcon />
          </MessageActionButton>
        </>
      )}
      {statusLabel && (
        <span className="komsco-ai__message-action-status" role="status">
          {statusLabel}
        </span>
      )}
    </div>
  );
};

export const MessageFeedbackComment: React.FC<{
  comment?: string;
  feedback: MessageFeedbackChoice;
  language: UiLanguage;
  onSubmit: (comment: string) => void;
}> = ({ comment = '', feedback, language, onSubmit }) => {
  const labels = messageActionLabels(language);
  const [draft, setDraft] = React.useState(comment);

  React.useEffect(() => {
    setDraft(comment);
  }, [comment, feedback]);

  const trimmedDraft = draft.trim();
  const savedComment = comment.trim();
  const dirty = trimmedDraft !== savedComment;
  const hasSavedComment = savedComment.length > 0;
  const prompt =
    language === 'en'
      ? feedback === 'down'
        ? 'Improve'
        : 'Worked well'
      : feedback === 'down'
        ? '개선점'
        : '좋았던 점';
  const storageHint = language === 'en' ? 'saved: browser+Gateway' : '기록: 브라우저+Gateway';
  const storageHintTitle =
    language === 'en'
      ? `Browser localStorage: ${STORED_MESSAGE_FEEDBACK_KEY} · Gateway API: /v1/chat/feedback`
      : `브라우저 localStorage: ${STORED_MESSAGE_FEEDBACK_KEY} · Gateway API: /v1/chat/feedback`;

  return (
    <form
      className="komsco-ai__feedback-comment"
      onSubmit={(event) => {
        event.preventDefault();
        if (!dirty) {
          return;
        }
        onSubmit(trimmedDraft);
      }}
    >
      <div className="komsco-ai__feedback-comment-row">
        <label>
          <span className="komsco-ai__feedback-prompt" title={storageHintTitle}>
            {prompt} · {storageHint}
          </span>
          <input
            maxLength={1000}
            onChange={(event) => setDraft(event.target.value)}
            placeholder={feedbackCommentPlaceholder(language, feedback)}
            value={draft}
          />
        </label>
        <button disabled={!dirty} type="submit">
          {dirty
            ? labels.feedbackCommentSubmit
            : hasSavedComment
              ? labels.feedbackCommentSaved
              : labels.feedbackCommentSubmit}
        </button>
      </div>
    </form>
  );
};
