import * as React from 'react';

import { CoolCopyIcon, CoolWrapTextIcon } from './coolicons';
import { INLINE_PATTERN, MARKDOWN_LINK_PATTERN, URL_PATTERN } from './assistant.constants';
import { isCommandLikeLine } from './assistant.commandDetection';
import type { RagAppendixRef, UiLanguage } from './assistant.types';
import { redactSensitiveText } from '../utils/evidenceDisplay';

export { isCommandLikeLine, isMarkdownHeadingLine } from './assistant.commandDetection';

export const cleanMarkdownLabel = (label: string): string =>
  label
    .replace(/\\(\[|\])/g, '$1')
    .replace(/\s+/g, ' ')
    .trim();

export const stripDefaultEvidenceAppendix = (content: string): string => {
  const lines = content.split('\n');
  const appendixIndex = lines.findIndex((line) =>
    /^\s*\[?\s*(?:RAG\s*근거|참고\s*문서)\s*\]?\s*$/i.test(line.trim()),
  );

  if (appendixIndex < 0) {
    return content;
  }

  return lines.slice(0, appendixIndex).join('\n').trimEnd();
};

export const extractRagAppendixRefs = (content: string): RagAppendixRef[] => {
  const lines = content.split('\n');
  const appendixIndex = lines.findIndex((line) =>
    /^\s*\[?\s*(?:RAG\s*근거|참고\s*문서)\s*\]?\s*$/i.test(line.trim()),
  );

  if (appendixIndex < 0) {
    return [];
  }

  const refs: RagAppendixRef[] = [];
  lines.slice(appendixIndex + 1).forEach((rawLine) => {
    const line = rawLine.trim();
    const titleMatch = line.match(/^\d+\.\s+(.+?)(?:\s+\([^)]*\))?$/);
    if (titleMatch) {
      refs.push({ title: titleMatch[1].trim() });
      return;
    }

    const sourceMatch = line.match(/^[-*]\s*source:\s*(.+)$/i);
    if (sourceMatch && refs.length > 0) {
      refs[refs.length - 1] = {
        ...refs[refs.length - 1],
        sourceUri: sourceMatch[1].trim(),
      };
    }
  });

  return refs.slice(0, 5);
};

export const parseMarkdownLink = (line: string): { href: string; label: string } | null => {
  const match = line.match(MARKDOWN_LINK_PATTERN);

  if (!match) {
    return null;
  }

  return {
    href: match[2].replace(/[),.;]+$/, ''),
    label: cleanMarkdownLabel(match[1]),
  };
};

export const trimIndentedCodeLine = (line: string): string => line.replace(/^( {4}|\t)/, '');

export const collectIndentedBlock = (lines: string[], startIndex: number): string[] => {
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

const CODE_BLOCK_LABELS: Record<
  UiLanguage,
  { copyCommand: string; showWrapped: string; showUnwrapped: string }
> = {
  en: {
    copyCommand: 'Copy command',
    showUnwrapped: 'Disable line wrap',
    showWrapped: 'Wrap lines',
  },
  ko: {
    copyCommand: '명령 복사',
    showUnwrapped: '개행 해제',
    showWrapped: '개행 표시',
  },
};

const CodeBlock: React.FC<{ language?: string; lines: string[]; uiLanguage?: UiLanguage }> = ({
  language,
  lines,
  uiLanguage = 'ko',
}) => {
  const [wrapped, setWrapped] = React.useState(false);
  const code = lines.join('\n').trimEnd();
  const labels = CODE_BLOCK_LABELS[uiLanguage];

  return (
    <pre
      className={`komsco-ai__formatted-code-block${
        wrapped ? ' komsco-ai__formatted-code-block--wrapped' : ''
      }`}
      data-language={language || undefined}
    >
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
          aria-label={labels.copyCommand}
          className="komsco-ai__code-copy"
          onClick={() => {
            if (navigator.clipboard) {
              void navigator.clipboard.writeText(redactSensitiveText(code));
            }
          }}
          type="button"
        >
          <CoolCopyIcon />
        </button>
      </div>
    </pre>
  );
};

export const renderCodeBlock = (
  lines: string[],
  key: string,
  language?: string,
  uiLanguage: UiLanguage = 'ko',
): React.ReactNode => (
  <CodeBlock key={key} language={language} lines={lines} uiLanguage={uiLanguage} />
);

export const renderInlineText = (
  text: string,
  keyPrefix: string,
  uiLanguage: UiLanguage = 'ko',
): React.ReactNode[] =>
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
      const innerText = part.slice(1, -1);
      if (isCommandLikeLine(innerText)) {
        return (
          <CodeBlock
            key={`${keyPrefix}-code-${index}`}
            lines={[innerText]}
            uiLanguage={uiLanguage}
          />
        );
      }

      return (
        <code className="komsco-ai__formatted-code" key={`${keyPrefix}-code-${index}`}>
          {innerText}
        </code>
      );
    }

    if (part.startsWith('**') && part.endsWith('**')) {
      return (
        <strong className="komsco-ai__formatted-strong" key={`${keyPrefix}-strong-${index}`}>
          {renderInlineText(part.slice(2, -2), `${keyPrefix}-strong-${index}`, uiLanguage)}
        </strong>
      );
    }

    return <React.Fragment key={`${keyPrefix}-text-${index}`}>{part}</React.Fragment>;
  });

const FORMATTED_HEADING_TONE_KEYWORDS: Array<{ keywords: string[]; tone: string }> = [
  { keywords: ['재발 방지', '재발방지'], tone: 'prevention' },
  { keywords: ['후속 조치', '후속조치'], tone: 'followup' },
  { keywords: ['권장 조치', '조치 방안', '조치'], tone: 'action' },
  { keywords: ['추가 확인', '검증'], tone: 'evidence' },
  { keywords: ['원인'], tone: 'cause' },
  { keywords: ['근거'], tone: 'evidence' },
];

export const formattedHeadingTone = (headingText: string): string | undefined => {
  const match = FORMATTED_HEADING_TONE_KEYWORDS.find(({ keywords }) =>
    keywords.some((keyword) => headingText.includes(keyword)),
  );
  return match?.tone;
};
