import { stripPublicWebReferenceLines } from './assistant.markdownPrepare';

const PRIVATE_REASONING_START_RE =
  /(<\|channel\|>\s*(?:thought|analysis)\s*<channel>|<\|start_header_id\|>\s*(?:thought|analysis)\s*<\|end_header_id\|>|<think>|<(?:thought|analysis)>)/i;
const PRIVATE_REASONING_END_RE =
  /(<\|channel\|>\s*(?:final|assistant)\s*<channel>|<\|start_header_id\|>\s*(?:final|assistant)\s*<\|end_header_id\|>|<\/think>|<\/(?:thought|analysis)>|<(?:final|assistant)>)/i;
const PRIVATE_REASONING_TOKEN_RE = /<\|[^>\n]*\|>|<\/?channel>|<\/?(?:thought|analysis|final|assistant)>/gi;
const PRIVATE_REASONING_LEAK_LINE_RE =
  /^\s*(?:(?:thought|analysis)\b.*\b(?:user|I\s+(?:need|should|have|will)|tool|called|already)\b|(?:I\s+(?:need|should|have|will)|I\s+have\s+already|Let's\s+search|Looking\s+at\s+the\s+.*output|Patterns\s+to\s+search)\b)/i;

export const stripPrivateReasoningText = (content: string): string => {
  let privateReasoningActive = false;
  const output: string[] = [];

  content.replace(/\r\n/g, '\n').split(/(?<=\n)/).forEach((line) => {
    let remaining = line;

    while (remaining) {
      if (privateReasoningActive) {
        const endMatch = remaining.match(PRIVATE_REASONING_END_RE);
        if (!endMatch || endMatch.index === undefined) {
          remaining = '';
          break;
        }
        privateReasoningActive = false;
        remaining = remaining.slice(endMatch.index + endMatch[0].length);
        continue;
      }

      const startMatch = remaining.match(PRIVATE_REASONING_START_RE);
      if (!startMatch || startMatch.index === undefined) {
        const cleaned = remaining.replace(PRIVATE_REASONING_TOKEN_RE, '');
        if (!PRIVATE_REASONING_LEAK_LINE_RE.test(cleaned)) {
          output.push(cleaned);
        }
        remaining = '';
        break;
      }

      const before = remaining.slice(0, startMatch.index).replace(PRIVATE_REASONING_TOKEN_RE, '');
      if (before) {
        output.push(before);
      }
      privateReasoningActive = true;
      remaining = remaining.slice(startMatch.index + startMatch[0].length);
    }
  });

  return output.join('');
};

export const normalizeAssistantDisplayText = (content: string): string =>
  stripPublicWebReferenceLines(stripPrivateReasoningText(content))
    .replace(/\bOpenShift\s+Lightspeed(?:\s*\(OLS\))?\b/gi, 'AIOps')
    .replace(/\bKOMSCO\s+AI\s+AGENT\b/gi, 'AIOps');

export const messagePreview = (content: string, limit = 110): string => {
  const collapsed = normalizeAssistantDisplayText(content).replace(/\s+/g, ' ').trim();
  if (!collapsed) {
    return '내용 없음';
  }

  return collapsed.length > limit ? `${collapsed.slice(0, limit - 1)}...` : collapsed;
};
