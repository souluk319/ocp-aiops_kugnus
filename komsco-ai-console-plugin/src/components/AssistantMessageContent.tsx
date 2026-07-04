import * as React from 'react';

import { CoolCaretDownIcon } from './coolicons';
import { normalizeAssistantDisplayText } from './assistant.display';
import { formatFileSize, getAttachmentPreviewUrl } from './assistant.attachments';
import {
  cleanMarkdownLabel,
  collectIndentedBlock,
  formattedHeadingTone,
  isCommandLikeLine,
  parseMarkdownLink,
  renderCodeBlock,
  renderInlineText,
  stripDefaultEvidenceAppendix,
  trimIndentedCodeLine,
} from './assistant.render';
import type { Message } from './assistant.types';
import type { ImageAttachment } from '../services/aiGateway';

const renderAttachmentGrid = (
  attachments: ImageAttachment[] | undefined,
  keyPrefix: string,
  onPreview: (attachment: ImageAttachment) => void,
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

type RunbookSectionId =
  | 'summary'
  | 'impact'
  | 'evidence'
  | 'cause'
  | 'action'
  | 'verification'
  | 'details';

type RunbookSection = {
  id: RunbookSectionId;
  lines: string[];
  title: string;
};

const RUNBOOK_SECTION_TITLES: Record<RunbookSectionId, string> = {
  action: 'Action Plan',
  cause: '원인 후보',
  details: '근거 상세보기',
  evidence: '확인한 근거',
  impact: '영향 범위',
  summary: '현재 판단',
  verification: '검증/롤백',
};

const RUNBOOK_SECTION_META: Record<
  RunbookSectionId,
  { badge: string; subtitle: string; tone: 'high' | 'mid' | 'low' | 'neutral' }
> = {
  action: {
    badge: '조치',
    subtitle: '승인 조건과 실행 전 확인 사항',
    tone: 'high',
  },
  cause: {
    badge: '가설',
    subtitle: '증상과 근거로 좁힌 원인 후보',
    tone: 'mid',
  },
  details: {
    badge: '상세',
    subtitle: '감사와 재검토를 위한 원문 근거',
    tone: 'neutral',
  },
  evidence: {
    badge: '근거',
    subtitle: '클러스터에서 확인한 신호와 조회 결과',
    tone: 'low',
  },
  impact: {
    badge: '영향',
    subtitle: '서비스 영향 범위와 우선순위',
    tone: 'mid',
  },
  summary: {
    badge: '판단',
    subtitle: '현재 상황과 먼저 볼 항목',
    tone: 'low',
  },
  verification: {
    badge: '검증',
    subtitle: '실행 후 확인과 실패 시 되돌림',
    tone: 'low',
  },
};

const normalizeRunbookHeading = (line: string): string =>
  line
    .replace(/^#+\s*/, '')
    .replace(/^\d+[.)]\s*/, '')
    .replace(/^[-*]\s*/, '')
    .replace(/[：:]\s*$/, '')
    .trim();

const runbookSectionId = (line: string): RunbookSectionId | null => {
  const heading = normalizeRunbookHeading(line).replace(/\s*\([^)]*\)\s*/g, '').trim();
  if (/^(요약|현재 판단|우선 판단|우선 확인|상세 분석|분석 결과|결론)$/i.test(heading)) {
    return 'summary';
  }
  if (/^(영향 범위|운영 영향|서비스 영향|영향|대상|범위|심각도|우선순위)$/i.test(heading)) {
    return 'impact';
  }
  if (/^(확인한 근거|실제 근거|근거|증거|관측 근거|확인 근거)$/i.test(heading)) {
    return 'evidence';
  }
  if (/^(원인 후보|원인 후보 및 추가 확인 필요 항목|추가 확인 필요|가능한 원인|원인|가설)$/i.test(heading)) {
    return 'cause';
  }
  if (/^(action plan|조치 계획|실행 계획|권장 조치|권장 명령|다음 확인|다음 확인 명령|조치)$/i.test(heading)) {
    return 'action';
  }
  if (/^(검증\/롤백|검증|롤백|확인 및 롤백)$/i.test(heading)) {
    return 'verification';
  }
  if (/^(근거 상세보기|상세 근거|상세|원문 근거)$/i.test(heading)) {
    return 'details';
  }
  return null;
};

const parseRunbookSections = (content: string): RunbookSection[] | null => {
  const lines = stripDefaultEvidenceAppendix(content).split('\n');
  const intro: string[] = [];
  const sections: RunbookSection[] = [];
  let current: RunbookSection | null = null;

  const pushCurrent = () => {
    if (!current) {
      return;
    }
    current.lines = current.lines.filter((line) => line.trim());
    if (current.lines.length > 0) {
      sections.push(current);
    }
    current = null;
  };

  lines.forEach((rawLine) => {
    const line = rawLine.trim();
    const sectionId = line ? runbookSectionId(line) : null;
    if (sectionId) {
      pushCurrent();
      current = {
        id: sectionId,
        lines: [],
        title: RUNBOOK_SECTION_TITLES[sectionId],
      };
      return;
    }
    if (current) {
      current.lines.push(rawLine);
      return;
    }
    intro.push(rawLine);
  });
  pushCurrent();

  const cleanIntro = intro.filter((line) => line.trim());
  if (cleanIntro.length > 0 && !sections.some((section) => section.id === 'summary')) {
    sections.unshift({
      id: 'summary',
      lines: cleanIntro.slice(0, 4),
      title: RUNBOOK_SECTION_TITLES.summary,
    });
  }

  return sections.length >= 3 ? sections : null;
};

const renderRunbookLines = (lines: string[], sectionKey: string): React.ReactNode => {
  const items = lines
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => line.replace(/^[-*]\s+/, '').replace(/^\d+\.\s+/, ''));

  if (items.length === 0) {
    return <p>표시할 내용이 없습니다.</p>;
  }

  if (items.every(isCommandLikeLine)) {
    return renderCodeBlock(items.slice(0, 6), `${sectionKey}-commands`);
  }

  if (items.length === 1) {
    if (isCommandLikeLine(items[0])) {
      return renderCodeBlock([items[0]], `${sectionKey}-command`);
    }

    return <p>{renderInlineText(items[0], `${sectionKey}-line`)}</p>;
  }

  return (
    <ul>
      {items.slice(0, 6).map((item, index) => (
        <li
          className={isCommandLikeLine(item) ? 'is-command' : undefined}
          key={`${sectionKey}-${index}`}
        >
          {isCommandLikeLine(item)
            ? renderCodeBlock([item], `${sectionKey}-${index}-command`)
            : renderInlineText(item, `${sectionKey}-${index}`)}
        </li>
      ))}
    </ul>
  );
};

const renderRunbookAnswer = (sections: RunbookSection[]): React.ReactNode => (
  <div className="komsco-ai__runbook-answer">
    {sections.map((section, index) => {
      const meta = RUNBOOK_SECTION_META[section.id];
      return (
        <details
          className={`komsco-ai__runbook-section is-${section.id} tone-${meta.tone}`}
          key={section.id}
          open={index === 0}
        >
          <summary className="komsco-ai__runbook-section-head">
            <span className="komsco-ai__runbook-step-index">
              {String(index + 1).padStart(2, '0')}
            </span>
            <span className="komsco-ai__runbook-section-copy">
              <span className="komsco-ai__runbook-section-title">{section.title}</span>
              <span className="komsco-ai__runbook-section-subtitle">{meta.subtitle}</span>
            </span>
            <span className={`komsco-ai__runbook-badge tone-${meta.tone}`}>{meta.badge}</span>
            <CoolCaretDownIcon />
          </summary>
          <div className="komsco-ai__runbook-section-body">
            {renderRunbookLines(section.lines, `runbook-${section.id}`)}
          </div>
        </details>
      );
    })}
  </div>
);

export const renderFormattedContent = (
  message: Message,
  onPreviewAttachment: (attachment: ImageAttachment) => void,
): React.ReactNode => {
  if (message.role === 'user') {
    return (
      <div className="komsco-ai__message-text">
        {message.content && <div>{message.content}</div>}
        {renderAttachmentGrid(message.attachments, 'message', onPreviewAttachment)}
      </div>
    );
  }

  const displayContent = normalizeAssistantDisplayText(message.content);
  const runbookSections = parseRunbookSections(displayContent);
  if (runbookSections) {
    return renderRunbookAnswer(runbookSections);
  }

  const lines = stripDefaultEvidenceAppendix(displayContent).split('\n');
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
      const headingText = line.replace(/^#+\s*/, '');
      const tone = formattedHeadingTone(headingText);
      nodes.push(
        <div
          className={`komsco-ai__formatted-heading${
            tone ? ` komsco-ai__formatted-heading--${tone}` : ''
          }`}
          key={`heading-${index}`}
        >
          {renderInlineText(headingText, `heading-${index}`)}
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
