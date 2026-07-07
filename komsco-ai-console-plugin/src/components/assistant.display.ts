import { stripPublicWebReferenceLines } from './assistant.markdownPrepare';

export const normalizeAssistantDisplayText = (content: string): string =>
  stripPublicWebReferenceLines(content)
    .replace(/\bOpenShift\s+Lightspeed(?:\s*\(OLS\))?\b/gi, 'AIOps')
    .replace(/\bKOMSCO\s+AI\s+AGENT\b/gi, 'AIOps');

export const messagePreview = (content: string, limit = 110): string => {
  const collapsed = normalizeAssistantDisplayText(content).replace(/\s+/g, ' ').trim();
  if (!collapsed) {
    return '내용 없음';
  }

  return collapsed.length > limit ? `${collapsed.slice(0, limit - 1)}...` : collapsed;
};
