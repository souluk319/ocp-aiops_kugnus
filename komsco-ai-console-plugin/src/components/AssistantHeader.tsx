import * as React from 'react';
import { Button } from '@patternfly/react-core';
import { PanelLeft } from 'lucide-react';

import type { ClusterSummary } from '../services/aiGateway';
import type { AiopsExecutionMode, UiLanguage } from './assistant.types';
import type { AssistantCopy } from './assistant.copy';
import AssistantExecutionModeToggle from './AssistantExecutionModeToggle';
import { renderHeaderOpsStatus } from './assistant.insightRailHelpers';
import {
  CoolCloseIcon,
  CoolExpandIcon,
  CoolLockIcon,
  CoolLockOpenIcon,
  CoolShrinkIcon,
} from './coolicons';

type AssistantHeaderProps = {
  actionExecutionAvailable: boolean;
  actionExecutionDisabledReason: string;
  clusterSummary: ClusterSummary | null;
  clusterSummaryError: string;
  clusterSummaryLoading: boolean;
  copy: AssistantCopy;
  executionMode: AiopsExecutionMode;
  fullScreen: boolean;
  lockOpen: boolean;
  onClose: () => void;
  onExecutionModeChange: (mode: AiopsExecutionMode) => void;
  onMouseDown: (event: React.MouseEvent<HTMLDivElement>) => void;
  onToggleFullScreen: () => void;
  onToggleLanguage: () => void;
  onToggleResizeLock: () => void;
  onToggleSidebar: () => void;
  panelResizeUnlocked: boolean;
  uiLanguage: UiLanguage;
};

const AssistantHeader: React.FC<AssistantHeaderProps> = ({
  actionExecutionAvailable,
  actionExecutionDisabledReason,
  clusterSummary,
  clusterSummaryError,
  clusterSummaryLoading,
  copy,
  executionMode,
  fullScreen,
  lockOpen,
  onClose,
  onExecutionModeChange,
  onMouseDown,
  onToggleFullScreen,
  onToggleLanguage,
  onToggleResizeLock,
  onToggleSidebar,
  panelResizeUnlocked,
  uiLanguage,
}) => (
  <div className="komsco-ai__header" onMouseDown={onMouseDown}>
    <Button
      aria-label={copy.openSidebar}
      className="komsco-ai__icon-button komsco-ai__sidebar-toggle"
      onClick={onToggleSidebar}
      title={copy.openSidebar}
      variant="plain"
    >
      <PanelLeft aria-hidden="true" strokeWidth={1.8} />
    </Button>
    <div className="komsco-ai__brand">
      <span className="komsco-ai__title">AIOps for OCP</span>
    </div>
    <div
      className="komsco-ai__header-status"
      aria-label={uiLanguage === 'ko' ? '클러스터 운영 상태 및 실행 모드' : 'Cluster status and execution mode'}
    >
      {renderHeaderOpsStatus(clusterSummary, clusterSummaryLoading, clusterSummaryError, uiLanguage)}
      <div className="komsco-ai__header-sep" aria-hidden="true" />
      <AssistantExecutionModeToggle
        actionExecutionAvailable={actionExecutionAvailable}
        actionExecutionDisabledReason={actionExecutionDisabledReason}
        executionMode={executionMode}
        onExecutionModeChange={onExecutionModeChange}
        uiLanguage={uiLanguage}
      />
    </div>
    <div className="komsco-ai__header-actions">
      <Button
        aria-label={copy.switchLanguage}
        className="komsco-ai__icon-button komsco-ai__language-button"
        onClick={onToggleLanguage}
        title={copy.switchLanguage}
        variant="plain"
      >
        <span className="komsco-ai__language-code">{uiLanguage === 'ko' ? 'KR' : 'EN'}</span>
      </Button>
      <Button
        aria-label={fullScreen ? copy.exitFullScreen : copy.openFullScreen}
        className="komsco-ai__icon-button"
        onClick={onToggleFullScreen}
        title={fullScreen ? copy.exitFullScreen : copy.openFullScreen}
        variant="plain"
      >
        {fullScreen ? <CoolShrinkIcon /> : <CoolExpandIcon />}
      </Button>
      <Button
        aria-label={panelResizeUnlocked ? copy.lockWindowSize : copy.unlockWindowSize}
        className={`komsco-ai__icon-button${
          panelResizeUnlocked ? ' komsco-ai__icon-button--active' : ''
        }`}
        onClick={onToggleResizeLock}
        title={panelResizeUnlocked ? copy.lockWindowSize : copy.unlockWindowSize}
        variant="plain"
      >
        {panelResizeUnlocked ? <CoolLockOpenIcon /> : <CoolLockIcon />}
      </Button>
      {!lockOpen && (
        <Button
          aria-label={copy.closeCopilot}
          className="komsco-ai__icon-button"
          onClick={onClose}
          title={copy.closeCopilot}
          variant="plain"
        >
          <CoolCloseIcon />
        </Button>
      )}
    </div>
  </div>
);

export default AssistantHeader;
