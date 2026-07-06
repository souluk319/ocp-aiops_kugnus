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

const assistantSourceLabel = (message: Message): string => {
  if (message.fallbackAnswer || message.answerSource === 'gateway_fallback') {
    return 'Gateway fallback';
  }
  if (message.answerSource === 'ols') {
    return 'OLS 연결';
  }
  if (message.answerSource === 'gateway_direct') {
    return 'Gateway 직접조회';
  }
  return '응답 경로 확인 중';
};

const assistantSourceClass = (message: Message): string => {
  if (message.fallbackAnswer || message.answerSource === 'gateway_fallback') {
    return 'komsco-ai__message-source--fallback';
  }
  if (message.answerSource === 'ols') {
    return 'komsco-ai__message-source--ols';
  }
  return 'komsco-ai__message-source--aiops';
};

const assistantSourceTitle = (message: Message): string => {
  if (message.fallbackAnswer || message.answerSource === 'gateway_fallback') {
    return message.gatewayContextDigest
      ? `Gateway fallback · ${message.gatewayContextDigest}`
      : 'Gateway fallback answer';
  }
  if (message.answerSource === 'ols') {
    return message.gatewayContextDigest
      ? `OpenShift Lightspeed stream connected · ${message.gatewayContextDigest}`
      : 'OpenShift Lightspeed stream connected';
  }
  if (message.answerSource === 'gateway_direct') {
    return message.gatewayContextDigest
      ? `Gateway direct evidence response · ${message.gatewayContextDigest}`
      : 'Gateway direct evidence response';
  }
  return 'Answer source is still being resolved';
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
  const sourceLabel =
    message.role === 'assistant' && hasContent ? assistantSourceLabel(message) : '';

  return (
    <div className="komsco-ai__message-head">
      {message.role !== 'user' && (
        <div className="komsco-ai__message-avatar">
          <MessageIcon role={message.role} />
        </div>
      )}
      <div className="komsco-ai__message-label">{getMessageLabel(message.role, language)}</div>
      {sourceLabel && (
        <span
          className={`komsco-ai__message-source ${assistantSourceClass(message)}`}
          title={assistantSourceTitle(message)}
        >
          {sourceLabel}
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
