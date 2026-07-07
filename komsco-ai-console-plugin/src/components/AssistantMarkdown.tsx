import * as React from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import rehypeSanitize from 'rehype-sanitize';
import remarkGfm from 'remark-gfm';

import { CoolCopyIcon, CoolWrapTextIcon } from './coolicons';
import {
  isCommandBlock,
  isPublicWebReferenceHref,
  prepareMarkdownContent,
} from './assistant.markdownPrepare';
import type { UiLanguage } from './assistant.types';
import { redactSensitiveText } from '../utils/evidenceDisplay';

type AssistantMarkdownProps = {
  content: string;
  streaming?: boolean;
  uiLanguage?: UiLanguage;
  variant?: 'default' | 'runbook';
};

type CodeBlockProps = {
  code: string;
  language?: string;
  risk?: CommandRisk;
  uiLanguage: UiLanguage;
};

type CommandRisk = 'read-only' | 'approval-required';

const MUTATION_RE =
  /\b(apply|create|delete|replace|patch|edit|scale|rollout|restart|adm|label|annotate|set|exec|rsh|cp|drain|cordon|uncordon|taint)\b/i;
const READ_ONLY_OC_RE =
  /\b(get|describe|logs|top|explain|auth\s+can-i|api-resources|api-versions|whoami|project|version)\b/i;

const CODE_BLOCK_LABELS: Record<
  UiLanguage,
  {
    copy: string;
    copyCommand: string;
    language: string;
    readOnly: string;
    approvalRequired: string;
    showUnwrapped: string;
    showWrapped: string;
  }
> = {
  en: {
    approvalRequired: 'approval required',
    copy: 'Copy code',
    copyCommand: 'Copy command',
    language: 'code',
    readOnly: 'read-only',
    showUnwrapped: 'Disable line wrap',
    showWrapped: 'Wrap lines',
  },
  ko: {
    approvalRequired: '승인 필요',
    copy: '코드 복사',
    copyCommand: '명령 복사',
    language: '코드',
    readOnly: '읽기 전용',
    showUnwrapped: '개행 해제',
    showWrapped: '개행 표시',
  },
};

const safeHref = (href: string | undefined): string | undefined => {
  if (!href) {
    return undefined;
  }
  if (isPublicWebReferenceHref(href)) {
    return undefined;
  }
  if (/^(https?:|mailto:)/i.test(href)) {
    return href;
  }
  return undefined;
};

const commandRisk = (code: string): CommandRisk => {
  const text = code.toLowerCase();
  if (MUTATION_RE.test(text)) {
    return 'approval-required';
  }
  if (READ_ONLY_OC_RE.test(text)) {
    return 'read-only';
  }
  if (/\bcurl\b/.test(text) && /\s-X\s+(POST|PUT|PATCH|DELETE)\b/i.test(code)) {
    return 'approval-required';
  }
  return 'read-only';
};

const CodeBlock: React.FC<CodeBlockProps> = ({ code, language, risk, uiLanguage }) => {
  const [wrapped, setWrapped] = React.useState(false);
  const labels = CODE_BLOCK_LABELS[uiLanguage];
  const command = risk !== undefined;
  const displayLanguage = language || (command ? 'bash' : labels.language);

  return (
    <pre
      className={`${command ? 'komsco-ai__command-card' : 'komsco-ai__formatted-code-block'}${
        wrapped ? ' komsco-ai__formatted-code-block--wrapped' : ''
      }`}
      data-aiops-command-card={command ? 'true' : undefined}
      data-command-risk={risk}
      data-language={displayLanguage}
    >
      <div className="komsco-ai__code-meta">
        <span className="komsco-ai__code-language">{displayLanguage}</span>
        {risk && (
          <span className={`komsco-ai__command-risk is-${risk}`}>
            {risk === 'approval-required' ? labels.approvalRequired : labels.readOnly}
          </span>
        )}
      </div>
      <code>{code}</code>
      <div className="komsco-ai__code-actions">
        <button
          aria-label={wrapped ? labels.showUnwrapped : labels.showWrapped}
          aria-pressed={wrapped}
          className={`komsco-ai__code-wrap-toggle${
            wrapped ? ' komsco-ai__code-wrap-toggle--active' : ''
          }`}
          onClick={() => setWrapped((value) => !value)}
          title={wrapped ? labels.showUnwrapped : labels.showWrapped}
          type="button"
        >
          <CoolWrapTextIcon />
        </button>
        <button
          aria-label={command ? labels.copyCommand : labels.copy}
          className="komsco-ai__code-copy"
          onClick={() => {
            if (navigator.clipboard) {
              void navigator.clipboard.writeText(redactSensitiveText(code));
            }
          }}
          title={command ? labels.copyCommand : labels.copy}
          type="button"
        >
          <CoolCopyIcon />
        </button>
      </div>
    </pre>
  );
};

const markdownComponents = (uiLanguage: UiLanguage): Components => ({
  a({ children, href }) {
    const safe = safeHref(href);
    if (!safe) {
      return <>{children}</>;
    }
    return (
      <a className="komsco-ai__formatted-link" href={safe} rel="noreferrer" target="_blank">
        {children}
      </a>
    );
  },
  blockquote({ children }) {
    return <blockquote className="komsco-ai__markdown-quote">{children}</blockquote>;
  },
  code({ children, className, inline }) {
    const code = String(children).replace(/\n$/, '');
    const language = /language-([A-Za-z0-9_-]+)/.exec(className || '')?.[1];
    if (inline) {
      return <code className="komsco-ai__formatted-code">{code}</code>;
    }
    if (isCommandBlock(code, language)) {
      return (
        <CodeBlock
          code={code}
          language={language || 'bash'}
          risk={commandRisk(code)}
          uiLanguage={uiLanguage}
        />
      );
    }
    return <CodeBlock code={code} language={language} uiLanguage={uiLanguage} />;
  },
  h1({ children }) {
    return <div className="komsco-ai__formatted-heading">{children}</div>;
  },
  h2({ children }) {
    return <div className="komsco-ai__formatted-heading">{children}</div>;
  },
  h3({ children }) {
    return <div className="komsco-ai__formatted-heading">{children}</div>;
  },
  h4({ children }) {
    return <div className="komsco-ai__formatted-heading">{children}</div>;
  },
  li({ children }) {
    return <li className="komsco-ai__formatted-list-item">{children}</li>;
  },
  ol({ children }) {
    return <ol className="komsco-ai__formatted-list komsco-ai__formatted-list--ordered">{children}</ol>;
  },
  p({ children }) {
    return <p className="komsco-ai__formatted-line">{children}</p>;
  },
  table({ children }) {
    return (
      <div className="komsco-ai__table-wrap">
        <table className="komsco-ai__table">{children}</table>
      </div>
    );
  },
  ul({ children }) {
    return <ul className="komsco-ai__formatted-list">{children}</ul>;
  },
});

const AssistantMarkdown: React.FC<AssistantMarkdownProps> = ({
  content,
  streaming = false,
  uiLanguage = 'ko',
  variant = 'default',
}) => {
  const prepared = React.useMemo(
    () => prepareMarkdownContent(content, streaming),
    [content, streaming],
  );

  return (
    <div
      className={`komsco-ai__markdown komsco-ai__markdown--${variant}${
        streaming ? ' is-streaming' : ''
      }`}
    >
      <ReactMarkdown
        components={markdownComponents(uiLanguage)}
        rehypePlugins={[rehypeSanitize]}
        remarkPlugins={[remarkGfm]}
        skipHtml
      >
        {prepared}
      </ReactMarkdown>
    </div>
  );
};

export default AssistantMarkdown;
