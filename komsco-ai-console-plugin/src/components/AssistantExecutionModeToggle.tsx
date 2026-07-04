import * as React from 'react';

import {
  CoolInfoIcon,
  CoolShieldCheckIcon,
  CoolTerminalIcon,
} from './coolicons';
import type { AiopsExecutionMode } from './assistant.types';

type AssistantExecutionModeToggleProps = {
  actionExecutionAvailable: boolean;
  actionExecutionDisabledReason: string;
  executionMode: AiopsExecutionMode;
  onExecutionModeChange: (mode: AiopsExecutionMode) => void;
};

const AssistantExecutionModeToggle: React.FC<AssistantExecutionModeToggleProps> = ({
  actionExecutionAvailable,
  actionExecutionDisabledReason,
  executionMode,
  onExecutionModeChange,
}) => (
  <div className="komsco-ai__mode-toggle" role="group" aria-label="AIOps 실행 모드">
    <button
      aria-label="읽기 전용 모드"
      aria-pressed={executionMode === 'read-only'}
      className={`komsco-ai__mode-toggle-button${
        executionMode === 'read-only' ? ' komsco-ai__mode-toggle-button--active' : ''
      }`}
      onClick={() => onExecutionModeChange('read-only')}
      title="조회와 근거 수집만 수행하고 조치 계획, 승인, 실행은 만들지 않습니다."
      type="button"
    >
      <CoolShieldCheckIcon />
      <span>읽기 전용</span>
    </button>
    <button
      aria-label="승인 후 실행 모드"
      aria-pressed={executionMode === 'execute'}
      className={`komsco-ai__mode-toggle-button${
        executionMode === 'execute' ? ' komsco-ai__mode-toggle-button--active-execute' : ''
      }`}
      data-disabled-reason={!actionExecutionAvailable ? actionExecutionDisabledReason : undefined}
      onClick={() => onExecutionModeChange('execute')}
      title={
        actionExecutionAvailable
          ? '승인 후 실행 모드'
          : `승인 후 실행 비활성: ${actionExecutionDisabledReason}`
      }
      type="button"
    >
      <CoolTerminalIcon />
      <span>실행 가능</span>
    </button>
    <button
      aria-label="실험 무제한 모드"
      aria-pressed={executionMode === 'unrestricted'}
      className={`komsco-ai__mode-toggle-button${
        executionMode === 'unrestricted' ? ' komsco-ai__mode-toggle-button--active-danger' : ''
      }`}
      onClick={() => onExecutionModeChange('unrestricted')}
      title="실험 무제한 모드"
      type="button"
    >
      <CoolInfoIcon />
      <span>실행 무제한</span>
    </button>
  </div>
);

export default AssistantExecutionModeToggle;
