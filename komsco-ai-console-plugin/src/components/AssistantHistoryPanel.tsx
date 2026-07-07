import * as React from 'react';
import * as ReactDOM from 'react-dom';

import {
  CoolCheckIcon,
  CoolClockIcon,
  CoolComposeIcon,
  CoolDocumentIcon,
  CoolListChecklistIcon,
  CoolMoreIcon,
  CoolPencilIcon,
  CoolShieldCheckIcon,
  CoolTrashIcon,
  CoolUserCircleIcon,
} from './coolicons';
import type { AuthSubject, ClusterSummary, RagUploadedDocument } from '../services/aiGateway';
import type {
  ConversationActionRef,
  ConversationHistoryItem,
  HistoryPanelView,
  UiLanguage,
} from './assistant.types';
import type { AssistantCopy } from './assistant.copy';
import { getActionToolLabel } from './assistant.actionRecords';
import AssistantUploadedDocuments from './AssistantUploadedDocuments';

type HistoryMenuAnchor = {
  right: number;
  top: number;
};

type AssistantHistoryPanelProps = {
  activeSessionId: string;
  authSubject: AuthSubject | null;
  authSubjectError: string;
  clusterSummary: ClusterSummary | null;
  conversationHistory: ConversationHistoryItem[];
  copy: AssistantCopy;
  deleteConversation: (conversationHistoryId: string) => void;
  formatHistoryTime: (timestamp: number, language: UiLanguage) => string;
  getClusterHost: (apiUrl?: string, language?: UiLanguage) => string;
  historyMenuAnchor: HistoryMenuAnchor | null;
  historyMenuPanelRef: React.RefObject<HTMLDivElement>;
  historyMenuRef: React.RefObject<HTMLDivElement>;
  historyPanelView: HistoryPanelView;
  historySidebarStyle: React.CSSProperties;
  productIcon: string;
  loadConversation: (conversation: ConversationHistoryItem) => void;
  loading: boolean;
  onActionRefSelect: (
    conversation: ConversationHistoryItem,
    actionRef: ConversationActionRef,
  ) => void;
  openHistoryMenuId: string | null;
  renameConversation: (conversationHistoryId: string, title: string) => void;
  renamingHistoryId: string | null;
  renamingHistoryTitle: string;
  setHistoryMenuAnchor: React.Dispatch<React.SetStateAction<HistoryMenuAnchor | null>>;
  setHistoryPanelView: React.Dispatch<React.SetStateAction<HistoryPanelView>>;
  setOpenHistoryMenuId: React.Dispatch<React.SetStateAction<string | null>>;
  setRenamingHistoryId: React.Dispatch<React.SetStateAction<string | null>>;
  setRenamingHistoryTitle: React.Dispatch<React.SetStateAction<string>>;
  startNewConversation: () => void;
  uiLanguage: UiLanguage;
  uploadedDocuments: RagUploadedDocument[];
  uploadedDocumentsError: string;
  uploadedDocumentsLoading: boolean;
};

const getHistoryUserLabel = (
  authSubject: AuthSubject | null,
  authSubjectError: string,
  language: UiLanguage,
) => {
  const isKo = language === 'ko';
  if (authSubjectError) {
    return isKo ? '인증 확인 필요' : 'Auth check needed';
  }

  const username = authSubject?.username?.trim();
  if (!username) {
    return isKo ? '확인 중' : 'Checking';
  }

  const uid = authSubject?.uid || '';
  if (/fixture/i.test(uid) || /^local-admin$/i.test(username)) {
    return isKo ? '검증 사용자' : 'Validation user';
  }

  return username;
};

const HistoryActionStageIcon: React.FC<{ stage: ConversationActionRef['stage'] }> = ({ stage }) => {
  const Icon =
    stage === 'execution'
      ? CoolCheckIcon
      : stage === 'approval'
        ? CoolClockIcon
        : stage === 'plan'
          ? CoolShieldCheckIcon
          : CoolListChecklistIcon;

  return (
    <span className={`komsco-ai__history-action-ref-icon is-${stage}`} aria-hidden="true">
      <Icon />
    </span>
  );
};

const compactActionLabel = (label: string): string => label.replace(/^\d+단계\s*·\s*/, '');

const isInternalActionTargetLabel = (targetKey: string | undefined): boolean =>
  /^(proposal|plan|approval|execution)-local\b/i.test(String(targetKey || '')) ||
  /^(ActionProposalRecord|SealedActionPlanRecord|ApprovalDecisionRecord|ExecutionRecord)$/i.test(
    String(targetKey || ''),
  );

const historyActionDetailLabel = (
  actionRef: ConversationActionRef,
  language: UiLanguage,
): string => {
  const toolLabel = actionRef.toolName
    ? getActionToolLabel(actionRef.toolName, language)
    : language === 'en'
      ? 'Action'
      : '조치';

  return actionRef.targetKey && !isInternalActionTargetLabel(actionRef.targetKey)
    ? `${toolLabel} · ${actionRef.targetKey}`
    : toolLabel;
};

const actionStageLabel = (stage: ConversationActionRef['stage'], language: UiLanguage): string => {
  if (stage === 'plan') {
    return 'Action Plan';
  }
  if (stage === 'approval') {
    return language === 'en' ? 'Approval' : '승인';
  }
  if (stage === 'execution') {
    return language === 'en' ? 'Execution' : '실행';
  }
  return language === 'en' ? 'Candidate' : '조치 후보';
};

const AssistantHistoryPanel: React.FC<AssistantHistoryPanelProps> = ({
  activeSessionId,
  authSubject,
  authSubjectError,
  clusterSummary,
  conversationHistory,
  copy,
  deleteConversation,
  formatHistoryTime,
  getClusterHost,
  historyMenuAnchor,
  historyMenuPanelRef,
  historyMenuRef,
  historyPanelView,
  historySidebarStyle,
  productIcon,
  loadConversation,
  loading,
  onActionRefSelect,
  openHistoryMenuId,
  renameConversation,
  renamingHistoryId,
  renamingHistoryTitle,
  setHistoryMenuAnchor,
  setHistoryPanelView,
  setOpenHistoryMenuId,
  setRenamingHistoryId,
  setRenamingHistoryTitle,
  startNewConversation,
  uiLanguage,
  uploadedDocuments,
  uploadedDocumentsError,
  uploadedDocumentsLoading,
}) => {
  const [openActionHistoryId, setOpenActionHistoryId] = React.useState<string | null>(null);
  const historyUserLabel = getHistoryUserLabel(authSubject, authSubjectError, uiLanguage);

  return (
  <aside
    className="komsco-ai__history-sidebar"
    aria-label={historyPanelView === 'uploads' ? copy.uploadedDocs : copy.sidebar}
    style={historySidebarStyle}
  >
    <div
      className="komsco-ai__history-actions"
      aria-label={historyPanelView === 'uploads' ? copy.uploadedDocs : copy.sidebar}
    >
      <div className="komsco-ai__history-brand">
        <img alt="AIOps for OCP" className="komsco-ai__history-logo" src={productIcon} />
      </div>
      <div className="komsco-ai__history-actions-right">
        <button
          aria-label={copy.newChat}
          className="komsco-ai__history-action-button komsco-ai__history-action-button--primary"
          onClick={() => {
            startNewConversation();
            setHistoryPanelView('chats');
          }}
          title={copy.newChat}
          type="button"
        >
          <CoolComposeIcon />
        </button>
        <div className="komsco-ai__history-action-group" role="group" aria-label={copy.sidebar}>
          <button
            aria-label={copy.openHistoryPanel}
            aria-pressed={historyPanelView === 'chats'}
            className={`komsco-ai__history-action-button${
              historyPanelView === 'chats' ? ' komsco-ai__history-action-button--active' : ''
            }`}
            onClick={() => setHistoryPanelView('chats')}
            title={copy.openHistoryPanel}
            type="button"
          >
            <CoolClockIcon />
          </button>
          <button
            aria-label={copy.openUploadedDocs}
            aria-pressed={historyPanelView === 'uploads'}
            className={`komsco-ai__history-action-button${
              historyPanelView === 'uploads' ? ' komsco-ai__history-action-button--active' : ''
            }`}
            onClick={() => setHistoryPanelView('uploads')}
            title={copy.openUploadedDocs}
            type="button"
          >
            <CoolDocumentIcon />
          </button>
        </div>
      </div>
    </div>
    <div className="komsco-ai__history-title">
      {historyPanelView === 'uploads' ? <CoolDocumentIcon /> : <CoolClockIcon />}
      <span>{historyPanelView === 'uploads' ? copy.uploadedDocs : copy.history}</span>
    </div>
    {historyPanelView === 'uploads' ? (
      <div className="komsco-ai__history-list komsco-ai__history-list--uploads">
        {uploadedDocumentsLoading && uploadedDocuments.length === 0 ? (
          <div className="komsco-ai__history-empty">{copy.uploadedDocsLoading}</div>
        ) : uploadedDocumentsError && uploadedDocuments.length === 0 ? (
          <div className="komsco-ai__history-empty komsco-ai__history-empty--error">
            {uploadedDocumentsError}
          </div>
        ) : (
          <AssistantUploadedDocuments
            documents={uploadedDocuments}
            emptyText={copy.emptyUploadedDocs}
          />
        )}
      </div>
    ) : (
      <div className="komsco-ai__history-list" onScroll={() => setOpenHistoryMenuId(null)}>
        {conversationHistory.length === 0 ? (
          <div className="komsco-ai__history-empty">{copy.emptyHistory}</div>
        ) : (
          conversationHistory.map((conversation) => {
            const isRenaming = renamingHistoryId === conversation.id;
            const actionRefs = conversation.actionRefs ?? [];
            const actionHistoryOpen = openActionHistoryId === conversation.id;
            const menuOpen = openHistoryMenuId === conversation.id;

            return (
              <div
                className={`komsco-ai__history-item-row${
                  conversation.id === activeSessionId ? ' komsco-ai__history-item-row--active' : ''
                }${actionHistoryOpen ? ' komsco-ai__history-item-row--actions-open' : ''}`}
                key={conversation.id}
              >
                <div className="komsco-ai__history-item-main">
                  {isRenaming ? (
                    <input
                      autoFocus
                      className="komsco-ai__history-item-rename-input"
                      onBlur={() => {
                        renameConversation(conversation.id, renamingHistoryTitle);
                        setRenamingHistoryId(null);
                      }}
                      onChange={(event) => setRenamingHistoryTitle(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter') {
                          renameConversation(conversation.id, renamingHistoryTitle);
                          setRenamingHistoryId(null);
                        } else if (event.key === 'Escape') {
                          setRenamingHistoryId(null);
                        }
                      }}
                      value={renamingHistoryTitle}
                    />
                  ) : (
                    <button
                      className={`komsco-ai__history-item${
                        conversation.id === activeSessionId ? ' komsco-ai__history-item--active' : ''
                      }`}
                      disabled={loading}
                      onClick={() => loadConversation(conversation)}
                      title={conversation.title}
                      type="button"
                    >
                      <span>{conversation.title}</span>
                      <small>{formatHistoryTime(conversation.updatedAt, uiLanguage)}</small>
                    </button>
                  )}
                  <div
                    className="komsco-ai__history-item-menu"
                    ref={menuOpen ? historyMenuRef : undefined}
                  >
                    <button
                      aria-expanded={menuOpen}
                      aria-haspopup="menu"
                      aria-label={uiLanguage === 'en' ? 'Conversation options' : '대화 옵션'}
                      className="komsco-ai__history-item-menu-trigger"
                      onClick={(event) => {
                        const rect = event.currentTarget.getBoundingClientRect();
                        setHistoryMenuAnchor({
                          right: window.innerWidth - rect.right,
                          top: rect.bottom + 4,
                        });
                        setOpenHistoryMenuId((value) =>
                          value === conversation.id ? null : conversation.id,
                        );
                      }}
                      type="button"
                    >
                      <CoolMoreIcon />
                    </button>
                  </div>
                </div>
                {!isRenaming && actionHistoryOpen && (
                  <div
                    aria-label={
                      uiLanguage === 'en'
                        ? `${conversation.title} action history`
                        : `${conversation.title} 조치내역`
                    }
                    className={`komsco-ai__history-action-refs${
                      actionRefs.length === 0 ? ' komsco-ai__history-action-refs--empty' : ''
                    }`}
                  >
                    {actionRefs.length === 0 ? (
                      <div className="komsco-ai__history-action-empty">
                        {uiLanguage === 'en'
                          ? 'No saved action history.'
                          : '저장된 조치내역이 없습니다.'}
                      </div>
                    ) : (
                      actionRefs.map((actionRef) => (
                        <button
                          className="komsco-ai__history-action-ref"
                          data-action-stage={actionRef.stage}
                          disabled={loading}
                          key={actionRef.id}
                          onClick={() => onActionRefSelect(conversation, actionRef)}
                          title={`${actionStageLabel(actionRef.stage, uiLanguage)} · ${compactActionLabel(
                            actionRef.label,
                          )} · ${historyActionDetailLabel(actionRef, uiLanguage)}`}
                          type="button"
                        >
                          <HistoryActionStageIcon stage={actionRef.stage} />
                          <span className="komsco-ai__history-action-ref-copy">
                            <span className="komsco-ai__history-action-ref-stage">
                              {actionStageLabel(actionRef.stage, uiLanguage)}
                            </span>
                            <strong>{compactActionLabel(actionRef.label)}</strong>
                            <small>{historyActionDetailLabel(actionRef, uiLanguage)}</small>
                          </span>
                        </button>
                      ))
                    )}
                  </div>
                )}
                {menuOpen &&
                  historyMenuAnchor &&
                  typeof document !== 'undefined' &&
                  ReactDOM.createPortal(
                    <div
                      className="komsco-ai__history-item-menu-panel"
                      ref={historyMenuPanelRef}
                      role="menu"
                      style={{
                        right: historyMenuAnchor.right,
                        top: historyMenuAnchor.top,
                      }}
                    >
                      <button
                        className="komsco-ai__history-item-menu-item"
                        onClick={() => {
                          setOpenHistoryMenuId(null);
                          setRenamingHistoryId(conversation.id);
                          setRenamingHistoryTitle(conversation.title);
                        }}
                        role="menuitem"
                        type="button"
                      >
                        <CoolPencilIcon />
                        {uiLanguage === 'en' ? 'Rename' : '이름 변경'}
                      </button>
                      <button
                        className="komsco-ai__history-item-menu-item"
                        onClick={() => {
                          setOpenHistoryMenuId(null);
                          setOpenActionHistoryId((value) =>
                            value === conversation.id ? null : conversation.id,
                          );
                        }}
                        role="menuitem"
                        type="button"
                      >
                        <CoolListChecklistIcon />
                        {uiLanguage === 'en' ? 'Action history' : '조치내역'}
                      </button>
                      <button
                        className="komsco-ai__history-item-menu-item komsco-ai__history-item-menu-item--danger"
                        onClick={() => {
                          setOpenHistoryMenuId(null);
                          setOpenActionHistoryId((value) =>
                            value === conversation.id ? null : value,
                          );
                          deleteConversation(conversation.id);
                        }}
                        role="menuitem"
                        type="button"
                      >
                        <CoolTrashIcon />
                        {uiLanguage === 'en' ? 'Delete chat' : '대화 삭제'}
                      </button>
                    </div>,
                    document.body,
                  )}
              </div>
            );
          })
        )}
      </div>
    )}
    <div
      className="komsco-ai__history-user"
      aria-label={uiLanguage === 'en' ? 'Current OpenShift user' : '현재 OpenShift 사용자'}
    >
      <div className="komsco-ai__history-user-avatar">
        <CoolUserCircleIcon />
      </div>
      <div className="komsco-ai__history-user-main">
        <strong title={historyUserLabel}>{historyUserLabel}</strong>
        <small title={clusterSummary?.apiUrl || ''}>
          {getClusterHost(clusterSummary?.apiUrl, uiLanguage)}
        </small>
      </div>
    </div>
  </aside>
  );
};

export default AssistantHistoryPanel;
