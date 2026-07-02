import type { AssistantTaskMode, UiLanguage } from './assistant.types';

export type AssistantCopy = {
  emptyHistory: string;
  emptyUploadedDocs: string;
  fileAttach: string;
  history: string;
  inputPlaceholder: string;
  newChat: string;
  openHistoryPanel: string;
  openUploadedDocs: string;
  openSidebar: string;
  sidebar: string;
  switchLanguage: string;
  userLabel: string;
  systemLabel: string;
  answerCopy: string;
  answerCopied: string;
  scrollToLatest: string;
  uploadedDocs: string;
  uploadedDocsError: string;
  uploadedDocsLoading: string;
};

export const TASK_MODE_EMPTY_COPY: Record<
  AssistantTaskMode,
  Record<UiLanguage, { title: string; text: string }>
> = {
  ask: {
    ko: {
      title: '무엇을 확인할까요?',
      text: '클러스터 상태, 최근 경고, 노드와 Pod 현황을 승인 실행으로 확인합니다.',
    },
    en: {
      title: 'What should I check?',
      text: 'Ask about cluster status, recent alerts, nodes, and pods in approval-gated execution mode.',
    },
  },
  troubleshooting: {
    ko: {
      title: '문제 원인을 점검합니다',
      text: 'Event, Pod, Operator, Metrics 근거를 모아 원인 후보와 다음 확인 절차를 정리합니다.',
    },
    en: {
      title: 'Troubleshoot an issue',
      text: 'I will collect evidence from events, pods, operators, and metrics, then organize likely causes and next checks.',
    },
  },
};

export const UI_COPY: Record<UiLanguage, AssistantCopy> = {
  ko: {
    emptyHistory: '아직 저장된 대화가 없습니다.',
    emptyUploadedDocs: '업로드된 문서가 없습니다. 파일 첨부 RAG 연결 후 이곳에 표시됩니다.',
    fileAttach: '파일 첨부',
    history: '지난 대화',
    inputPlaceholder: '현재 화면이나 클러스터 상태를 질문하세요',
    newChat: '새 채팅',
    openHistoryPanel: '대화 기록 패널',
    openUploadedDocs: '업로드 문서 패널',
    openSidebar: '대화 사이드바',
    sidebar: '대화 기록',
    switchLanguage: 'Switch to English',
    userLabel: '사용자',
    systemLabel: '시스템',
    answerCopy: '복사',
    answerCopied: '복사됨',
    scrollToLatest: '최신 답변으로 이동',
    uploadedDocs: '업로드 문서',
    uploadedDocsError: '업로드 문서 목록을 불러오지 못했습니다.',
    uploadedDocsLoading: '업로드 문서를 확인하는 중입니다.',
  },
  en: {
    emptyHistory: 'No saved conversations yet.',
    emptyUploadedDocs:
      'No uploaded documents yet. They will appear here after file-attachment RAG ingestion is connected.',
    fileAttach: 'Attach file',
    history: 'Recent chats',
    inputPlaceholder: 'Ask about the current screen or cluster state',
    newChat: 'New chat',
    openHistoryPanel: 'Conversation history panel',
    openUploadedDocs: 'Uploaded documents panel',
    openSidebar: 'Conversation sidebar',
    sidebar: 'Conversation history',
    switchLanguage: '한국어로 전환',
    userLabel: 'User',
    systemLabel: 'System',
    answerCopy: 'Copy',
    answerCopied: 'Copied',
    scrollToLatest: 'Jump to latest answer',
    uploadedDocs: 'Uploaded documents',
    uploadedDocsError: 'Unable to load uploaded documents.',
    uploadedDocsLoading: 'Checking uploaded documents.',
  },
};
