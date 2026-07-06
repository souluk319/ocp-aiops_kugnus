import * as React from 'react';
import { Button, Switch, TextArea } from '@patternfly/react-core';

import {
  CoolArrowDownIcon,
  CoolCaretDownIcon,
  CoolCloseIcon,
  CoolPaperclipIcon,
  CoolPaperPlaneIcon,
  CoolPlusIcon,
  CoolShieldCheckIcon,
  CoolStopIcon,
} from './coolicons';
import {
  ASSISTANT_TASK_MODES,
  FILE_INPUT_ACCEPT,
  QUICK_PROMPTS,
  TASK_MODE_PLACEHOLDERS,
} from './assistant.constants';
import type { AssistantCopy } from './assistant.copy';
import { formatFileSize, getAttachmentPreviewUrl } from './assistant.attachments';
import type {
  AiopsExecutionMode,
  AssistantTaskMode,
  UiLanguage,
} from './assistant.types';
import type { ImageAttachment } from '../services/aiGateway';

type AssistantComposerProps = {
  assistantTaskMode: AssistantTaskMode;
  attachmentError: string;
  autoProposeActions: boolean;
  copy: AssistantCopy;
  dragActive: boolean;
  executionMode: AiopsExecutionMode;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  input: string;
  loading: boolean;
  pendingAttachments: ImageAttachment[];
  quickPromptMenuOpen: boolean;
  quickPromptMenuRef: React.RefObject<HTMLDivElement | null>;
  showScrollToBottom: boolean;
  taskModeMenuOpen: boolean;
  taskModeMenuRef: React.RefObject<HTMLDivElement | null>;
  uiLanguage: UiLanguage;
  cancelAssistantResponse: () => void;
  onDragEnter: React.DragEventHandler<HTMLDivElement>;
  onDragLeave: React.DragEventHandler<HTMLDivElement>;
  onDragOver: React.DragEventHandler<HTMLDivElement>;
  onDrop: React.DragEventHandler<HTMLDivElement>;
  onFileInputChange: React.ChangeEventHandler<HTMLInputElement>;
  onInputChange: (value: string) => void;
  onPaste: React.ClipboardEventHandler<HTMLTextAreaElement>;
  onPreviewAttachment: (attachment: ImageAttachment) => void;
  onRemoveAttachment: (id: string) => void;
  onScrollToBottom: () => void;
  onSend: (prompt?: string) => void | Promise<void>;
  setAssistantTaskMode: (mode: AssistantTaskMode) => void;
  setAutoProposeActions: (enabled: boolean) => void;
  setQuickPromptMenuOpen: React.Dispatch<React.SetStateAction<boolean>>;
  setTaskModeMenuOpen: React.Dispatch<React.SetStateAction<boolean>>;
};

const AssistantComposer: React.FC<AssistantComposerProps> = ({
  assistantTaskMode,
  attachmentError,
  autoProposeActions,
  cancelAssistantResponse,
  copy,
  dragActive,
  executionMode,
  fileInputRef,
  input,
  loading,
  onDragEnter,
  onDragLeave,
  onDragOver,
  onDrop,
  onFileInputChange,
  onInputChange,
  onPaste,
  onPreviewAttachment,
  onRemoveAttachment,
  onScrollToBottom,
  onSend,
  pendingAttachments,
  quickPromptMenuOpen,
  quickPromptMenuRef,
  setAssistantTaskMode,
  setAutoProposeActions,
  setQuickPromptMenuOpen,
  setTaskModeMenuOpen,
  showScrollToBottom,
  taskModeMenuOpen,
  taskModeMenuRef,
  uiLanguage,
}) => {
  const selectedTaskMode =
    ASSISTANT_TASK_MODES.find((item) => item.value === assistantTaskMode) ||
    ASSISTANT_TASK_MODES[0];

  return (
    <div
      className={`komsco-ai__composer-wrap${
        dragActive ? ' komsco-ai__composer-wrap--drag-active' : ''
      }`}
      onDragEnter={onDragEnter}
      onDragLeave={onDragLeave}
      onDragOver={onDragOver}
      onDrop={onDrop}
    >
      {showScrollToBottom && (
        <Button
          aria-label={copy.scrollToLatest}
          className="komsco-ai__scroll-bottom"
          onClick={onScrollToBottom}
          variant="secondary"
        >
          <CoolArrowDownIcon />
        </Button>
      )}
      <div className="komsco-ai__input">
        <input
          accept={FILE_INPUT_ACCEPT}
          aria-label={copy.fileAttach}
          className="komsco-ai__file-input"
          disabled={loading}
          multiple
          onChange={onFileInputChange}
          ref={fileInputRef as React.Ref<HTMLInputElement>}
          type="file"
        />
        <div className="komsco-ai__composer">
          {pendingAttachments.length > 0 && (
            <div className="komsco-ai__pending-attachments">
              {pendingAttachments.map((attachment) => (
                <div className="komsco-ai__pending-attachment" key={attachment.id}>
                  <button
                    aria-label={`${attachment.name} 크게 보기`}
                    className="komsco-ai__pending-attachment-preview"
                    onClick={() => onPreviewAttachment(attachment)}
                    title={`${attachment.name} · ${formatFileSize(attachment.size)}`}
                    type="button"
                  >
                    <img
                      alt={attachment.name}
                      className="komsco-ai__pending-attachment-image"
                      src={getAttachmentPreviewUrl(attachment)}
                    />
                  </button>
                  <Button
                    aria-label={`${attachment.name} 첨부 제거`}
                    className="komsco-ai__attachment-remove"
                    isDisabled={loading}
                    onClick={(event) => {
                      event.stopPropagation();
                      onRemoveAttachment(attachment.id);
                    }}
                    variant="plain"
                  >
                    <CoolCloseIcon />
                  </Button>
                </div>
              ))}
            </div>
          )}
          {attachmentError && (
            <div className="komsco-ai__attachment-error">{attachmentError}</div>
          )}
          <TextArea
            aria-label="Question"
            autoResize
            className="komsco-ai__textarea"
            onChange={(_, value) => onInputChange(value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                void onSend();
              }
            }}
            onPaste={onPaste}
            placeholder={
              uiLanguage === 'ko'
                ? TASK_MODE_PLACEHOLDERS[assistantTaskMode]
                : copy.inputPlaceholder
            }
            rows={1}
            style={{ maxHeight: 76, minHeight: 32, overflowY: 'auto' }}
            value={input}
          />
          <div className="komsco-ai__composer-toolbar">
            <div className="komsco-ai__composer-tools">
              <div
                className="komsco-ai__quick-menu"
                ref={quickPromptMenuRef as React.Ref<HTMLDivElement>}
              >
                <Button
                  aria-expanded={quickPromptMenuOpen}
                  aria-label="자주 쓰는 점검 질문 열기"
                  aria-haspopup="menu"
                  className="komsco-ai__tool-button komsco-ai__quick-menu-trigger"
                  isDisabled={loading}
                  onClick={() => {
                    setQuickPromptMenuOpen((value) => !value);
                    setTaskModeMenuOpen(false);
                  }}
                  variant="plain"
                >
                  <CoolPlusIcon />
                </Button>
                {quickPromptMenuOpen && (
                  <div className="komsco-ai__quick-menu-panel" role="menu">
                    {executionMode === 'execute' && (
                      <div
                        aria-checked={autoProposeActions}
                        className="komsco-ai__quick-menu-item komsco-ai__quick-menu-item--toggle"
                        role="menuitemcheckbox"
                      >
                        <span className="komsco-ai__quick-prompt-icon">
                          <CoolShieldCheckIcon />
                        </span>
                        <span className="komsco-ai__quick-menu-copy">
                          <strong>조치 계획 기본 제공</strong>
                          <small>
                            질문마다 조치 계획을 먼저 보여줍니다. 끄면 요청할 때만 만듭니다.
                          </small>
                        </span>
                        <Switch
                          aria-label="답변 후 조치 계획 기본 제공"
                          id="komsco-ai-auto-propose-toggle"
                          isChecked={autoProposeActions}
                          onChange={(_event, checked) => setAutoProposeActions(checked)}
                        />
                      </div>
                    )}
                    {QUICK_PROMPTS.map((item) => (
                      <button
                        className="komsco-ai__quick-menu-item"
                        key={item.label}
                        onClick={() => {
                          setQuickPromptMenuOpen(false);
                          void onSend(item.prompt);
                        }}
                        role="menuitem"
                        type="button"
                      >
                        <span className="komsco-ai__quick-prompt-icon">{item.icon}</span>
                        <span className="komsco-ai__quick-menu-copy">
                          <strong>{item.label}</strong>
                          <small>{item.prompt}</small>
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <Button
                aria-label="파일 첨부"
                className="komsco-ai__tool-button komsco-ai__attach"
                isDisabled={loading}
                onClick={() => fileInputRef.current?.click()}
                variant="plain"
              >
                <CoolPaperclipIcon />
              </Button>
              <div
                className="komsco-ai__task-mode"
                ref={taskModeMenuRef as React.Ref<HTMLDivElement>}
              >
                <button
                  aria-expanded={taskModeMenuOpen}
                  aria-haspopup="listbox"
                  className="komsco-ai__task-mode-button"
                  data-assistant-task-mode={assistantTaskMode}
                  disabled={loading}
                  onClick={() => {
                    setTaskModeMenuOpen((value) => !value);
                    setQuickPromptMenuOpen(false);
                  }}
                  type="button"
                >
                  <span className="komsco-ai__task-mode-icon">{selectedTaskMode.icon}</span>
                  <span className="komsco-ai__task-mode-label">{selectedTaskMode.label}</span>
                  <CoolCaretDownIcon />
                </button>
                {taskModeMenuOpen && (
                  <div className="komsco-ai__task-mode-menu" role="listbox">
                    {ASSISTANT_TASK_MODES.map((item) => (
                      <button
                        aria-selected={assistantTaskMode === item.value}
                        className="komsco-ai__task-mode-option"
                        data-komsco-task-mode={item.value}
                        key={item.value}
                        onClick={() => {
                          setAssistantTaskMode(item.value);
                          setTaskModeMenuOpen(false);
                        }}
                        role="option"
                        type="button"
                      >
                        <span className="komsco-ai__task-mode-icon">{item.icon}</span>
                        <span>
                          <strong>{item.label}</strong>
                          <small>{item.description}</small>
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
            <Button
              aria-label={loading ? '응답 중지' : '질문 전송'}
              className={`komsco-ai__send${loading ? ' komsco-ai__send--stop' : ''}`}
              isDisabled={!loading && !input.trim() && pendingAttachments.length === 0}
              onClick={() => {
                if (loading) {
                  cancelAssistantResponse();
                  return;
                }
                void onSend();
              }}
              variant="plain"
            >
              {loading ? <CoolStopIcon /> : <CoolPaperPlaneIcon />}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AssistantComposer;
