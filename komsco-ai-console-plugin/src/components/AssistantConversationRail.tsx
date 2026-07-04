import * as React from 'react';

import { messagePreview } from './assistant.display';
import { formatHistoryTime, languageLocale } from './assistant.storage';
import type { ConversationHistoryItem, Message, UiLanguage, UiTone } from './assistant.types';

const messageTime = (timestamp: number | undefined, language: UiLanguage): string => {
  if (!timestamp) {
    return '시간 대기';
  }

  return new Date(timestamp).toLocaleTimeString(languageLocale(language), {
    hour: '2-digit',
    minute: '2-digit',
  });
};

const conversationMessages = (messages: Message[]): Message[] =>
  messages.filter((message) => message.role === 'user' || message.role === 'assistant');

const latestMessageByRole = (
  messages: Message[],
  role: 'user' | 'assistant',
): Message | undefined =>
  [...messages].reverse().find((message) => message.role === role && message.content.trim());

const StatusTag: React.FC<{
  label: string;
  tone?: UiTone;
}> = ({ label, tone = 'neutral' }) => (
  <span className={`komsco-ai__scope-tag komsco-ai__scope-tag--${tone}`}>{label}</span>
);

type AssistantConversationRailProps = {
  conversationHistory: ConversationHistoryItem[];
  language: UiLanguage;
  messages: Message[];
};

const AssistantConversationRail: React.FC<AssistantConversationRailProps> = ({
  conversationHistory,
  language,
  messages,
}) => {
  const visibleMessages = conversationMessages(messages);
  const latestUser = latestMessageByRole(visibleMessages, 'user');
  const latestAssistant = latestMessageByRole(visibleMessages, 'assistant');
  const timeline = visibleMessages.slice(-4);

  return (
    <>
      <div className="komsco-ai__rail-section">
        <div className="komsco-ai__rail-section-head">
          <strong>대화 요약</strong>
          <span>{visibleMessages.length}건</span>
        </div>
        {latestUser || latestAssistant ? (
          <>
            <div className="komsco-ai__rail-command">
              <code>최근 질문 · {messageTime(latestUser?.timestamp, language)}</code>
              <p>{latestUser ? messagePreview(latestUser.content) : '아직 질문이 없습니다.'}</p>
            </div>
            <div className="komsco-ai__rail-command">
              <code>최근 답변 · {messageTime(latestAssistant?.timestamp, language)}</code>
              <p>
                {latestAssistant
                  ? messagePreview(latestAssistant.content)
                  : '아직 답변이 없습니다.'}
              </p>
            </div>
          </>
        ) : (
          <div className="komsco-ai__rail-empty">
            질문을 보내면 요약과 답변 흐름이 여기에 남습니다.
          </div>
        )}
      </div>

      <div className="komsco-ai__rail-section">
        <div className="komsco-ai__rail-section-head">
          <strong>질문·답변 타임라인</strong>
          <span>최신 {timeline.length}건</span>
        </div>
        {timeline.length > 0 ? (
          timeline.map((message, index) => (
            <div
              className="komsco-ai__rail-command"
              data-message-role={message.role}
              key={`${message.timestamp ?? index}-${message.role}`}
            >
              <div className="komsco-ai__rail-command-head">
                <div className="komsco-ai__rail-command-title">
                  <span>{message.role === 'user' ? '사용자' : 'AIOps'}</span>
                  <code>{messageTime(message.timestamp, language)}</code>
                </div>
                <StatusTag label={message.role === 'user' ? '질문' : '답변'} />
              </div>
              <p>{messagePreview(message.content)}</p>
            </div>
          ))
        ) : (
          <div className="komsco-ai__rail-empty">아직 질문·답변 타임라인이 없습니다.</div>
        )}
      </div>

      <div className="komsco-ai__rail-section">
        <div className="komsco-ai__rail-section-head">
          <strong>저장된 리포트</strong>
          <span>{conversationHistory.length}건</span>
        </div>
        {conversationHistory.length > 0 ? (
          conversationHistory.slice(0, 3).map((item) => (
            <div className="komsco-ai__rail-command" key={item.id}>
              <code>{formatHistoryTime(item.updatedAt, language)}</code>
              <p>{item.title}</p>
            </div>
          ))
        ) : (
          <div className="komsco-ai__rail-empty">
            저장된 분석 대화가 있으면 이곳에서 다시 확인합니다.
          </div>
        )}
      </div>
    </>
  );
};

export default AssistantConversationRail;
