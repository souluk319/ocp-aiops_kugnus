import { isCommandLikeLine, isMarkdownHeadingLine } from './assistant.commandDetection';

const COMMAND_LANGUAGES = new Set(['bash', 'sh', 'shell', 'zsh', 'console', 'terminal']);
const FENCE_RE = /^\s*```([A-Za-z0-9_-]+)?\s*$/;
const CLOSE_FENCE_RE = /^\s*```\s*$/;
const STANDALONE_COMMAND_RE = /^(?:\$+\s*)?(oc|kubectl|curl|docker|podman|helm)\b/;
const CONTINUATION_RE = /^(\\|&&|\|\||--[A-Za-z0-9][A-Za-z0-9-]*\b)/;

export const isCommandLanguage = (language?: string): boolean =>
  Boolean(language && COMMAND_LANGUAGES.has(language.toLowerCase()));

export const isExecutableCommandLine = (line: string): boolean => {
  const trimmed = line.trim();
  if (!trimmed) {
    return false;
  }
  if (isMarkdownHeadingLine(trimmed)) {
    return false;
  }
  if (STANDALONE_COMMAND_RE.test(trimmed)) {
    return true;
  }
  if (isCommandLikeLine(trimmed)) {
    return true;
  }
  return CONTINUATION_RE.test(trimmed);
};

export const isCommandBlock = (code: string, language?: string): boolean => {
  const lines = code
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
  if (lines.length === 0) {
    return false;
  }
  if (isCommandLanguage(language)) {
    return lines.some(isExecutableCommandLine);
  }
  return lines.every(isExecutableCommandLine);
};

const countFenceMarkers = (content: string): number =>
  content.split('\n').filter((line) => FENCE_RE.test(line)).length;

const fixSingleBacktickClosers = (content: string): string =>
  content
    .split('\n')
    .map((line) => (line.trim() === '`' ? '```' : line))
    .join('\n');

const emitCommandBlock = (output: string[], commandLines: string[], language: string) => {
  if (commandLines.length === 0) {
    return;
  }
  output.push(`\`\`\`${language || 'bash'}`, ...commandLines, '```');
};

const repairCommandFenceBlock = (
  output: string[],
  language: string,
  blockLines: string[],
): boolean => {
  const hasNestedFence = blockLines.some((line) => FENCE_RE.test(line));
  const proseLines = blockLines.filter((line) => {
    const trimmed = line.trim();
    return trimmed && !FENCE_RE.test(trimmed) && !isExecutableCommandLine(trimmed);
  });
  const hasProse = proseLines.length > 0;

  if (!hasNestedFence && !hasProse) {
    return false;
  }

  let currentCommand: string[] = [];

  blockLines.forEach((line) => {
    const trimmed = line.trim();
    if (FENCE_RE.test(trimmed)) {
      return;
    }
    if (!trimmed) {
      if (currentCommand.length > 0) {
        currentCommand.push('');
      }
      return;
    }
    if (isExecutableCommandLine(trimmed)) {
      currentCommand.push(line);
      return;
    }

    emitCommandBlock(output, currentCommand, language || 'bash');
    currentCommand = [];
    output.push(line);
  });

  emitCommandBlock(output, currentCommand, language || 'bash');
  return true;
};

const repairFencedCommandBlocks = (content: string): string => {
  const lines = content.split('\n');
  const output: string[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    const open = line.match(FENCE_RE);
    if (!open) {
      output.push(line);
      index += 1;
      continue;
    }

    const language = open[1] || '';
    const blockLines: string[] = [];
    index += 1;
    while (index < lines.length && !CLOSE_FENCE_RE.test(lines[index])) {
      blockLines.push(lines[index]);
      index += 1;
    }
    const closed = index < lines.length;

    if (isCommandLanguage(language) && repairCommandFenceBlock(output, language, blockLines)) {
      index += closed ? 1 : 0;
      continue;
    }

    output.push(line, ...blockLines);
    if (closed) {
      output.push(lines[index]);
      index += 1;
    }
  }

  return output.join('\n');
};

const wrapStandaloneCommands = (content: string): string => {
  const lines = content.split('\n');
  const output: string[] = [];
  let commandLines: string[] = [];
  let inFence = false;

  const flush = () => {
    emitCommandBlock(output, commandLines, 'bash');
    commandLines = [];
  };

  lines.forEach((line) => {
    if (FENCE_RE.test(line)) {
      flush();
      inFence = !inFence;
      output.push(line);
      return;
    }

    if (!inFence && isExecutableCommandLine(line.trim())) {
      commandLines.push(line);
      return;
    }

    flush();
    output.push(line);
  });

  flush();
  return output.join('\n');
};

export const prepareMarkdownContent = (content: string, streaming: boolean): string => {
  const fixedClosers = fixSingleBacktickClosers(content.replace(/\r\n/g, '\n'));
  const repaired = wrapStandaloneCommands(repairFencedCommandBlocks(fixedClosers));
  if (!streaming || countFenceMarkers(repaired) % 2 === 0) {
    return repaired;
  }
  return `${repaired}\n\`\`\``;
};
