import * as React from 'react';

import {
  CoolInfoIcon,
  CoolShieldCheckIcon,
  CoolTerminalIcon,
} from './coolicons';
import type { AiopsExecutionMode, UiLanguage } from './assistant.types';

type AssistantExecutionModeToggleProps = {
  actionExecutionAvailable: boolean;
  actionExecutionDisabledReason: string;
  executionMode: AiopsExecutionMode;
  onExecutionModeChange: (mode: AiopsExecutionMode) => void;
  uiLanguage: UiLanguage;
};

const AssistantExecutionModeToggle: React.FC<AssistantExecutionModeToggleProps> = ({
  actionExecutionAvailable,
  actionExecutionDisabledReason,
  executionMode,
  onExecutionModeChange,
  uiLanguage,
}) => {
  const isKo = uiLanguage === 'ko';
  const copy = {
    group: isKo ? 'AIOps 실행 모드' : 'AIOps execution mode',
    readOnlyLabel: isKo ? '읽기 전용' : 'Read only',
    readOnlyAria: isKo ? '읽기 전용 모드' : 'Read-only mode',
    readOnlyTitle: isKo
      ? '조회와 근거 수집만 수행하고 조치 계획, 승인, 실행은 만들지 않습니다.'
      : 'Collects evidence only. It does not create plans, approvals, or executions.',
    executeLabel: isKo ? '실행 가능' : 'Execute',
    executeAria: isKo ? '승인 후 실행 모드' : 'Approval-gated execution mode',
    executeTitle: actionExecutionAvailable
      ? isKo
        ? '승인 후 실행 모드'
        : 'Approval-gated execution mode'
      : isKo
        ? `승인 후 실행 비활성: ${actionExecutionDisabledReason}`
        : `Execution disabled: ${actionExecutionDisabledReason}`,
    unrestrictedLabel: isKo ? '실행 무제한' : 'Unrestricted',
    unrestrictedAria: isKo ? '실험 무제한 모드' : 'Unrestricted lab mode',
    unrestrictedTitle: isKo ? '실험 무제한 모드' : 'Unrestricted lab mode',
  };

  return (
    <div className="komsco-ai__mode-toggle" role="group" aria-label={copy.group}>
      <button
        aria-label={copy.readOnlyAria}
        aria-pressed={executionMode === 'read-only'}
        className={`komsco-ai__mode-toggle-button${
          executionMode === 'read-only' ? ' komsco-ai__mode-toggle-button--active' : ''
        }`}
        onClick={() => onExecutionModeChange('read-only')}
        title={copy.readOnlyTitle}
        type="button"
      >
        <CoolShieldCheckIcon />
        <span>{copy.readOnlyLabel}</span>
      </button>
      <button
        aria-label={copy.executeAria}
        aria-pressed={executionMode === 'execute'}
        className={`komsco-ai__mode-toggle-button${
          executionMode === 'execute' ? ' komsco-ai__mode-toggle-button--active-execute' : ''
        }`}
        data-disabled-reason={!actionExecutionAvailable ? actionExecutionDisabledReason : undefined}
        onClick={() => onExecutionModeChange('execute')}
        title={copy.executeTitle}
        type="button"
      >
        <CoolTerminalIcon />
        <span>{copy.executeLabel}</span>
      </button>
      <button
        aria-label={copy.unrestrictedAria}
        aria-pressed={executionMode === 'unrestricted'}
        className={`komsco-ai__mode-toggle-button${
          executionMode === 'unrestricted' ? ' komsco-ai__mode-toggle-button--active-danger' : ''
        }`}
        onClick={() => onExecutionModeChange('unrestricted')}
        title={copy.unrestrictedTitle}
        type="button"
      >
        <CoolInfoIcon />
        <span>{copy.unrestrictedLabel}</span>
      </button>
    </div>
  );
};

export default AssistantExecutionModeToggle;
