import * as React from 'react';

import {
  CoolChatDotsIcon,
  CoolDesktopTowerIcon,
  CoolSettingsIcon,
  CoolShieldCheckIcon,
  CoolTerminalIcon,
  CoolWarningIcon,
} from './coolicons';
import type { AiopsExecutionMode, AssistantTaskMode } from './assistant.types';

export const QUICK_PROMPTS = [
  {
    icon: <CoolDesktopTowerIcon />,
    label: 'Node 상태',
    prompt: '현재 클러스터 노드 상태를 요약하고 이상 징후가 있으면 알려줘.',
  },
  {
    icon: <CoolWarningIcon />,
    label: '최근 경고',
    prompt:
      '최근 OpenShift 경고와 우선 확인할 항목을 실제 근거와 추가 확인 필요 항목으로 구분해서 정리해줘.',
  },
  {
    icon: <CoolTerminalIcon />,
    label: '화면 진단',
    prompt:
      '현재 화면의 대상 리소스에 대해 가능한 안전 조회를 실행하고, 확인한 증적과 원인 후보, 승인 가능한 조치 후보를 정리해줘.',
  },
  {
    icon: <CoolShieldCheckIcon />,
    label: '조치 후보 검토',
    prompt:
      '현재 화면의 대상에 대해 가능한 AIOps 조치 후보, 승인 필요 여부, 실행 전 검증 조건을 정리해줘.',
  },
];

export const ASSISTANT_TASK_MODES: Array<{
  description: string;
  icon: React.ReactNode;
  label: string;
  value: AssistantTaskMode;
}> = [
  {
    description: '일반 질문과 상태 확인',
    icon: <CoolChatDotsIcon />,
    label: 'Ask',
    value: 'ask',
  },
  {
    description: '원인 분석과 점검 절차',
    icon: <CoolSettingsIcon />,
    label: 'Troubleshooting',
    value: 'troubleshooting',
  },
];

export const TASK_MODE_PLACEHOLDERS: Record<AssistantTaskMode, string> = {
  ask: '무엇을 확인할까요?',
  troubleshooting: '어떤 문제를 점검할까요?',
};

export const URL_PATTERN = /(https?:\/\/[^\s]+)/g;
export const MARKDOWN_LINK_PATTERN = /^\[(.+)\]\((https?:\/\/[^)]+)\)$/;
export const INLINE_PATTERN = /(\[[^\n]+\]\(https?:\/\/[^)]+\)|\*\*[^*]+\*\*|`[^`]+`|https?:\/\/[^\s]+)/g;
export const FAILED_TOOL_STATUSES = new Set(['error', 'failed', 'failure']);
export const ACCEPTED_IMAGE_MIME_TYPES = new Set(['image/gif', 'image/jpeg', 'image/png', 'image/webp']);
export const ACCEPTED_RAG_DOCUMENT_MIME_TYPES = new Set([
  'application/pdf',
  'application/json',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/x-yaml',
  'text/log',
  'text/markdown',
  'text/plain',
  'text/x-markdown',
]);
export const ACCEPTED_RAG_DOCUMENT_EXTENSIONS = [
  '.docx',
  '.json',
  '.log',
  '.md',
  '.markdown',
  '.pdf',
  '.pptx',
  '.txt',
  '.xlsx',
  '.yaml',
  '.yml',
];
export const MULTIPART_RAG_DOCUMENT_EXTENSIONS = ['.docx', '.pdf', '.pptx', '.xlsx'];
export const MULTIPART_RAG_DOCUMENT_MIME_TYPES = new Set([
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
]);
export const FILE_INPUT_ACCEPT = [
  'image/png',
  'image/jpeg',
  'image/webp',
  'image/gif',
  'text/plain',
  'text/markdown',
  'application/json',
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  '.docx',
  '.json',
  '.log',
  '.md',
  '.markdown',
  '.pdf',
  '.pptx',
  '.txt',
  '.xlsx',
  '.yaml',
  '.yml',
].join(',');

export const MAX_IMAGE_ATTACHMENTS = 4;
export const MAX_IMAGE_ATTACHMENT_BYTES = 2 * 1024 * 1024;
export const MAX_IMAGE_ATTACHMENT_TOTAL_BYTES = 6 * 1024 * 1024;
export const MAX_RAG_DOCUMENT_UPLOAD_BYTES = 5 * 1024 * 1024;
export const MAX_RECENT_CONTEXT_MESSAGES = 8;
export const CLUSTER_SUMMARY_REFRESH_MS = 10 * 1000;
export const DEFAULT_AIOPS_EXECUTION_MODE: AiopsExecutionMode = 'read-only';
export const HISTORY_DRAWER_WIDTH = 268;
export const MIN_STOP_BUTTON_VISIBLE_MS = 2000;
export const SCROLL_BOTTOM_THRESHOLD_PX = 80;
export const GATEWAY_PREP_TOOLS = new Set(['access_check', 'attachment_check']);
export const GATEWAY_PREP_STEP_ID = 'gateway-request-prep';
export const RCA_PLAN_STEP_ID = 'assistant-rca-plan';
export const RCA_CONTEXT_STEP_ID = 'assistant-rca-context';
export const RUN_LOOP_STEP_ID = 'assistant-run-loop';
export const RESPONSE_WAIT_STEP_ID = 'assistant-response-wait';
export const ANSWER_STREAM_STEP_ID = 'assistant-answer-stream';
export const ASSISTANT_TYPEWRITER_CHARS = 18;
export const ASSISTANT_TYPEWRITER_INTERVAL_MS = 24;

export const TOOL_LABELS: Record<string, string> = {
  access_check: '접근 권한 확인',
  audit_record: '감사 기록',
  attachment_check: '이미지 첨부 확인',
  configuration_view: '클러스터 설정 조회',
  evidence_ref: '증거 참조 기록',
  events_list: '이벤트 조회',
  execute_instant_query: '현재 메트릭 조회',
  execute_range_query: '기간 메트릭 조회',
  get_alerts: 'OpenShift 경고 조회',
  get_label_names: '메트릭 라벨 조회',
  get_label_values: '메트릭 값 조회',
  get_series: '메트릭 시리즈 조회',
  get_silences: '알림 침묵 조회',
  get_resources: '리소스 목록 조회',
  helm_list: 'Helm 릴리스 조회',
  list_metrics: '메트릭 목록 조회',
  list_resources: '리소스 목록 조회',
  namespaces_list: '네임스페이스 조회',
  nodes_log: '노드 로그 조회',
  nodes_stats_summary: '노드 상세 사용량 조회',
  nodes_top: '노드 사용량 조회',
  natural_action_execute: '자연어 조치 실행',
  natural_action_followup: '후속 조치 실행',
  natural_action_plan: '자연어 조치 계획 생성',
  natural_action_unresolved: '조치 대상 확인',
  pod_count_deployment_lookup: 'Deployment 조회',
  pod_count_investigation: 'Pod 개수 결과',
  pod_count_pod_lookup: 'Pod 목록 조회',
  pod_count_scope_resolve: '조회 범위 결정',
  pod_count_selector_match: 'Pod 매칭 계산',
  pods_get: 'Pod 상세 조회',
  pods_list: 'Pod 목록 조회',
  pods_list_in_namespace: 'Namespace Pod 조회',
  pods_log: 'Pod 로그 조회',
  pods_top: 'Pod 사용량 조회',
  projects_list: '프로젝트 조회',
  resources_get: '리소스 상세 조회',
  resources_list: '리소스 목록 조회',
  policy_check: '정책 확인',
  product_access_review: '제품 접근 권한 확인',
  runtime_tool_plan: '증거 수집 계획',
  security_boundary: '보안 경계 확인',
  show_timeseries: '시계열 차트 준비',
  subject_review: '사용자 주체 확인',
  vision_analysis: '이미지 분석',
};

export const ACTION_POLICY_LABELS: Record<string, string> = {
  evict_one_unhealthy_controller_owned_pod: '비정상 Pod 축출(재생성 유도)',
  rollout_restart_deployment: '배포 롤아웃 재시작',
  rollback_deployment_to_revision: '이전 리비전으로 롤백',
  set_replicas_within_bounds: '레플리카 수 조정',
  set_hpa_bounds: '오토스케일러(HPA) 범위 조정',
};

export const RISK_LABEL_KO: Record<string, { label: string; tone: 'ok' | 'warn' | 'danger' }> = {
  low: { label: '낮음', tone: 'ok' },
  medium: { label: '보통', tone: 'warn' },
  high: { label: '높음', tone: 'danger' },
};

export const PREP_SUBTASKS = [
  {
    detail: '사용자 권한과 질문 내용을 확인한 뒤 답변 생성을 요청합니다.',
    label: '요청 확인',
    toolName: 'access_check',
  },
  {
    detail: '첨부 이미지 형식과 크기를 확인한 뒤 필요한 메타데이터만 답변 요청에 포함합니다.',
    label: '첨부 확인',
    toolName: 'attachment_check',
  },
];

export const RESPONSE_WAIT_PHASES = [
  {
    activity: 'Gateway가 AIOps에 답변 생성을 요청했습니다.',
    title: '답변 요청',
  },
  {
    activity: 'AIOps가 사용자 권한 범위 안에서 질문을 처리합니다.',
    title: '질문 처리',
  },
  {
    activity: '필요한 도구 조회와 답변 생성을 기다립니다.',
    title: '답변 준비',
  },
  {
    activity: '생성된 답변을 화면에 표시할 준비를 합니다.',
    title: '화면 표시 준비',
  },
];

export const STORED_CONVERSATION_HISTORY_KEY = 'komsco-ai.assistant.conversation-history.v1';
export const STORED_ACTIVE_CONVERSATION_KEY = 'komsco-ai.assistant.active-conversation.v1';
export const STORED_UI_LANGUAGE_KEY = 'komsco-ai.assistant.ui-language.v1';
export const MAX_STORED_CONVERSATIONS = 12;
