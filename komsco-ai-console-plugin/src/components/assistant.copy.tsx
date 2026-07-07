import type { AssistantTaskMode, UiLanguage } from './assistant.types';

export type AssistantCopy = {
  autoProposeActionsToggle: string;
  closeCopilot: string;
  emptyHistory: string;
  emptyUploadedDocs: string;
  exitFullScreen: string;
  fileAttach: string;
  history: string;
  inputPlaceholder: string;
  lockWindowSize: string;
  newChat: string;
  openFullScreen: string;
  openHistoryPanel: string;
  openUploadedDocs: string;
  openSidebar: string;
  quickPromptMenu: string;
  resizeHandles: string;
  resizeHandlePrefix: string;
  sidebar: string;
  sendQuestion: string;
  stopResponse: string;
  switchLanguage: string;
  unlockWindowSize: string;
  userLabel: string;
  systemLabel: string;
  answerCopy: string;
  answerCopied: string;
  emptyHistorySearch: string;
  pinConversation: string;
  pinnedConversation: string;
  searchHistory: string;
  scrollToLatest: string;
  unpinConversation: string;
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
      text: 'Event, Pod, Operator, Metrics 확인 결과를 모아 원인 후보와 다음 확인 절차를 정리합니다.',
    },
    en: {
      title: 'Troubleshoot an issue',
      text: 'I will collect evidence from events, pods, operators, and metrics, then organize likely causes and next checks.',
    },
  },
};

export const UI_COPY: Record<UiLanguage, AssistantCopy> = {
  ko: {
    autoProposeActionsToggle: '답변 후 조치 계획 기본 제공',
    closeCopilot: 'AIOps for OCP 닫기',
    emptyHistory: '아직 저장된 대화가 없습니다.',
    emptyUploadedDocs: '업로드된 문서가 없습니다. 파일 첨부 RAG 연결 후 이곳에 표시됩니다.',
    exitFullScreen: '전체 화면 종료',
    fileAttach: '파일 첨부',
    history: '지난 대화',
    inputPlaceholder: '현재 화면이나 클러스터 상태를 질문하세요',
    lockWindowSize: '창 크기 잠금',
    newChat: '새 채팅',
    openFullScreen: '전체 화면 열기',
    openHistoryPanel: '대화 기록 패널',
    openUploadedDocs: '업로드 문서 패널',
    openSidebar: '대화 사이드바',
    quickPromptMenu: '자주 쓰는 점검 질문 열기',
    resizeHandles: '채팅창 크기 조절 핸들',
    resizeHandlePrefix: '채팅창',
    sidebar: '대화 기록',
    sendQuestion: '질문 전송',
    stopResponse: '응답 중지',
    switchLanguage: '영어로 전환',
    unlockWindowSize: '창 크기 잠금 해제',
    userLabel: '사용자',
    systemLabel: '시스템',
    answerCopy: '복사',
    answerCopied: '복사됨',
    emptyHistorySearch: '검색 결과가 없습니다.',
    pinConversation: '상단 고정',
    pinnedConversation: '상단 고정됨',
    searchHistory: '대화 검색',
    scrollToLatest: '최신 답변으로 이동',
    unpinConversation: '상단 고정 해제',
    uploadedDocs: '업로드 문서',
    uploadedDocsError: '업로드 문서 목록을 불러오지 못했습니다.',
    uploadedDocsLoading: '업로드 문서를 확인하는 중입니다.',
  },
  en: {
    autoProposeActionsToggle: 'Show action plans after answers',
    closeCopilot: 'Close AIOps for OCP',
    emptyHistory: 'No saved conversations yet.',
    emptyUploadedDocs:
      'No uploaded documents yet. They will appear here after file-attachment RAG ingestion is connected.',
    exitFullScreen: 'Exit full screen',
    fileAttach: 'Attach file',
    history: 'Recent chats',
    inputPlaceholder: 'Ask about the current screen or cluster state',
    lockWindowSize: 'Lock window size',
    newChat: 'New chat',
    openFullScreen: 'Open full screen',
    openHistoryPanel: 'Conversation history panel',
    openUploadedDocs: 'Uploaded documents panel',
    openSidebar: 'Conversation sidebar',
    quickPromptMenu: 'Open common check prompts',
    resizeHandles: 'Chat window resize handles',
    resizeHandlePrefix: 'Resize chat window',
    sidebar: 'Conversation history',
    sendQuestion: 'Send question',
    stopResponse: 'Stop response',
    switchLanguage: 'Switch to Korean',
    unlockWindowSize: 'Unlock window size',
    userLabel: 'User',
    systemLabel: 'System',
    answerCopy: 'Copy',
    answerCopied: 'Copied',
    emptyHistorySearch: 'No matching conversations.',
    pinConversation: 'Pin chat',
    pinnedConversation: 'Pinned',
    searchHistory: 'Search chats',
    scrollToLatest: 'Jump to latest answer',
    unpinConversation: 'Unpin chat',
    uploadedDocs: 'Uploaded documents',
    uploadedDocsError: 'Unable to load uploaded documents.',
    uploadedDocsLoading: 'Checking uploaded documents.',
  },
};
