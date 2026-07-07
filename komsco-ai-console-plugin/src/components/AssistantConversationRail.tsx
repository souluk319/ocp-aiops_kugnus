import * as React from 'react';

import { messagePreview } from './assistant.display';
import { formatHistoryTime, languageLocale } from './assistant.storage';
import type { ConversationHistoryItem, Message, UiLanguage, UiTone } from './assistant.types';

const messageTime = (timestamp: number | undefined, language: UiLanguage): string => {
  if (!timestamp) {
    return language === 'ko' ? '시간 대기' : 'Time pending';
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

const text = (language: UiLanguage, ko: string, en: string): string =>
  language === 'ko' ? ko : en;

const countText = (count: number, language: UiLanguage): string =>
  language === 'ko' ? `${count}건` : String(count);

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
          <strong>{text(language, '대화 요약', 'Conversation summary')}</strong>
          <span>{countText(visibleMessages.length, language)}</span>
        </div>
        {latestUser || latestAssistant ? (
          <>
            <div className="komsco-ai__rail-command">
              <code>
                {text(language, '최근 질문', 'Latest question')} ·{' '}
                {messageTime(latestUser?.timestamp, language)}
              </code>
              <p>
                {latestUser
                  ? messagePreview(latestUser.content)
                  : text(language, '아직 질문이 없습니다.', 'No question yet.')}
              </p>
            </div>
            <div className="komsco-ai__rail-command">
              <code>
                {text(language, '최근 답변', 'Latest answer')} ·{' '}
                {messageTime(latestAssistant?.timestamp, language)}
              </code>
              <p>
                {latestAssistant
                  ? messagePreview(latestAssistant.content)
                  : text(language, '아직 답변이 없습니다.', 'No answer yet.')}
              </p>
            </div>
          </>
        ) : (
          <div className="komsco-ai__rail-empty">
            {text(
              language,
              '질문을 보내면 요약과 답변 흐름이 여기에 남습니다.',
              'After you send a question, the summary and answer flow appear here.',
            )}
          </div>
        )}
      </div>

      <div className="komsco-ai__rail-section">
        <div className="komsco-ai__rail-section-head">
          <strong>{text(language, '질문·답변 타임라인', 'Question-answer timeline')}</strong>
          <span>
            {text(language, `최신 ${timeline.length}건`, `Latest ${timeline.length}`)}
          </span>
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
                  <span>
                    {message.role === 'user' ? text(language, '사용자', 'User') : 'AIOps for OCP'}
                  </span>
                  <code>{messageTime(message.timestamp, language)}</code>
                </div>
                <StatusTag
                  label={
                    message.role === 'user'
                      ? text(language, '질문', 'Question')
                      : text(language, '답변', 'Answer')
                  }
                />
              </div>
              <p>{messagePreview(message.content)}</p>
            </div>
          ))
        ) : (
          <div className="komsco-ai__rail-empty">
            {text(
              language,
              '아직 질문·답변 타임라인이 없습니다.',
              'No question-answer timeline yet.',
            )}
          </div>
        )}
      </div>

      <div className="komsco-ai__rail-section">
        <div className="komsco-ai__rail-section-head">
          <strong>{text(language, '저장된 리포트', 'Saved reports')}</strong>
          <span>{countText(conversationHistory.length, language)}</span>
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
            {text(
              language,
              '저장된 분석 대화가 있으면 이곳에서 다시 확인합니다.',
              'Saved analysis conversations appear here.',
            )}
          </div>
        )}
      </div>
    </>
  );
};

export default AssistantConversationRail;
