import * as React from 'react';
import {
  CoolInfoIcon,
  CoolUserCircleIcon,
} from './coolicons';
import { UI_COPY } from './assistant.copy';
import type { Message, UiLanguage } from './assistant.types';
import aiopsIcon from '../assets/aiops_icon.svg';

type AssistantMessageHeaderProps = {
  hasContent: boolean;
  language: UiLanguage;
  message: Message;
};

const getMessageLabel = (message: Message, language: UiLanguage): string => {
  if (message.role === 'user') {
    return UI_COPY[language].userLabel;
  }

  if (message.role === 'system') {
    return UI_COPY[language].systemLabel;
  }

  return 'AIOps for OCP';
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

const assistantSourceLabel = (message: Message, language: UiLanguage): string => {
  const isKo = language === 'ko';

  if (message.fallbackAnswer || message.answerSource === 'gateway_fallback') {
    return 'Gateway fallback';
  }
  if (message.answerSource === 'ols') {
    return isKo ? 'Lightspeed 연결' : 'Lightspeed connected';
  }
  if (message.answerSource === 'ols_unavailable') {
    return isKo ? 'Lightspeed 응답 없음' : 'Lightspeed unavailable';
  }
  if (message.answerSource === 'gateway_direct') {
    return isKo ? 'Gateway 실조회' : 'Gateway live query';
  }
  if (message.answerSource === 'copilot_reply') {
    return isKo ? 'OCP 안내' : 'OCP guide';
  }
  if (message.answerSource === 'copilot_clarification') {
    return isKo ? '요청 확인' : 'Request clarification';
  }
  return isKo ? '응답 경로 확인 중' : 'Resolving answer source';
};

const assistantSourceClass = (message: Message): string => {
  if (message.fallbackAnswer || message.answerSource === 'gateway_fallback') {
    return 'komsco-ai__message-source--fallback';
  }
  if (message.answerSource === 'ols') {
    return 'komsco-ai__message-source--ols';
  }
  if (message.answerSource === 'ols_unavailable') {
    return 'komsco-ai__message-source--fallback';
  }
  if (message.answerSource === 'copilot_reply') {
    return 'komsco-ai__message-source--aiops';
  }
  if (message.answerSource === 'copilot_clarification') {
    return 'komsco-ai__message-source--clarification';
  }
  return 'komsco-ai__message-source--aiops';
};

const assistantSourceTitle = (message: Message, language: UiLanguage): string => {
  const isKo = language === 'ko';

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
  if (message.answerSource === 'ols_unavailable') {
    return message.gatewayContextDigest
      ? `OpenShift Lightspeed final answer unavailable · ${message.gatewayContextDigest}`
      : 'OpenShift Lightspeed final answer unavailable';
  }
  if (message.answerSource === 'gateway_direct') {
    const label = isKo
      ? 'Gateway 실조회 · 결정형 조회라 Lightspeed를 호출하지 않았습니다'
      : 'Gateway live query · Deterministic lookup did not call Lightspeed';

    return message.gatewayContextDigest
      ? `${label} · ${message.gatewayContextDigest}`
      : label;
  }
  if (message.answerSource === 'copilot_reply') {
    return isKo
      ? 'AIOps for OCP 역할 안내입니다. 클러스터 조회나 변경은 실행하지 않았습니다.'
      : 'AIOps for OCP guidance. No cluster query or change was executed.';
  }
  if (message.answerSource === 'copilot_clarification') {
    return isKo
      ? '요청 대상과 작업 목적을 더 확인해야 합니다.'
      : 'The request needs a clearer target and task goal.';
  }
  return isKo ? '응답 경로를 확인하는 중입니다.' : 'Answer source is still being resolved';
};

const AssistantMessageHeader: React.FC<AssistantMessageHeaderProps> = ({
  hasContent,
  language,
  message,
}) => {
  const sourceLabel =
    message.role === 'assistant' && hasContent ? assistantSourceLabel(message, language) : '';

  return (
    <div className="komsco-ai__message-head">
      {message.role !== 'user' && (
        <div className="komsco-ai__message-avatar">
          <MessageIcon role={message.role} />
        </div>
      )}
      <div className="komsco-ai__message-label">{getMessageLabel(message, language)}</div>
      {sourceLabel && (
        <span
          className={`komsco-ai__message-source ${assistantSourceClass(message)}`}
          title={assistantSourceTitle(message, language)}
        >
          {sourceLabel}
        </span>
      )}
    </div>
  );
};

export default AssistantMessageHeader;
