import * as React from 'react';
import { Button, Card, CardBody, Spinner, TextArea } from '@patternfly/react-core';
import {
  ClipboardIcon,
  CompressArrowsAltIcon,
  ExclamationCircleIcon,
  ExclamationTriangleIcon,
  ExpandArrowsAltIcon,
  OpenshiftIcon,
  PaperclipIcon,
  PaperPlaneIcon,
  RobotIcon,
  ServerIcon,
  ShieldAltIcon,
  TerminalIcon,
  TimesIcon,
  UserCircleIcon,
} from '@patternfly/react-icons';
import {
  type ClusterSummary,
  type ImageAttachment,
  fetchClusterSummary,
  streamChat,
} from '../services/aiGateway';
import './assistant.css';

const QUICK_PROMPTS = [
  {
    icon: <ServerIcon />,
    label: 'Node 상태',
    prompt: '현재 클러스터 노드 상태를 요약하고 이상 징후가 있으면 알려줘.',
  },
  {
    icon: <ExclamationTriangleIcon />,
    label: '최근 경고',
    prompt: '최근 OpenShift 경고와 우선 확인할 항목을 실제 근거와 추가 확인 필요 항목으로 구분해서 정리해줘.',
  },
  {
    icon: <TerminalIcon />,
    label: '조치 절차',
    prompt: '현재 화면 기준으로 안전한 확인 절차를 단계별로 제안해줘.',
  },
];

type Message = {
  role: 'user' | 'assistant' | 'system';
  attachments?: ImageAttachment[];
  content: string;
  progressSteps?: ProgressStep[];
};

type ProgressStatus = 'running' | 'completed' | 'failed';

type ProgressStep = {
  id: string;
  name: string;
  title: string;
  status: ProgressStatus;
  startedAt: number;
  detail?: string;
  elapsedMs?: number;
  endedAt?: number;
  serverName?: string;
  summary?: string;
};

type ToolStreamEvent = {
  type: 'tool_call' | 'tool_result';
  name: string;
  id?: string;
  args?: unknown;
  detail?: string;
  result?: unknown;
  serverName?: string;
  status?: string;
  summary?: string;
};

type RunStatusEvent = {
  type: 'run_status';
  elapsedMs?: number;
  message: string;
  runId?: string;
  stage: string;
};

const URL_PATTERN = /(https?:\/\/[^\s]+)/g;
const MARKDOWN_LINK_PATTERN = /^\[(.+)\]\((https?:\/\/[^)]+)\)$/;
const INLINE_PATTERN = /(\[[^\n]+\]\(https?:\/\/[^)]+\)|\*\*[^*]+\*\*|`[^`]+`|https?:\/\/[^\s]+)/g;
const FAILED_TOOL_STATUSES = new Set(['error', 'failed', 'failure']);
const ACCEPTED_IMAGE_MIME_TYPES = new Set(['image/gif', 'image/jpeg', 'image/png', 'image/webp']);
const MAX_IMAGE_ATTACHMENTS = 4;
const MAX_IMAGE_ATTACHMENT_BYTES = 2 * 1024 * 1024;
const MAX_IMAGE_ATTACHMENT_TOTAL_BYTES = 6 * 1024 * 1024;
const CLUSTER_SUMMARY_REFRESH_MS = 10 * 1000;
const GATEWAY_PREP_TOOLS = new Set(['access_check', 'attachment_check']);
const GATEWAY_PREP_STEP_ID = 'gateway-request-prep';
const RUN_LOOP_STEP_ID = 'assistant-run-loop';
const RESPONSE_WAIT_STEP_ID = 'assistant-response-wait';
const ANSWER_STREAM_STEP_ID = 'assistant-answer-stream';
const TOOL_LABELS: Record<string, string> = {
  access_check: '접근 권한 확인',
  attachment_check: '이미지 첨부 확인',
  configuration_view: '클러스터 설정 조회',
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
  pods_get: 'Pod 상세 조회',
  pods_list: 'Pod 목록 조회',
  pods_list_in_namespace: 'Namespace Pod 조회',
  pods_log: 'Pod 로그 조회',
  pods_top: 'Pod 사용량 조회',
  projects_list: '프로젝트 조회',
  resources_get: '리소스 상세 조회',
  resources_list: '리소스 목록 조회',
  show_timeseries: '시계열 차트 준비',
};
const PREP_SUBTASKS = [
  {
    detail: 'Console UserToken과 요청 본문을 확인한 뒤 Lightspeed로 전달합니다.',
    label: '요청 확인',
    toolName: 'access_check',
  },
  {
    detail: '첨부 이미지 형식과 크기를 검증한 뒤 메타데이터만 Lightspeed 컨텍스트에 포함합니다.',
    label: '첨부 확인',
    toolName: 'attachment_check',
  },
];
const RESPONSE_WAIT_PHASES = [
  {
    activity: 'Gateway가 OLS streaming endpoint로 요청을 전달했습니다.',
    title: 'OLS 질의 전달',
  },
  {
    activity: 'OpenShift Lightspeed가 UserToken 기준으로 질의를 처리합니다.',
    title: 'Lightspeed 처리',
  },
  {
    activity: 'Lightspeed에서 필요한 도구 호출 또는 답변 생성을 기다립니다.',
    title: '응답 준비',
  },
  {
    activity: 'Lightspeed 응답 스트림을 브라우저로 중계할 준비를 합니다.',
    title: '답변 스트림 준비',
  },
];

const getMessageLabel = (role: Message['role']): string => {
  if (role === 'user') {
    return '사용자';
  }

  if (role === 'system') {
    return '시스템';
  }

  return 'AI Assistant';
};

const MessageIcon: React.FC<{ role: Message['role'] }> = ({ role }) => {
  if (role === 'user') {
    return <UserCircleIcon />;
  }

  if (role === 'system') {
    return <ExclamationCircleIcon />;
  }

  return <RobotIcon />;
};

const normalizeToolName = (name: string): string =>
  name
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, '_');

const formatToolTitle = (name: string): string => {
  const normalizedName = normalizeToolName(name);

  if (TOOL_LABELS[normalizedName]) {
    return TOOL_LABELS[normalizedName];
  }

  return normalizedName
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
};

const formatDuration = (milliseconds: number): string => {
  const safeMilliseconds = Math.max(0, milliseconds);

  if (safeMilliseconds < 1000) {
    return `${Math.max(0.1, safeMilliseconds / 1000).toFixed(1)}초`;
  }

  const totalSeconds = Math.round(safeMilliseconds / 1000);

  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;

  if (minutes > 0) {
    return `${minutes}분 ${seconds}초`;
  }

  return `${seconds}초`;
};

const formatFileSize = (size: number): string => {
  if (size < 1024) {
    return `${size} B`;
  }

  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }

  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
};

const createRunId = (): string =>
  `run-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;

const getAttachmentPreviewUrl = (attachment: ImageAttachment): string =>
  `data:${attachment.mimeType};base64,${attachment.data}`;

const readImageAttachment = (file: File): Promise<ImageAttachment> =>
  new Promise((resolve, reject) => {
    const reader = new FileReader();

    reader.onerror = () => reject(new Error(`${file.name} 파일을 읽을 수 없습니다.`));
    reader.onload = () => {
      const result = typeof reader.result === 'string' ? reader.result : '';
      const [, data = ''] = result.split(',');

      if (!data) {
        reject(new Error(`${file.name} 파일 데이터가 비어 있습니다.`));
        return;
      }

      resolve({
        data,
        id: `img-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
        mimeType: file.type,
        name: file.name,
        size: file.size,
      });
    };
    reader.readAsDataURL(file);
  });

const stringifyDetail = (value: unknown): string => {
  if (value === undefined || value === null) {
    return '';
  }

  if (typeof value === 'string') {
    return value;
  }

  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
};

const getToolDetail = (event: ToolStreamEvent): string => {
  if (event.detail) {
    return event.detail;
  }

  if (event.type === 'tool_call') {
    return stringifyDetail(event.args);
  }

  return stringifyDetail(event.result);
};

const getToolSummary = (event: ToolStreamEvent): string => {
  if (event.summary) {
    return event.summary;
  }

  if (event.type === 'tool_call') {
    return event.serverName ? `${event.serverName} 도구 호출` : '도구 호출';
  }

  return event.status ? `상태: ${event.status}` : '도구 실행 완료';
};

const findLastAssistantIndex = (messages: Message[]): number => {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index].role === 'assistant') {
      return index;
    }
  }

  return -1;
};

const getElapsedMs = (step: ProgressStep): number => {
  if (step.status === 'running') {
    return Date.now() - step.startedAt;
  }

  return step.elapsedMs ?? (step.endedAt ?? step.startedAt) - step.startedAt;
};

const isResponseWaitStep = (step: ProgressStep): boolean =>
  step.id.startsWith(RESPONSE_WAIT_STEP_ID);

const isAnswerStreamStep = (step: ProgressStep): boolean => step.id === ANSWER_STREAM_STEP_ID;

const getResponseWaitMessageIndex = (startedAt: number): number => {
  const elapsedSeconds = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));

  return Math.min(RESPONSE_WAIT_PHASES.length - 1, Math.floor(elapsedSeconds / 3));
};

const getResponseWaitMessage = (startedAt: number): string => {
  const phase = RESPONSE_WAIT_PHASES[getResponseWaitMessageIndex(startedAt)];

  return `${phase.title} 중`;
};

const cleanMarkdownLabel = (label: string): string =>
  label
    .replace(/\\([\[\]])/g, '$1')
    .replace(/\s+/g, ' ')
    .trim();

const parseMarkdownLink = (line: string): { href: string; label: string } | null => {
  const match = line.match(MARKDOWN_LINK_PATTERN);

  if (!match) {
    return null;
  }

  return {
    href: match[2].replace(/[),.;]+$/, ''),
    label: cleanMarkdownLabel(match[1]),
  };
};

const trimIndentedCodeLine = (line: string): string => line.replace(/^( {4}|\t)/, '');

const isCommandLikeLine = (line: string): boolean =>
  /^(#|oc\s+|kubectl\s+|helm\s+|etcdctl\s+|curl\s+|podman\s+|docker\s+|jq\s+|grep\s+|watch\s+|export\s+)/.test(
    line.trim(),
  );

const collectIndentedBlock = (lines: string[], startIndex: number): string[] => {
  const block: string[] = [];
  let index = startIndex;

  while (index < lines.length) {
    const candidate = lines[index];
    if (!/^( {4}|\t)/.test(candidate) || !candidate.trim()) {
      break;
    }

    block.push(trimIndentedCodeLine(candidate));
    index += 1;
  }

  return block;
};

const renderCodeBlock = (
  lines: string[],
  key: string,
  language?: string,
): React.ReactNode => {
  const code = lines.join('\n').trimEnd();

  return (
    <pre className="komsco-ai__formatted-code-block" data-language={language || undefined} key={key}>
      <code>{code}</code>
      <button
        aria-label="명령 복사"
        className="komsco-ai__code-copy"
        onClick={() => {
          if (navigator.clipboard) {
            void navigator.clipboard.writeText(code);
          }
        }}
        type="button"
      >
        <ClipboardIcon />
      </button>
    </pre>
  );
};

const getStepActivity = (step: ProgressStep): string => {
  if (step.status === 'failed') {
    return '오류 확인 필요';
  }

  if (step.id === GATEWAY_PREP_STEP_ID) {
    if (step.status === 'completed') {
      return '요청 준비 완료';
    }

    const completedCount = PREP_SUBTASKS.filter((item) =>
      step.detail?.includes(formatToolTitle(item.toolName)),
    ).length;
    const currentTask = PREP_SUBTASKS[Math.min(completedCount, PREP_SUBTASKS.length - 1)];

    return `${currentTask.label} 중`;
  }

  if (isResponseWaitStep(step) && step.status === 'running') {
    return getResponseWaitMessage(step.startedAt);
  }

  if (step.name === RUN_LOOP_STEP_ID) {
    return step.status === 'running' ? step.summary || '장기 실행 루프 유지 중' : '실행 루프 완료';
  }

  if (isAnswerStreamStep(step)) {
    return step.status === 'running' ? '본문을 실시간으로 수신하고 있습니다.' : '답변 생성 완료';
  }

  if (step.status === 'running') {
    return step.summary || '도구 응답을 기다리는 중입니다.';
  }

  return step.summary || '완료';
};

const renderInlineText = (text: string, keyPrefix: string): React.ReactNode[] =>
  text.split(INLINE_PATTERN).map((part, index) => {
    const markdownLink = parseMarkdownLink(part);
    if (markdownLink) {
      return (
        <a
          className="komsco-ai__formatted-link"
          href={markdownLink.href}
          key={`${keyPrefix}-md-link-${index}`}
          rel="noreferrer"
          target="_blank"
          title={markdownLink.href}
        >
          {markdownLink.label}
        </a>
      );
    }

    if (part.match(URL_PATTERN)) {
      const href = part.replace(/[),.;]+$/, '');
      const suffix = part.slice(href.length);

      return (
        <React.Fragment key={`${keyPrefix}-url-${index}`}>
          <a className="komsco-ai__formatted-link" href={href} rel="noreferrer" target="_blank">
            {href}
          </a>
          {suffix}
        </React.Fragment>
      );
    }

    if (part.startsWith('`') && part.endsWith('`')) {
      return (
        <code className="komsco-ai__formatted-code" key={`${keyPrefix}-code-${index}`}>
          {part.slice(1, -1)}
        </code>
      );
    }

    if (part.startsWith('**') && part.endsWith('**')) {
      return (
        <strong className="komsco-ai__formatted-strong" key={`${keyPrefix}-strong-${index}`}>
          {renderInlineText(part.slice(2, -2), `${keyPrefix}-strong-${index}`)}
        </strong>
      );
    }

    return <React.Fragment key={`${keyPrefix}-text-${index}`}>{part}</React.Fragment>;
  });

const renderAttachmentGrid = (
  attachments: ImageAttachment[] | undefined,
  keyPrefix: string,
  onPreview: React.Dispatch<React.SetStateAction<ImageAttachment | null>>,
): React.ReactNode => {
  if (!attachments || attachments.length === 0) {
    return null;
  }

  return (
    <div className="komsco-ai__attachment-grid" key={`${keyPrefix}-attachments`}>
      {attachments.map((attachment) => (
        <button
          aria-label={`${attachment.name} 크게 보기`}
          className="komsco-ai__attachment-card"
          key={attachment.id}
          onClick={() => onPreview(attachment)}
          title={`${attachment.name} 크게 보기`}
          type="button"
        >
          <img
            alt={attachment.name}
            className="komsco-ai__attachment-image"
            src={getAttachmentPreviewUrl(attachment)}
          />
          <div className="komsco-ai__attachment-meta">
            <span className="komsco-ai__attachment-name">{attachment.name}</span>
            <span className="komsco-ai__attachment-size">
              {attachment.mimeType} · {formatFileSize(attachment.size)}
            </span>
          </div>
        </button>
      ))}
    </div>
  );
};

const renderFormattedContent = (
  message: Message,
  onPreviewAttachment: React.Dispatch<React.SetStateAction<ImageAttachment | null>>,
): React.ReactNode => {
  if (message.role === 'user') {
    return (
      <div className="komsco-ai__message-text">
        {message.content && <div>{message.content}</div>}
        {renderAttachmentGrid(message.attachments, 'message', onPreviewAttachment)}
      </div>
    );
  }

  const lines = message.content.split('\n');
  const nodes: React.ReactNode[] = [];
  let bulletItems: string[] = [];
  let orderedItems: string[] = [];
  let codeBlockLanguage = '';
  let codeBlockLines: string[] = [];
  let inCodeBlock = false;
  let referenceItems: { href: string; label: string }[] = [];

  const flushBullets = () => {
    if (bulletItems.length === 0) {
      return;
    }

    const listIndex = nodes.length;
    nodes.push(
      <ul className="komsco-ai__formatted-list" key={`list-${listIndex}`}>
        {bulletItems.map((item, index) => (
          <li className="komsco-ai__formatted-list-item" key={`list-${listIndex}-${index}`}>
            {renderInlineText(item, `list-${listIndex}-${index}`)}
          </li>
        ))}
      </ul>,
    );
    bulletItems = [];
  };

  const flushOrdered = () => {
    if (orderedItems.length === 0) {
      return;
    }

    const listIndex = nodes.length;
    nodes.push(
      <ol
        className="komsco-ai__formatted-list komsco-ai__formatted-list--ordered"
        key={`ordered-${listIndex}`}
      >
        {orderedItems.map((item, index) => (
          <li className="komsco-ai__formatted-list-item" key={`ordered-${listIndex}-${index}`}>
            {renderInlineText(item, `ordered-${listIndex}-${index}`)}
          </li>
        ))}
      </ol>,
    );
    orderedItems = [];
  };

  const flushReferences = () => {
    if (referenceItems.length === 0) {
      return;
    }

    const referenceIndex = nodes.length;
    nodes.push(
      <div className="komsco-ai__reference-list" key={`references-${referenceIndex}`}>
        {referenceItems.map((item, index) => (
          <a
            className="komsco-ai__reference-link"
            href={item.href}
            key={`references-${referenceIndex}-${index}`}
            rel="noreferrer"
            target="_blank"
            title={item.href}
          >
            <span className="komsco-ai__reference-title">{item.label}</span>
          </a>
        ))}
      </div>,
    );
    referenceItems = [];
  };

  const flushCodeBlock = () => {
    if (!inCodeBlock && codeBlockLines.length === 0) {
      return;
    }

    const codeIndex = nodes.length;
    nodes.push(renderCodeBlock(codeBlockLines, `code-block-${codeIndex}`, codeBlockLanguage));
    codeBlockLanguage = '';
    codeBlockLines = [];
    inCodeBlock = false;
  };

  const flushLists = () => {
    flushBullets();
    flushOrdered();
  };

  const flushAll = () => {
    flushCodeBlock();
    flushLists();
    flushReferences();
  };

  const parseTableRow = (line: string): string[] =>
    line
      .replace(/^\|/, '')
      .replace(/\|$/, '')
      .split('|')
      .map((cell) => cell.trim());

  const isTableSeparator = (line: string): boolean =>
    /^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$/.test(line);

  for (let index = 0; index < lines.length; index += 1) {
    let rawLine = lines[index];
    let line = rawLine.trim();

    if (line.startsWith('```')) {
      if (inCodeBlock) {
        flushCodeBlock();
        continue;
      }

      flushAll();
      inCodeBlock = true;
      codeBlockLanguage = line.replace(/^```/, '').trim();
      continue;
    }

    if (inCodeBlock) {
      if (line === '`') {
        flushCodeBlock();
        continue;
      }

      codeBlockLines.push(rawLine);
      continue;
    }

    if (/^( {4}|\t)/.test(rawLine) && line) {
      const codeLines = collectIndentedBlock(lines, index);
      if (codeLines.some(isCommandLikeLine)) {
        flushAll();
        nodes.push(renderCodeBlock(codeLines, `indented-code-${index}`));
        index += codeLines.length - 1;
        continue;
      }

      rawLine = trimIndentedCodeLine(rawLine);
      line = rawLine.trim();
    }

    if (!line) {
      flushAll();
      continue;
    }

    if (line === '---') {
      flushAll();
      nodes.push(<div className="komsco-ai__formatted-divider" key={`divider-${index}`} />);
      continue;
    }

    const nextLine = lines[index + 1]?.trim() ?? '';
    if (line.includes('|') && isTableSeparator(nextLine)) {
      flushAll();
      const headers = parseTableRow(line);
      const rows: string[][] = [];
      let rowIndex = index + 2;

      while (rowIndex < lines.length) {
        const rowLine = lines[rowIndex].trim();
        if (!rowLine || !rowLine.includes('|')) {
          break;
        }

        rows.push(parseTableRow(rowLine));
        rowIndex += 1;
      }

      nodes.push(
        <div className="komsco-ai__table-wrap" key={`table-${index}`}>
          <table className="komsco-ai__table">
            <thead>
              <tr>
                {headers.map((header, headerIndex) => (
                  <th key={`table-${index}-head-${headerIndex}`}>
                    {renderInlineText(header, `table-${index}-head-${headerIndex}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, tableRowIndex) => (
                <tr key={`table-${index}-row-${tableRowIndex}`}>
                  {headers.map((_, cellIndex) => (
                    <td key={`table-${index}-row-${tableRowIndex}-${cellIndex}`}>
                      {renderInlineText(
                        row[cellIndex] ?? '',
                        `table-${index}-${tableRowIndex}-${cellIndex}`,
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      index = rowIndex - 1;
      continue;
    }

    const bullet = line.match(/^[-*]\s+(.+)$/);
    if (bullet) {
      flushOrdered();
      flushReferences();
      bulletItems.push(bullet[1]);
      continue;
    }

    const ordered = line.match(/^\d+\.\s+(.+)$/);
    if (ordered) {
      flushBullets();
      flushReferences();
      orderedItems.push(ordered[1]);
      continue;
    }

    const markdownReference = parseMarkdownLink(line);
    if (markdownReference) {
      flushLists();
      referenceItems.push(markdownReference);
      continue;
    }

    const reference = line.match(/^(.{2,120}?):\s+(https?:\/\/\S+)$/);
    if (reference) {
      flushLists();
      referenceItems.push({
        href: reference[2].replace(/[),.;]+$/, ''),
        label: cleanMarkdownLabel(reference[1]),
      });
      continue;
    }

    flushAll();

    if (line.startsWith('#')) {
      nodes.push(
        <div className="komsco-ai__formatted-heading" key={`heading-${index}`}>
          {renderInlineText(line.replace(/^#+\s*/, ''), `heading-${index}`)}
        </div>,
      );
      continue;
    }

    nodes.push(
      <div className="komsco-ai__formatted-line" key={`line-${index}`}>
        {renderInlineText(line, `line-${index}`)}
      </div>,
    );
  }

  flushAll();

  flushCodeBlock();

  return <div className="komsco-ai__formatted">{nodes}</div>;
};

const getProgressSummary = (steps: ProgressStep[], active: boolean): string => {
  const firstStartedAt = steps[0]?.startedAt ?? Date.now();
  const lastEndedAt = steps.reduce(
    (latest, step) => Math.max(latest, step.endedAt ?? step.startedAt),
    firstStartedAt,
  );
  const elapsedMs = (active ? Date.now() : lastEndedAt) - firstStartedAt;
  const runningStep = steps.find((step) => step.status === 'running');

  if (active && runningStep) {
    return `${formatDuration(elapsedMs)} 동안 작업 중 · ${runningStep.title} · ${getStepActivity(
      runningStep,
    )}`;
  }

  return `${formatDuration(elapsedMs)} 동안 작업 완료`;
};

const getStepElapsed = (step: ProgressStep): string => {
  if (step.status === 'running') {
    return formatDuration(getElapsedMs(step));
  }

  return formatDuration(getElapsedMs(step));
};

const expandProgressStep = (step: ProgressStep): ProgressStep[] => {
  return [step];
};

const getDisplaySteps = (steps: ProgressStep[]): ProgressStep[] =>
  steps
    .flatMap(expandProgressStep)
    .filter((step) => step.name !== RUN_LOOP_STEP_ID)
    .filter((step) => !(isAnswerStreamStep(step) && step.status === 'completed' && getElapsedMs(step) < 300));

const ProgressTimeline: React.FC<{ active: boolean; steps: ProgressStep[] }> = ({
  active,
  steps,
}) => {
  const displaySteps = getDisplaySteps(steps);

  if (displaySteps.length === 0) {
    return null;
  }

  return (
    <details className="komsco-ai__progress" key={active ? 'active' : 'complete'} open={active}>
      <summary className="komsco-ai__progress-summary">
        <span className="komsco-ai__progress-toggle" aria-hidden="true" />
        <span className="komsco-ai__progress-title">
          {getProgressSummary(displaySteps, active)}
        </span>
      </summary>
      <div className="komsco-ai__progress-list">
        {displaySteps.map((step) => {
          return (
            <div
              className={`komsco-ai__progress-step komsco-ai__progress-step--${step.status}`}
              key={step.id}
            >
              <span
                className={`komsco-ai__progress-status komsco-ai__progress-status--${step.status}`}
                aria-hidden="true"
              />
              <span className="komsco-ai__progress-step-copy">
                <span className="komsco-ai__progress-step-title">{step.title}</span>
                <span className="komsco-ai__progress-step-separator" aria-hidden="true">
                  ·
                </span>
                <span className="komsco-ai__progress-step-activity">{getStepActivity(step)}</span>
              </span>
              <span className="komsco-ai__progress-step-meta">{getStepElapsed(step)}</span>
            </div>
          );
        })}
      </div>
    </details>
  );
};

const formatSummaryTime = (updatedAt?: string): string => {
  if (!updatedAt) {
    return '수집 대기';
  }

  const date = new Date(updatedAt);
  if (Number.isNaN(date.getTime())) {
    return '수집됨';
  }

  return date.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
};

const getNodePressureLabel = (node: ClusterSummary['nodes']['items'][number]): string => {
  const pressures = [];
  if (node.pressures.disk) {
    pressures.push('Disk');
  }
  if (node.pressures.memory) {
    pressures.push('Memory');
  }
  if (node.pressures.pid) {
    pressures.push('PID');
  }

  return pressures.length > 0 ? `${pressures.join('/')} Pressure` : 'Pressure 없음';
};

const formatCpuUsage = (value?: string): string | null => {
  if (!value) {
    return null;
  }

  const trimmed = value.trim();
  const match = trimmed.match(/^(\d+(?:\.\d+)?)([a-zA-Z]*)$/);
  if (!match) {
    return trimmed;
  }

  const amount = Number(match[1]);
  if (!Number.isFinite(amount)) {
    return trimmed;
  }

  const unit = match[2];
  const cores =
    unit === 'n'
      ? amount / 1_000_000_000
      : unit === 'u'
        ? amount / 1_000_000
        : unit === 'm'
          ? amount / 1_000
          : amount;

  if (cores >= 1) {
    return `${cores.toFixed(cores >= 10 ? 0 : 1)} cores`;
  }

  return `${Math.max(1, Math.round(cores * 1000))} m`;
};

const formatMemoryUsage = (value?: string): string | null => {
  if (!value) {
    return null;
  }

  const trimmed = value.trim();
  const match = trimmed.match(/^(\d+(?:\.\d+)?)([a-zA-Z]*)$/);
  if (!match) {
    return trimmed;
  }

  const amount = Number(match[1]);
  if (!Number.isFinite(amount)) {
    return trimmed;
  }

  const unitMultipliers: Record<string, number> = {
    Ki: 1024,
    Mi: 1024 ** 2,
    Gi: 1024 ** 3,
    Ti: 1024 ** 4,
    K: 1000,
    M: 1000 ** 2,
    G: 1000 ** 3,
    T: 1000 ** 4,
    '': 1,
  };
  const multiplier = unitMultipliers[match[2]];
  if (!multiplier) {
    return trimmed;
  }

  const bytes = amount * multiplier;
  const gib = bytes / 1024 ** 3;
  if (gib >= 1) {
    return `${gib.toFixed(gib >= 10 ? 1 : 2)} GiB`;
  }

  const mib = bytes / 1024 ** 2;
  if (mib >= 1) {
    return `${mib.toFixed(mib >= 10 ? 0 : 1)} MiB`;
  }

  return `${Math.round(bytes / 1024)} KiB`;
};

const formatNodeUsage = (node: ClusterSummary['nodes']['items'][number]): string => {
  const cpu = formatCpuUsage(node.usage.cpu);
  const memory = formatMemoryUsage(node.usage.memory);
  if (!cpu && !memory) {
    return getNodePressureLabel(node);
  }

  return `CPU ${cpu ?? '-'} · 메모리 ${memory ?? '-'}`;
};

const getOperatorIssueLabel = (summary: ClusterSummary): string => {
  const issueCount = summary.operators.issues.length;
  if (issueCount === 0) {
    return 'Operator 정상';
  }

  return `Operator 이슈 ${issueCount}`;
};

const getClusterFaultCount = (summary: ClusterSummary): number =>
  summary.operators.degraded + summary.operators.unavailable;

const getContextHealthClass = (summary: ClusterSummary | null): string => {
  if (!summary) {
    return 'komsco-ai__context-pill--alert';
  }

  if (getClusterFaultCount(summary) > 0 || summary.nodes.notReady > 0) {
    return 'komsco-ai__context-pill--danger';
  }

  if (summary.operators.progressing > 0) {
    return 'komsco-ai__context-pill--alert';
  }

  return 'komsco-ai__context-pill--ok';
};

const getHealthTone = (summary: ClusterSummary | null): 'ok' | 'warn' | 'danger' | 'neutral' => {
  if (!summary) {
    return 'neutral';
  }

  if (summary.healthScore < 70 || getClusterFaultCount(summary) > 0 || summary.nodes.notReady > 0) {
    return 'danger';
  }

  if (summary.healthScore < 90 || summary.operators.progressing > 0) {
    return 'warn';
  }

  return 'ok';
};

const getOperatorTone = (
  operator: ClusterSummary['operators']['issues'][number],
): 'warn' | 'danger' => {
  if (!operator.available || operator.degraded) {
    return 'danger';
  }

  return 'warn';
};

const renderStatusTag = (
  label: string,
  tone: 'ok' | 'warn' | 'danger' | 'review' | 'neutral' = 'neutral',
  title?: string,
) => (
  <span className={`komsco-ai__scope-tag komsco-ai__scope-tag--${tone}`} title={title}>
    {label}
  </span>
);

const renderContextStrip = (summary: ClusterSummary | null, loading: boolean) => (
  <div className="komsco-ai__context-strip">
    <span className="komsco-ai__context-pill">
      <ServerIcon />
      {summary ? `Node ${summary.nodes.ready}/${summary.nodes.total}` : loading ? '상태 수집 중' : '현재 콘솔'}
    </span>
    <span className={`komsco-ai__context-pill ${getContextHealthClass(summary)}`}>
      <ExclamationTriangleIcon />
      {summary ? getOperatorIssueLabel(summary) : '클러스터 상태'}
    </span>
    <span className="komsco-ai__context-pill komsco-ai__context-pill--safe">
      <ShieldAltIcon />
      읽기 전용
    </span>
  </div>
);

const renderInsightRail = (
  summary: ClusterSummary | null,
  loading: boolean,
  error: string,
) => (
  <aside className="komsco-ai__insight-rail" aria-label="현재 분석 컨텍스트">
    <h2 className="komsco-ai__rail-title">현재 클러스터 컨텍스트</h2>
    <div className={`komsco-ai__health-card komsco-ai__health-card--${getHealthTone(summary)}`}>
      <div className="komsco-ai__health-head">
        <span>Cluster health score</span>
        <span>마지막 갱신 {formatSummaryTime(summary?.updatedAt)}</span>
      </div>
      <div className="komsco-ai__health-score">
        {summary ? summary.healthScore : loading ? '...' : '--'} <small>/ 100</small>
      </div>
      <div className="komsco-ai__health-bar">
        <span
          className={`komsco-ai__health-bar-fill komsco-ai__health-bar-fill--${getHealthTone(
            summary,
          )}`}
          style={{ width: `${summary?.healthScore ?? 0}%` }}
        />
      </div>
    </div>

    {error && (
      <div className="komsco-ai__rail-error">
        클러스터 요약을 가져오지 못했습니다. 대화 기능은 계속 사용할 수 있습니다.
      </div>
    )}

    <div className="komsco-ai__rail-section">
      <div className="komsco-ai__rail-section-head">
        <strong>노드 상태</strong>
        <span>
          {summary
            ? `${summary.nodes.ready}/${summary.nodes.total} Ready`
            : loading
              ? '수집 중'
              : '대기'}
        </span>
      </div>
      {(summary?.nodes.items ?? []).slice(0, 5).map((node) => (
        <div className="komsco-ai__alert-mini" key={node.name}>
          <span
            className={`komsco-ai__alert-mini-dot${
              node.ready && !Object.values(node.pressures).some(Boolean)
                ? ' komsco-ai__alert-mini-dot--green'
                : ''
            }`}
          />
          <div>
            <div className="komsco-ai__alert-mini-title">{node.name}</div>
            <div className="komsco-ai__alert-mini-sub">
              {node.roles.join(', ')} · {node.kubeletVersion ?? 'version unknown'}
            </div>
            <div className="komsco-ai__alert-mini-sub">{formatNodeUsage(node)}</div>
          </div>
          <span
            className={`komsco-ai__rail-badge${
              node.ready ? ' komsco-ai__rail-badge--ok' : ''
            }`}
          >
            {node.ready ? 'READY' : 'CHECK'}
          </span>
        </div>
      ))}
      {summary && summary.nodes.items.length === 0 && (
        <div className="komsco-ai__rail-empty">조회 가능한 노드가 없습니다.</div>
      )}
    </div>

    <div className="komsco-ai__rail-section">
      <div className="komsco-ai__rail-section-head">
        <strong>클러스터 상태</strong>
        <span>{summary?.version.version ?? 'version unknown'}</span>
      </div>
      <div className="komsco-ai__scope-list">
        {summary
          ? renderStatusTag(
              `Available ${summary.operators.available}/${summary.operators.total}`,
              summary.operators.available === summary.operators.total ? 'ok' : 'warn',
            )
          : renderStatusTag('Available 대기')}
        {summary
          ? renderStatusTag(
              `장애 ${getClusterFaultCount(summary)}건`,
              getClusterFaultCount(summary) > 0 ? 'danger' : 'ok',
              'Degraded + Unavailable Operator 수',
            )
          : renderStatusTag('장애 대기')}
        {summary
          ? renderStatusTag(
              `Progressing ${summary.operators.progressing}건`,
              summary.operators.progressing > 0 ? 'warn' : 'neutral',
            )
          : renderStatusTag('Progressing 대기')}
        {renderStatusTag(summary?.version.channel ?? 'channel unknown', 'neutral')}
        {renderStatusTag(
          summary?.version.updateAvailable ? 'Update available' : 'No update signal',
          summary?.version.updateAvailable ? 'review' : 'neutral',
        )}
        {renderStatusTag(
          summary?.version.upgradeable === false ? 'Upgrade blocked' : 'Upgradeable',
          summary?.version.upgradeable === false ? 'warn' : 'ok',
          summary?.version.upgradeableMessage,
        )}
        {renderStatusTag(
          `Metrics ${summary?.nodes.metricsAvailable ? 'available' : 'unavailable'}`,
          summary?.nodes.metricsAvailable ? 'ok' : 'warn',
        )}
      </div>
    </div>

    <div className="komsco-ai__rail-section">
      <div className="komsco-ai__rail-section-head">
        <strong>Operator 이슈</strong>
        <span>{summary ? `${summary.operators.issues.length}건` : '대기'}</span>
      </div>
      {(summary?.operators.issues ?? []).slice(0, 5).map((operator) => (
        <div
          className={`komsco-ai__rail-command komsco-ai__rail-command--${getOperatorTone(
            operator,
          )}`}
          key={operator.name}
        >
          <code>{operator.name}</code>
          <p>{operator.reason || operator.message || '상태 확인 필요'}</p>
        </div>
      ))}
      {summary && summary.operators.issues.length === 0 && (
        <div className="komsco-ai__rail-empty">주요 Operator 이슈가 없습니다.</div>
      )}
    </div>
  </aside>
);

const AssistantLauncher: React.FC = () => {
  const [open, setOpen] = React.useState(false);
  const [fullScreen, setFullScreen] = React.useState(false);
  const [input, setInput] = React.useState('');
  const [pendingAttachments, setPendingAttachments] = React.useState<ImageAttachment[]>([]);
  const [attachmentError, setAttachmentError] = React.useState('');
  const [clusterSummary, setClusterSummary] = React.useState<ClusterSummary | null>(null);
  const [clusterSummaryError, setClusterSummaryError] = React.useState('');
  const [clusterSummaryLoading, setClusterSummaryLoading] = React.useState(false);
  const [dragActive, setDragActive] = React.useState(false);
  const [messages, setMessages] = React.useState<Message[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [copiedMessageIndex, setCopiedMessageIndex] = React.useState<number | null>(null);
  const [previewAttachment, setPreviewAttachment] = React.useState<ImageAttachment | null>(null);
  const [, setProgressTick] = React.useState(0);
  const bodyEndRef = React.useRef<HTMLDivElement | null>(null);
  const fileInputRef = React.useRef<HTMLInputElement | null>(null);

  React.useEffect(() => {
    bodyEndRef.current?.scrollIntoView({ block: 'end' });
  }, [loading, messages]);

  React.useEffect(() => {
    if (!loading) {
      return undefined;
    }

    const timer = window.setInterval(() => {
      setProgressTick((value) => value + 1);
    }, 1000);

    return () => window.clearInterval(timer);
  }, [loading]);

  React.useEffect(() => {
    if (!previewAttachment) {
      return undefined;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setPreviewAttachment(null);
      }
    };

    window.addEventListener('keydown', handleKeyDown);

    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [previewAttachment]);

  React.useEffect(() => {
    if (!open) {
      return undefined;
    }

    let disposed = false;

    const loadSummary = async () => {
      setClusterSummaryLoading(true);
      try {
        const summary = await fetchClusterSummary();
        if (disposed) {
          return;
        }

        setClusterSummary(summary);
        setClusterSummaryError('');
      } catch (error) {
        if (disposed) {
          return;
        }

        setClusterSummaryError(
          error instanceof Error ? error.message : 'Cluster summary request failed.',
        );
      } finally {
        if (!disposed) {
          setClusterSummaryLoading(false);
        }
      }
    };

    void loadSummary();
    const timer = window.setInterval(() => {
      void loadSummary();
    }, CLUSTER_SUMMARY_REFRESH_MS);

    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, [open]);

  const appendAssistantText = React.useCallback((content: string) => {
    setMessages((prev) => {
      const assistantIndex = findLastAssistantIndex(prev);
      if (assistantIndex < 0) {
        return [...prev, { role: 'assistant', content }];
      }

      const next = [...prev];
      next[assistantIndex] = {
        ...next[assistantIndex],
        content: next[assistantIndex].content + content,
      };

      return next;
    });
  }, []);

  const copyMessage = React.useCallback((message: Message, index: number) => {
    const text = message.content.trim();
    if (!text || !navigator.clipboard) {
      return;
    }

    void navigator.clipboard.writeText(text).then(() => {
      setCopiedMessageIndex(index);
      window.setTimeout(() => {
        setCopiedMessageIndex((current) => (current === index ? null : current));
      }, 1400);
    });
  }, []);

  const upsertProgressStep = React.useCallback((step: ProgressStep) => {
    setMessages((prev) => {
      const assistantIndex = findLastAssistantIndex(prev);
      if (assistantIndex < 0) {
        return prev;
      }

      const next = [...prev];
      const message = next[assistantIndex];
      const progressSteps = [...(message.progressSteps ?? [])];
      const existingIndex = progressSteps.findIndex((item) => item.id === step.id);

      if (existingIndex >= 0) {
        progressSteps[existingIndex] = {
          ...progressSteps[existingIndex],
          ...step,
          startedAt: progressSteps[existingIndex].startedAt,
        };
      } else {
        progressSteps.push(step);
      }

      next[assistantIndex] = {
        ...message,
        progressSteps,
      };

      return next;
    });
  }, []);

  const markRunningProgressFailed = React.useCallback((summary: string) => {
    setMessages((prev) => {
      const assistantIndex = findLastAssistantIndex(prev);
      if (assistantIndex < 0) {
        return prev;
      }

      const next = [...prev];
      const message = next[assistantIndex];

      next[assistantIndex] = {
        ...message,
        progressSteps: message.progressSteps?.map((step) => {
          if (step.status !== 'running') {
            return step;
          }

          const endedAt = Date.now();

          return {
            ...step,
            detail: step.detail || summary,
            elapsedMs: endedAt - step.startedAt,
            endedAt,
            status: 'failed',
            summary,
          };
        }),
      };

      return next;
    });
  }, []);

  const addImageFiles = React.useCallback(
    async (files: File[]) => {
      const imageFiles = files.filter((file) => ACCEPTED_IMAGE_MIME_TYPES.has(file.type));

      if (imageFiles.length === 0) {
        setAttachmentError('지원되는 이미지 형식은 PNG, JPEG, WebP, GIF입니다.');
        return;
      }

      const nextCount = pendingAttachments.length + imageFiles.length;
      if (nextCount > MAX_IMAGE_ATTACHMENTS) {
        setAttachmentError(`이미지는 최대 ${MAX_IMAGE_ATTACHMENTS}개까지 첨부할 수 있습니다.`);
        return;
      }

      const tooLarge = imageFiles.find((file) => file.size > MAX_IMAGE_ATTACHMENT_BYTES);
      if (tooLarge) {
        setAttachmentError(
          `${tooLarge.name} 파일이 너무 큽니다. 이미지당 최대 ${formatFileSize(
            MAX_IMAGE_ATTACHMENT_BYTES,
          )}까지 가능합니다.`,
        );
        return;
      }

      const currentTotal = pendingAttachments.reduce((total, item) => total + item.size, 0);
      const nextTotal = imageFiles.reduce((total, file) => total + file.size, currentTotal);
      if (nextTotal > MAX_IMAGE_ATTACHMENT_TOTAL_BYTES) {
        setAttachmentError(
          `첨부 이미지 합계는 최대 ${formatFileSize(MAX_IMAGE_ATTACHMENT_TOTAL_BYTES)}까지 가능합니다.`,
        );
        return;
      }

      try {
        const attachments = await Promise.all(imageFiles.map(readImageAttachment));
        setPendingAttachments((prev) => [...prev, ...attachments]);
        setAttachmentError('');
      } catch (error) {
        setAttachmentError(error instanceof Error ? error.message : '이미지 파일을 읽지 못했습니다.');
      }
    },
    [pendingAttachments],
  );

  const removeAttachment = React.useCallback((id: string) => {
    setPendingAttachments((prev) => prev.filter((item) => item.id !== id));
    setAttachmentError('');
  }, []);

  const handleFileInputChange = React.useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(event.currentTarget.files ?? []);

      void addImageFiles(files);
      event.currentTarget.value = '';
    },
    [addImageFiles],
  );

  const handlePaste = React.useCallback(
    (event: React.ClipboardEvent<HTMLTextAreaElement>) => {
      const files = Array.from(event.clipboardData.files ?? []);
      const hasImage = files.some((file) => ACCEPTED_IMAGE_MIME_TYPES.has(file.type));

      if (!hasImage) {
        return;
      }

      event.preventDefault();
      void addImageFiles(files);
    },
    [addImageFiles],
  );

  const handleDrop = React.useCallback(
    (event: React.DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      setDragActive(false);
      void addImageFiles(Array.from(event.dataTransfer.files ?? []));
    },
    [addImageFiles],
  );

  const send = React.useCallback(
    async (prompt?: string) => {
      const question = (prompt ?? input).trim();
      const attachments = [...pendingAttachments];

      if ((!question && attachments.length === 0) || loading) {
        return;
      }

      setInput('');
      setPendingAttachments([]);
      setAttachmentError('');
      setLoading(true);
      setMessages((prev) => [
        ...prev,
        { role: 'user', attachments, content: question },
        { role: 'assistant', content: '', progressSteps: [] },
      ]);

      try {
        const runId = createRunId();
        const pageContext = {
          href: window.location.href,
          pathname: window.location.pathname,
        };
        const activeStepIdsByName = new Map<string, string>();
        const activeStepStartedAt = new Map<string, number>();
        const gatewayPrepDetails: string[] = [];
        let gatewayPrepStartedAt: number | undefined;
        let responseWaitStartedAt: number | undefined;
        let responseWaitStepId: string | undefined;
        let responseWaitSequence = 0;
        let answerStreamStartedAt: number | undefined;
        let runLoopStartedAt: number | undefined;
        let stepSequence = 0;

        const upsertGatewayPrepStep = (status: ProgressStatus) => {
          const now = Date.now();
          const startedAt = gatewayPrepStartedAt ?? now;

          gatewayPrepStartedAt = startedAt;
          upsertProgressStep({
            detail:
              gatewayPrepDetails.join('\n') ||
              '사용자 권한과 요청 본문을 확인합니다.',
            elapsedMs: status === 'running' ? undefined : now - startedAt,
            endedAt: status === 'running' ? undefined : now,
            id: GATEWAY_PREP_STEP_ID,
            name: GATEWAY_PREP_STEP_ID,
            startedAt,
            status,
            summary: '사용자 권한 및 요청 확인',
            title: '요청 준비',
          });
        };

        const startResponseWaitStep = () => {
          if (responseWaitStartedAt) {
            return;
          }

          const now = Date.now();
          const id = `${RESPONSE_WAIT_STEP_ID}-${responseWaitSequence}`;

          responseWaitSequence += 1;
          responseWaitStartedAt = now;
          responseWaitStepId = id;
          upsertProgressStep({
            detail:
              'OpenShift Lightspeed가 실제 응답 스트림을 시작하기를 기다리는 중입니다.',
            id,
            name: RESPONSE_WAIT_STEP_ID,
            startedAt: now,
            status: 'running',
            summary: '모델 응답 대기',
            title: 'AI 응답 대기',
          });
        };

        const finishResponseWaitStep = (summary: string) => {
          if (!responseWaitStartedAt || !responseWaitStepId) {
            return;
          }

          const now = Date.now();
          upsertProgressStep({
            detail: summary,
            elapsedMs: now - responseWaitStartedAt,
            endedAt: now,
            id: responseWaitStepId,
            name: RESPONSE_WAIT_STEP_ID,
            startedAt: responseWaitStartedAt,
            status: 'completed',
            summary,
            title: 'AI 응답 대기',
          });
          responseWaitStartedAt = undefined;
          responseWaitStepId = undefined;
        };

        const startAnswerStreamStep = () => {
          if (answerStreamStartedAt) {
            return;
          }

          const now = Date.now();
          answerStreamStartedAt = now;
          upsertProgressStep({
            detail: '응답 본문 스트림을 수신하고 화면에 렌더링합니다.',
            id: ANSWER_STREAM_STEP_ID,
            name: ANSWER_STREAM_STEP_ID,
            startedAt: now,
            status: 'running',
            summary: '본문 스트리밍',
            title: '답변 생성',
          });
        };

        const finishAnswerStreamStep = () => {
          if (!answerStreamStartedAt) {
            return;
          }

          const now = Date.now();
          upsertProgressStep({
            detail: '응답 본문 스트리밍이 완료되었습니다.',
            elapsedMs: now - answerStreamStartedAt,
            endedAt: now,
            id: ANSWER_STREAM_STEP_ID,
            name: ANSWER_STREAM_STEP_ID,
            startedAt: answerStreamStartedAt,
            status: 'completed',
            summary: '본문 스트리밍 완료',
            title: '답변 생성',
          });
          answerStreamStartedAt = undefined;
        };

        const handleGatewayPrepEvent = (event: ToolStreamEvent) => {
          upsertGatewayPrepStep('running');
          const normalizedName = normalizeToolName(event.name);

          if (event.type === 'tool_result') {
            gatewayPrepDetails.push(`${formatToolTitle(event.name)}: ${getToolSummary(event)}`);
          }

          if (
            event.type === 'tool_result' &&
            ((normalizedName === 'access_check' && attachments.length === 0) ||
              normalizedName === 'attachment_check')
          ) {
            upsertGatewayPrepStep('completed');
            startResponseWaitStep();
          }
        };

        const handleRunStatusEvent = (event: RunStatusEvent) => {
          const now = Date.now();
          const startedAt = runLoopStartedAt ?? now - (event.elapsedMs ?? 0);
          const failed = event.stage === 'failed';
          const completed = event.stage === 'completed';

          runLoopStartedAt = startedAt;

          upsertProgressStep({
            detail: event.message,
            elapsedMs: completed || failed ? now - startedAt : undefined,
            endedAt: completed || failed ? now : undefined,
            id: `${RUN_LOOP_STEP_ID}-${event.runId ?? runId}`,
            name: RUN_LOOP_STEP_ID,
            startedAt,
            status: failed ? 'failed' : completed ? 'completed' : 'running',
            summary: event.message,
            title: '실행 루프',
          });

          if (event.stage === 'lightspeed' || event.stage === 'waiting') {
            startResponseWaitStep();
          }
        };

        const startProgressStep = (event: ToolStreamEvent) => {
          const now = Date.now();
          const id = String(event.id ?? `${event.name}-${stepSequence}`);

          stepSequence += 1;
          activeStepIdsByName.set(event.name, id);
          activeStepStartedAt.set(id, now);
          upsertProgressStep({
            detail: getToolDetail(event),
            id,
            name: event.name,
            serverName: event.serverName,
            startedAt: now,
            status: 'running',
            summary: getToolSummary(event),
            title: formatToolTitle(event.name),
          });
        };

        const finishProgressStep = (event: ToolStreamEvent) => {
          const now = Date.now();
          const id = String(
            event.id ?? activeStepIdsByName.get(event.name) ?? `${event.name}-${stepSequence}`,
          );
          const startedAt = activeStepStartedAt.get(id) ?? now;
          const failed = FAILED_TOOL_STATUSES.has((event.status ?? '').toLowerCase());

          if (!event.id && !activeStepIdsByName.has(event.name)) {
            stepSequence += 1;
          }

          activeStepIdsByName.delete(event.name);
          activeStepStartedAt.delete(id);
          upsertProgressStep({
            detail: getToolDetail(event),
            elapsedMs: now - startedAt,
            endedAt: now,
            id,
            name: event.name,
            serverName: event.serverName,
            startedAt,
            status: failed ? 'failed' : 'completed',
            summary: getToolSummary(event),
            title: formatToolTitle(event.name),
          });
        };

        for await (const event of streamChat({ attachments, message: question, pageContext, runId })) {
          if (event.type === 'run_status') {
            handleRunStatusEvent(event);
          }

          if (event.type === 'text') {
            if (event.content.trim()) {
              finishResponseWaitStep('본문 스트리밍 시작');
              startAnswerStreamStep();
            }
            appendAssistantText(event.content);
          }

          if (event.type === 'tool_call') {
            if (GATEWAY_PREP_TOOLS.has(normalizeToolName(event.name))) {
              handleGatewayPrepEvent(event);
              continue;
            }

            finishResponseWaitStep(`${formatToolTitle(event.name)} 시작`);
            startProgressStep(event);
          }

          if (event.type === 'tool_result') {
            if (GATEWAY_PREP_TOOLS.has(normalizeToolName(event.name))) {
              handleGatewayPrepEvent(event);
              continue;
            }

            finishResponseWaitStep(`${formatToolTitle(event.name)} 완료`);
            finishProgressStep(event);
            startResponseWaitStep();
          }

          if (event.type === 'error') {
            finishResponseWaitStep('오류 응답 수신');
            markRunningProgressFailed(event.message || 'AI response failed.');
            setMessages((prev) => [
              ...prev,
              {
                role: 'system',
                content: event.message || 'AI response failed.',
              },
            ]);
          }
        }
        finishResponseWaitStep('스트림 종료');
        finishAnswerStreamStep();
      } catch (error) {
        markRunningProgressFailed(error instanceof Error ? error.message : 'AI response failed.');
        setMessages((prev) => [
          ...prev,
          {
            role: 'system',
            content: error instanceof Error ? error.message : 'AI response failed.',
          },
        ]);
      } finally {
        setLoading(false);
      }
    },
    [
      appendAssistantText,
      input,
      loading,
      markRunningProgressFailed,
      pendingAttachments,
      upsertProgressStep,
    ],
  );

  return (
    <div className="komsco-ai">
      {!open && (
        <Button
          aria-label="Open KOMSCO AI Assistant"
          className="komsco-ai__fab"
          onClick={() => setOpen(true)}
        >
          <span className="komsco-ai__fab-icon">
            <RobotIcon />
          </span>
          <span className="komsco-ai__fab-status" />
        </Button>
      )}

      {open && (
        <Card className={`komsco-ai__panel${fullScreen ? ' komsco-ai__panel--fullscreen' : ''}`}>
          <div className="komsco-ai__header">
            <div className="komsco-ai__brand">
              <div className="komsco-ai__brand-mark">
                <OpenshiftIcon />
              </div>
              <div className="komsco-ai__brand-copy">
                <div className="komsco-ai__kicker">OCP Operations Copilot</div>
                <strong className="komsco-ai__title">KOMSCO AI Assistant</strong>
                <div className="komsco-ai__subtitle">
                  <span className="komsco-ai__status-dot" />
                  prod-cluster · 실시간 컨텍스트 연결됨
                </div>
              </div>
            </div>
            <div className="komsco-ai__header-actions">
              <Button
                aria-label={fullScreen ? 'Exit full screen' : 'Open full screen'}
                className="komsco-ai__icon-button"
                onClick={() => setFullScreen((value) => !value)}
                variant="plain"
              >
                {fullScreen ? <CompressArrowsAltIcon /> : <ExpandArrowsAltIcon />}
              </Button>
              <Button
                aria-label="Close KOMSCO AI Assistant"
                className="komsco-ai__icon-button"
                onClick={() => setOpen(false)}
                variant="plain"
              >
                <TimesIcon />
              </Button>
            </div>
          </div>

          {renderContextStrip(clusterSummary, clusterSummaryLoading)}

          <div className="komsco-ai__workspace">
            <div className="komsco-ai__chat-column">
              <CardBody className="komsco-ai__body" aria-live="polite">
                <div className="komsco-ai__conversation-inner">
                  {messages.length === 0 && (
                    <div className="komsco-ai__empty">
                      <div className="komsco-ai__empty-mark">
                        <RobotIcon />
                      </div>
                      <div className="komsco-ai__empty-title">운영 확인 항목을 정리합니다</div>
                      <div className="komsco-ai__empty-text">
                        현재 콘솔 맥락과 OLS 조회 결과를 기준으로 안전한 점검 순서를 구성합니다.
                      </div>
                    </div>
                  )}

                  {messages.map((message, index) => {
                    const hasProgress = (message.progressSteps?.length ?? 0) > 0;
                    const hasContent = message.content.trim().length > 0;
                    const activeMessage = loading && index === messages.length - 1;

                    return (
                      <div
                        className={`komsco-ai__message komsco-ai__message--${message.role}`}
                        key={`${message.role}-${index}`}
                      >
                        <div className="komsco-ai__message-avatar">
                          <MessageIcon role={message.role} />
                        </div>
                        <div className="komsco-ai__message-stack">
                          <div className="komsco-ai__message-head">
                            <div className="komsco-ai__message-label">
                              {getMessageLabel(message.role)}
                            </div>
                            {message.role === 'assistant' && hasContent && (
                              <button
                                aria-label="답변 복사"
                                className="komsco-ai__message-copy"
                                onClick={() => copyMessage(message, index)}
                                title="답변 복사"
                                type="button"
                              >
                                <ClipboardIcon />
                                <span>{copiedMessageIndex === index ? '복사됨' : '복사'}</span>
                              </button>
                            )}
                          </div>
                          {hasProgress && message.progressSteps && (
                            <ProgressTimeline active={activeMessage} steps={message.progressSteps} />
                          )}
                          {(hasContent || !hasProgress) && (
                            <div className="komsco-ai__message-content">
                              {renderFormattedContent(message, setPreviewAttachment)}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}

                  {loading && (messages[messages.length - 1]?.progressSteps?.length ?? 0) === 0 && (
                    <div className="komsco-ai__loading">
                      <Spinner size="sm" />
                      <span>응답 생성 중</span>
                    </div>
                  )}
                  <div ref={bodyEndRef} />
                </div>
              </CardBody>

              <div
                className={`komsco-ai__composer-wrap${
                  dragActive ? ' komsco-ai__composer-wrap--drag-active' : ''
                }`}
                onDragEnter={(event) => {
                  event.preventDefault();
                  setDragActive(true);
                }}
                onDragLeave={(event) => {
                  if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
                    setDragActive(false);
                  }
                }}
                onDragOver={(event) => event.preventDefault()}
                onDrop={handleDrop}
              >
                <div className="komsco-ai__quick-prompts">
                  {QUICK_PROMPTS.map((item) => (
                    <Button
                      className="komsco-ai__quick-prompt"
                      isDisabled={loading}
                      key={item.label}
                      onClick={() => send(item.prompt)}
                      variant="secondary"
                    >
                      <span className="komsco-ai__quick-prompt-icon">{item.icon}</span>
                      <span className="komsco-ai__quick-prompt-label">{item.label}</span>
                    </Button>
                  ))}
                </div>

                <div className="komsco-ai__input">
                  <input
                    accept="image/png,image/jpeg,image/webp,image/gif"
                    aria-label="이미지 첨부"
                    className="komsco-ai__file-input"
                    disabled={loading}
                    multiple
                    onChange={handleFileInputChange}
                    ref={fileInputRef}
                    type="file"
                  />
                  <Button
                    aria-label="이미지 첨부"
                    className="komsco-ai__attach"
                    isDisabled={loading || pendingAttachments.length >= MAX_IMAGE_ATTACHMENTS}
                    onClick={() => fileInputRef.current?.click()}
                    variant="plain"
                  >
                    <PaperclipIcon />
                  </Button>
                  <div className="komsco-ai__composer">
                    {pendingAttachments.length > 0 && (
                      <div className="komsco-ai__pending-attachments">
                        {pendingAttachments.map((attachment) => (
                          <div className="komsco-ai__pending-attachment" key={attachment.id}>
                            <button
                              aria-label={`${attachment.name} 크게 보기`}
                              className="komsco-ai__pending-attachment-preview"
                              onClick={() => setPreviewAttachment(attachment)}
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
                                removeAttachment(attachment.id);
                              }}
                              variant="plain"
                            >
                              <TimesIcon />
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
                      className="komsco-ai__textarea"
                      onChange={(_, value) => setInput(value)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' && !event.shiftKey) {
                          event.preventDefault();
                          send();
                        }
                      }}
                      onPaste={handlePaste}
                      placeholder="현재 화면이나 클러스터 상태를 질문하세요"
                      rows={1}
                      value={input}
                    />
                  </div>
                  <Button
                    aria-label="Send question"
                    className="komsco-ai__send"
                    isDisabled={(!input.trim() && pendingAttachments.length === 0) || loading}
                    onClick={() => send()}
                  >
                    <PaperPlaneIcon />
                  </Button>
                </div>
                <div className="komsco-ai__composer-foot">
                  <span className="komsco-ai__read-only">명령 실행 전 사용자 확인</span>
                  <span>Enter 전송 · Shift+Enter 줄바꿈</span>
                </div>
              </div>
            </div>
            {renderInsightRail(clusterSummary, clusterSummaryLoading, clusterSummaryError)}
          </div>
        </Card>
      )}
      {previewAttachment && (
        <div
          aria-label={`${previewAttachment.name} 크게 보기`}
          aria-modal="true"
          className="komsco-ai__image-lightbox"
          onClick={() => setPreviewAttachment(null)}
          role="dialog"
        >
          <div
            className="komsco-ai__image-lightbox-panel"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="komsco-ai__image-lightbox-head">
              <div className="komsco-ai__image-lightbox-title">
                <strong>{previewAttachment.name}</strong>
                <span>
                  {previewAttachment.mimeType} · {formatFileSize(previewAttachment.size)}
                </span>
              </div>
              <Button
                aria-label="이미지 크게 보기 닫기"
                className="komsco-ai__image-lightbox-close"
                onClick={() => setPreviewAttachment(null)}
                variant="plain"
              >
                <TimesIcon />
              </Button>
            </div>
            <div className="komsco-ai__image-lightbox-body">
              <img
                alt={previewAttachment.name}
                className="komsco-ai__image-lightbox-image"
                src={getAttachmentPreviewUrl(previewAttachment)}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AssistantLauncher;
