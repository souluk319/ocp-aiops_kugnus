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
  getClusterHost: (apiUrl?: string) => string;
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
}) => (
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
        <img alt="AIOps" className="komsco-ai__history-logo" src={productIcon} />
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
            const menuOpen = openHistoryMenuId === conversation.id;

            return (
              <div
                className={`komsco-ai__history-item-row${
                  conversation.id === activeSessionId ? ' komsco-ai__history-item-row--active' : ''
                }`}
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
                      aria-label="대화 옵션"
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
                {!isRenaming && actionRefs.length > 0 && (
                  <div
                    aria-label={`${conversation.title} 조치 목록`}
                    className="komsco-ai__history-action-refs"
                  >
                    {actionRefs.slice(0, 4).map((actionRef) => (
                      <button
                        className="komsco-ai__history-action-ref"
                        data-action-stage={actionRef.stage}
                        disabled={loading}
                        key={actionRef.id}
                        onClick={() => onActionRefSelect(conversation, actionRef)}
                        title={`${actionRef.label} · ${actionRef.toolName || '조치'} · ${
                          actionRef.targetKey
                        }`}
                        type="button"
                      >
                        <HistoryActionStageIcon stage={actionRef.stage} />
                        <span className="komsco-ai__history-action-ref-copy">
                          <span className="komsco-ai__history-action-ref-stage">
                            {compactActionLabel(actionRef.label)}
                          </span>
                          <strong>{actionRef.toolName || '조치'}</strong>
                          <small>{actionRef.targetKey}</small>
                        </span>
                      </button>
                    ))}
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
                        이름 변경
                      </button>
                      <button
                        className="komsco-ai__history-item-menu-item komsco-ai__history-item-menu-item--danger"
                        onClick={() => {
                          setOpenHistoryMenuId(null);
                          deleteConversation(conversation.id);
                        }}
                        role="menuitem"
                        type="button"
                      >
                        <CoolTrashIcon />
                        대화 삭제
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
    <div className="komsco-ai__history-user" aria-label="현재 OpenShift 사용자">
      <div className="komsco-ai__history-user-avatar">
        <CoolUserCircleIcon />
      </div>
      <div className="komsco-ai__history-user-main">
        <strong title={authSubject?.username || authSubjectError || '사용자 확인 중'}>
          {authSubject?.username || (authSubjectError ? '인증 확인 필요' : '확인 중')}
        </strong>
        <small title={clusterSummary?.apiUrl || ''}>{getClusterHost(clusterSummary?.apiUrl)}</small>
      </div>
    </div>
  </aside>
);

export default AssistantHistoryPanel;
