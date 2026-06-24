export const safeEvidenceText = (value: unknown, fallback = ''): string => {
  const raw = String(value ?? fallback).trim();
  if (!raw) {
    return fallback;
  }

  return raw
    .replace(
      /\b((?:x[-_]?api[-_]?key|api[-_]?key|apikey|apiKey|token|access[-_]?token|refresh[-_]?token|client[-_]?secret|secret|password|passwd|authorization)\s*[:=]\s*)(["']?)[^\s,"'`<>]+(?:\2)?/gi,
      '$1[redacted-secret]',
    )
    .replace(/Bearer\s+[A-Za-z0-9._~+\/=-]+/gi, 'Bearer [redacted]')
    .replace(/sha256~[A-Za-z0-9._~-]+/gi, '[redacted-token]')
    .replace(/\b(?:AKIA|ASIA)[A-Z0-9]{16}\b/g, '[redacted-token]')
    .replace(/\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}(?:\.[A-Za-z0-9_-]{8,})?\b/g, '[redacted-token]')
    .replace(/\b(?:github_pat|gh[pousr]|glpat|sk|xox[baprs])-?[A-Za-z0-9_=-]{16,}\b/gi, '[redacted-token]')
    .replace(/\b(?=[A-Za-z0-9._~+\/=-]{40,}\b)(?=.*[._~+\/=-])[A-Za-z0-9._~+\/=-]+\b/g, '[redacted-token]')
    .replace(/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g, '[redacted-email]')
    .replace(/\b(kubeadmin|admin)\b/gi, '[redacted-user]')
    .slice(0, 96);
};

export const shortDigest = (value: unknown): string => {
  const digest = String(value ?? '').trim();
  if (!digest) {
    return '';
  }

  if (digest.startsWith('sha256:')) {
    return `sha256:${digest.slice(7, 19)}`;
  }

  return digest.length > 18 ? `${digest.slice(0, 18)}...` : digest;
};

export const evidenceCount = (
  summaryValue: unknown,
  statusCount: number,
  fallbackCount: number,
): number => {
  const summaryCount = Number(summaryValue);
  if (Number.isFinite(summaryCount) && summaryCount > 0) {
    return summaryCount;
  }

  return Math.max(statusCount, fallbackCount, 0);
};
