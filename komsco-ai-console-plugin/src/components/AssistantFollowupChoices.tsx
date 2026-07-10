import * as React from 'react';
import { renderFormattedContent } from './AssistantMessageContent';
import {
  parseAssistantFollowupBlock,
  rewriteAssistantFollowupQuery,
  type AssistantFollowupOption,
} from './assistant.followups';
import type { Message, UiLanguage } from './assistant.types';
import type { ImageAttachment } from '../services/aiGateway';

type AssistantFollowupChoicesProps = {
  disabled?: boolean;
  language: UiLanguage;
  onSelect: (prompt: string) => boolean | Promise<boolean>;
  options: AssistantFollowupOption[];
};

type AssistantFollowupMessageContentProps = {
  enabled: boolean;
  language: UiLanguage;
  message: Message;
  onPreviewAttachment: (attachment: ImageAttachment) => void;
  onSelect: (prompt: string) => boolean | Promise<boolean>;
  visible: boolean;
};

export const AssistantFollowupChoices: React.FC<AssistantFollowupChoicesProps> = ({
  disabled = false,
  language,
  onSelect,
  options,
}) => {
  const selectionLockRef = React.useRef(false);
  const [selectedIndex, setSelectedIndex] = React.useState<number | null>(null);
  const title =
    language === 'en' ? 'What would you like to check next?' : '다음으로 무엇을 확인할까요?';

  const selectOption = React.useCallback(
    async (option: AssistantFollowupOption) => {
      if (disabled || selectionLockRef.current) {
        return;
      }
      selectionLockRef.current = true;
      setSelectedIndex(option.index);
      try {
        const accepted = await onSelect(rewriteAssistantFollowupQuery(option.prompt));
        if (!accepted) {
          selectionLockRef.current = false;
          setSelectedIndex(null);
        }
      } catch (_error) {
        selectionLockRef.current = false;
        setSelectedIndex(null);
      }
    },
    [disabled, onSelect],
  );

  return (
    <section
      aria-label={title}
      className="komsco-ai__followup-choice-group"
      data-aiops-followup-choices
    >
      <div className="komsco-ai__followup-choice-title">{title}</div>
      <div className="komsco-ai__followup-choice-list" role="group">
        {options.map((option) => {
          const selected = selectedIndex === option.index;
          const selectionLabel =
            language === 'en'
              ? `Select option ${option.index}: ${option.prompt}`
              : `${option.index}번 선택: ${option.prompt}`;
          return (
            <button
              aria-label={selectionLabel}
              className="komsco-ai__followup-choice"
              data-selected={selected ? 'true' : 'false'}
              disabled={disabled || selectedIndex !== null}
              key={`${option.index}-${option.prompt}`}
              onClick={() => void selectOption(option)}
              type="button"
            >
              <span aria-hidden="true" className="komsco-ai__followup-choice-number">
                {option.index}
              </span>
              <span className="komsco-ai__followup-choice-text">{option.prompt}</span>
            </button>
          );
        })}
      </div>
    </section>
  );
};

const renderMessageSegment = (
  message: Message,
  content: string,
  onPreviewAttachment: (attachment: ImageAttachment) => void,
  language: UiLanguage,
): React.ReactNode => {
  if (!content.trim()) {
    return null;
  }
  return renderFormattedContent({ ...message, content }, onPreviewAttachment, language);
};

const AssistantFollowupMessageContent: React.FC<AssistantFollowupMessageContentProps> = ({
  enabled,
  language,
  message,
  onPreviewAttachment,
  onSelect,
  visible,
}) => {
  const followups = visible ? parseAssistantFollowupBlock(message.content) : null;
  if (!followups) {
    return <>{renderFormattedContent(message, onPreviewAttachment, language)}</>;
  }

  return (
    <>
      {renderMessageSegment(message, followups.before, onPreviewAttachment, language)}
      <AssistantFollowupChoices
        disabled={!enabled}
        language={language}
        onSelect={onSelect}
        options={followups.options}
      />
      {renderMessageSegment(message, followups.after, onPreviewAttachment, language)}
    </>
  );
};

export default AssistantFollowupMessageContent;
