import * as React from 'react';

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
import type { Message, UiLanguage } from './assistant.types';
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
  | 'followup'
  | 'cause'
  | 'action'
  | 'verification'
  | 'terminal'
  | 'details';

type RunbookSection = {
  id: RunbookSectionId;
  lines: string[];
  title: string;
};

const RUNBOOK_SECTION_TITLES: Record<UiLanguage, Record<RunbookSectionId, string>> = {
  en: {
    action: 'Action Plan',
    cause: 'Root Cause Candidates',
    details: 'Evidence Details',
    evidence: 'Confirmed Evidence',
    followup: 'Additional Checks',
    impact: 'Impact Scope',
    summary: 'Current Assessment',
    terminal: 'Terminal Read-Only Commands',
    verification: 'Verification / Rollback',
  },
  ko: {
    action: 'Action Plan',
    cause: '원인 후보',
    details: '근거 상세보기',
    evidence: '확인한 근거',
    followup: '추가 확인',
    impact: '영향 범위',
    summary: '현재 판단',
    terminal: '터미널 확인 명령',
    verification: '검증/롤백',
  },
};

const RUNBOOK_SECTION_META: Record<
  UiLanguage,
  Record<RunbookSectionId, { badge: string; subtitle: string; tone: 'high' | 'mid' | 'low' | 'neutral' }>
> = {
  en: {
    action: {
      badge: 'Action',
      subtitle: 'Approval conditions and execution checks',
      tone: 'high',
    },
    cause: {
      badge: 'RCA',
      subtitle: 'Likely causes narrowed by symptoms and evidence',
      tone: 'mid',
    },
    details: {
      badge: 'Details',
      subtitle: 'Source evidence for audit and review',
      tone: 'neutral',
    },
    evidence: {
      badge: 'Evidence',
      subtitle: 'Signals and query results confirmed from the cluster',
      tone: 'low',
    },
    followup: {
      badge: 'Check',
      subtitle: 'Items that still need confirmation',
      tone: 'low',
    },
    impact: {
      badge: 'Impact',
      subtitle: 'Service impact scope and priority',
      tone: 'mid',
    },
    summary: {
      badge: 'Assess',
      subtitle: 'Current situation and first items to read',
      tone: 'low',
    },
    terminal: {
      badge: 'Commands',
      subtitle: 'Safe read-only commands for terminal verification',
      tone: 'neutral',
    },
    verification: {
      badge: 'Verify',
      subtitle: 'Post-execution checks and rollback path',
      tone: 'low',
    },
  },
  ko: {
    action: {
      badge: '조치',
      subtitle: '승인 조건과 실행 전 확인 사항',
      tone: 'high',
    },
    cause: {
      badge: '분석',
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
    followup: {
      badge: '확인',
      subtitle: '아직 확정되지 않은 항목',
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
    terminal: {
      badge: '명령',
      subtitle: '터미널에서 안전하게 확인할 read-only 명령',
      tone: 'neutral',
    },
    verification: {
      badge: '검증',
      subtitle: '실행 후 확인과 실패 시 되돌림',
      tone: 'low',
    },
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
  if (
    /^(요약|현재 판단|우선 판단|우선 확인|상세 분석|분석 결과|결론|summary|current assessment|assessment|priority assessment|conclusion|request clarification)$/i.test(
      heading,
    )
  ) {
    return 'summary';
  }
  if (
    /^(영향 범위|운영 영향|서비스 영향|영향|대상|범위|심각도|우선순위|impact scope|operational impact|service impact|impact|target|scope|severity|priority)$/i.test(
      heading,
    )
  ) {
    return 'impact';
  }
  if (
    /^(확인한 근거|실제 근거|근거|증거|관측 근거|확인 근거|confirmed evidence|query evidence|evidence|observed evidence)$/i.test(
      heading,
    )
  ) {
    return 'evidence';
  }
  if (
    /^(추가 확인|추가 확인 필요|확인 필요 항목|다음 확인|다음 확인 명령|additional checks|additional check|needed information|next check|next step)$/i.test(
      heading,
    )
  ) {
    return 'followup';
  }
  if (
    /^(원인 후보|원인 후보 및 추가 확인 필요 항목|가능한 원인|원인|가설|root cause candidates|root cause|possible causes|cause candidates|causes)$/i.test(
      heading,
    )
  ) {
    return 'cause';
  }
  if (/^(action plan|조치 계획|실행 계획|권장 조치|권장 명령|조치)$/i.test(heading)) {
    return 'action';
  }
  if (
    /^(검증\/롤백|검증|롤백|확인 및 롤백|verification \/ rollback|verification\/rollback|verification|rollback|verify and rollback)$/i.test(
      heading,
    )
  ) {
    return 'verification';
  }
  if (
    /^(터미널 확인 명령|확인 명령|조회 명령|read-only 명령|oc 확인 명령|terminal read-only commands|terminal commands|read-only commands|query commands|oc commands)$/i.test(
      heading,
    )
  ) {
    return 'terminal';
  }
  if (/^(근거 상세보기|상세 근거|상세|원문 근거|evidence details|details|source evidence)$/i.test(heading)) {
    return 'details';
  }
  return null;
};

const parseRunbookSections = (content: string, language: UiLanguage): RunbookSection[] | null => {
  const lines = stripDefaultEvidenceAppendix(content).split('\n');
  const intro: string[] = [];
  const sections: RunbookSection[] = [];
  const titles = RUNBOOK_SECTION_TITLES[language];
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
        title: titles[sectionId],
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
      title: titles.summary,
    });
  }

  return sections.length >= 3 ? sections : null;
};

const renderRunbookLines = (
  lines: string[],
  sectionKey: string,
  sectionId: RunbookSectionId,
  language: UiLanguage,
): React.ReactNode => {
  const items = lines
    .map((line) => line.trim())
    .filter(Boolean)
    .filter((line) => !/^```/.test(line))
    .map((line) => line.replace(/^[-*]\s+/, '').replace(/^\d+\.\s+/, ''));

  if (items.length === 0) {
    return <p>{language === 'en' ? 'No displayable content.' : '표시할 내용이 없습니다.'}</p>;
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

  if (sectionId === 'summary') {
    return (
      <div className="komsco-ai__runbook-paragraph-stack">
        {items.slice(0, 6).map((item, index) => (
          <p key={`${sectionKey}-${index}`}>{renderInlineText(item, `${sectionKey}-${index}`)}</p>
        ))}
      </div>
    );
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

const renderRunbookAnswer = (sections: RunbookSection[], language: UiLanguage): React.ReactNode => (
  <div className="komsco-ai__runbook-answer">
    {sections.map((section, index) => {
      const meta = RUNBOOK_SECTION_META[language][section.id];
      return (
        <section
          className={`komsco-ai__runbook-section is-${section.id} tone-${meta.tone}`}
          key={section.id}
        >
          <div className="komsco-ai__runbook-section-head">
            <span className="komsco-ai__runbook-step-index">
              {String(index + 1).padStart(2, '0')}
            </span>
            <span className="komsco-ai__runbook-section-copy">
              <span className="komsco-ai__runbook-section-title">{section.title}</span>
              <span className="komsco-ai__runbook-section-subtitle">{meta.subtitle}</span>
            </span>
            <span className={`komsco-ai__runbook-badge tone-${meta.tone}`}>{meta.badge}</span>
          </div>
          <div className="komsco-ai__runbook-section-body">
            {renderRunbookLines(section.lines, `runbook-${section.id}`, section.id, language)}
          </div>
        </section>
      );
    })}
  </div>
);

export const renderFormattedContent = (
  message: Message,
  onPreviewAttachment: (attachment: ImageAttachment) => void,
  language: UiLanguage = 'ko',
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
  const runbookSections = parseRunbookSections(displayContent, language);
  if (runbookSections) {
    return renderRunbookAnswer(runbookSections, language);
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
