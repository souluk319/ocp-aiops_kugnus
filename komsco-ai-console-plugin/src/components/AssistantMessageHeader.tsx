import * as React from 'react';
import {
  CoolCopyIcon,
  CoolInfoIcon,
  CoolUserCircleIcon,
} from './coolicons';
import { UI_COPY } from './assistant.copy';
import type { Message, UiLanguage } from './assistant.types';
import aiopsIcon from '../assets/aiops_icon.svg';

type AssistantMessageHeaderProps = {
  copied: boolean;
  copyLabel: string;
  copiedLabel: string;
  hasContent: boolean;
  language: UiLanguage;
  message: Message;
  onCopy: () => void;
};

const getMessageLabel = (role: Message['role'], language: UiLanguage): string => {
  if (role === 'user') {
    return UI_COPY[language].userLabel;
  }

  if (role === 'system') {
    return UI_COPY[language].systemLabel;
  }

  return 'AIOps';
};

const MessageIcon: React.FC<{ role: Message['role'] }> = ({ role }) => {
  if (role === 'user') {
    return <CoolUserCircleIcon />;
  }

  if (role === 'system') {
    return <CoolInfoIcon />;
  }

  return <img alt="" className="komsco-ai__message-logo" src={aiopsIcon} />;
};

const AssistantMessageHeader: React.FC<AssistantMessageHeaderProps> = ({
  copied,
  copiedLabel,
  copyLabel,
  hasContent,
  language,
  message,
  onCopy,
}) => {
  const assistantSourceLabel =
    message.role === 'assistant' && hasContent
      ? message.fallbackAnswer
        ? 'Gateway fallback'
        : 'AIOps 응답'
      : '';
  const assistantSourceTitle = message.fallbackAnswer
    ? message.gatewayContextDigest
      ? `Gateway context ${message.gatewayContextDigest}`
      : 'Gateway fallback answer'
    : 'AIOps answer';

  return (
    <div className="komsco-ai__message-head">
      {message.role !== 'user' && (
        <div className="komsco-ai__message-avatar">
          <MessageIcon role={message.role} />
        </div>
      )}
      <div className="komsco-ai__message-label">{getMessageLabel(message.role, language)}</div>
      {assistantSourceLabel && (
        <span
          className={`komsco-ai__message-source ${
            message.fallbackAnswer
              ? 'komsco-ai__message-source--fallback'
              : 'komsco-ai__message-source--aiops'
          }`}
          title={assistantSourceTitle}
        >
          {assistantSourceLabel}
        </span>
      )}
      {message.role === 'assistant' && hasContent && (
        <button
          aria-label={copyLabel}
          className="komsco-ai__message-copy"
          onClick={onCopy}
          title={copyLabel}
          type="button"
        >
          <CoolCopyIcon />
          <span>{copied ? copiedLabel : copyLabel}</span>
        </button>
      )}
    </div>
  );
};

export default AssistantMessageHeader;
