export type AssistantFollowupOption = {
  index: number;
  prompt: string;
};

export type AssistantFollowupBlock = {
  after: string;
  before: string;
  options: AssistantFollowupOption[];
};

const NUMBERED_OPTION_RE = /^\s*(\d{1,2})[.)]\s+(.+?)\s*$/;
const INLINE_BOLD_HEADING_RE = /^\*\*(.+?)\*\*\s*[:：]?\s*(.*)$/;
const FOLLOWUP_HEADING_RE =
  /^(?:(?:다음\s*단계로?|다음으로)?\s*무엇을\s*(?:도와드릴까요|확인할까요)|what\s+would\s+you\s+like\s+(?:to\s+check|me\s+to\s+do)\s+next)\??$/i;

const normalizeHeading = (line: string): string =>
  line
    .trim()
    .replace(/^(?:#{1,6}\s+)+/, '')
    .replace(/[:：]\s*$/, '')
    .replace(/^\*\*(.+?)\*\*$/, '$1')
    .trim();

export const cleanAssistantFollowupPrompt = (raw: string): string => {
  let prompt = raw.trim().replace(/^[-•]\s*/, '');
  const headingMatch = prompt.match(INLINE_BOLD_HEADING_RE);
  if (headingMatch) {
    const heading = headingMatch[1].trim();
    const detail = headingMatch[2].trim();
    prompt = detail ? `${heading}: ${detail}` : heading;
  }
  return prompt
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\s+/g, ' ')
    .trim();
};

export const rewriteAssistantFollowupQuery = (raw: string): string => {
  let query = cleanAssistantFollowupPrompt(raw)
    .replace(/[?？]\s*$/, '')
    .trim();

  const englishLead = query.match(/^(?:would you like (?:me )?to|should i|shall i)\s+(.+)$/i);
  if (englishLead) {
    return englishLead[1].trim();
  }

  const koreanRewrites: Array<[RegExp, string]> = [
    [/해\s*드릴까요$/i, '해줘'],
    [/해드릴까요$/i, '해줘'],
    [/확인하시겠습니까$/i, '확인해줘'],
    [/점검하시겠습니까$/i, '점검해줘'],
    [/분석하시겠습니까$/i, '분석해줘'],
    [/진행하시겠습니까$/i, '진행해줘'],
    [/해\s*볼까요$/i, '해줘'],
    [/만들까요$/i, '만들어줘'],
    [/볼까요$/i, '봐줘'],
    [/할까요$/i, '해줘'],
    [/보여드릴까요$/i, '보여줘'],
    [/알려드릴까요$/i, '알려줘'],
    [/드릴까요$/i, '줘'],
  ];

  for (const [pattern, replacement] of koreanRewrites) {
    if (pattern.test(query)) {
      query = query.replace(pattern, replacement);
      break;
    }
  }

  return query.replace(/\s+/g, ' ').trim();
};

const followupHeadingAt = (lines: string[]): number => {
  let inCodeFence = false;

  for (let index = 0; index < lines.length; index += 1) {
    const trimmed = lines[index].trim();
    if (/^(?:```|~~~)/.test(trimmed)) {
      inCodeFence = !inCodeFence;
      continue;
    }
    if (!inCodeFence && FOLLOWUP_HEADING_RE.test(normalizeHeading(trimmed))) {
      return index;
    }
  }
  return -1;
};

export const parseAssistantFollowupBlock = (
  content: string,
  limit = 3,
): AssistantFollowupBlock | null => {
  const lines = (content || '').split(/\r?\n/);
  const headingIndex = followupHeadingAt(lines);
  if (headingIndex < 0) {
    return null;
  }

  const options: AssistantFollowupOption[] = [];
  let blockEnd = headingIndex + 1;
  let sawOption = false;

  for (let index = headingIndex + 1; index < lines.length; index += 1) {
    const trimmed = lines[index].trim();
    if (!trimmed) {
      blockEnd = index + 1;
      continue;
    }
    if (/^(?:```|~~~)/.test(trimmed)) {
      return null;
    }

    const match = trimmed.match(NUMBERED_OPTION_RE);
    if (!match) {
      if (sawOption) {
        break;
      }
      return null;
    }

    sawOption = true;
    blockEnd = index + 1;
    const prompt = cleanAssistantFollowupPrompt(match[2]);
    if (prompt && options.length < limit) {
      options.push({
        index: Number(match[1]),
        prompt,
      });
    }
  }

  if (options.length === 0) {
    return null;
  }

  return {
    after: lines.slice(blockEnd).join('\n').trimStart(),
    before: lines.slice(0, headingIndex).join('\n').trimEnd(),
    options,
  };
};
