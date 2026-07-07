export const isMarkdownHeadingLine = (line: string): boolean =>
  /^\s{0,3}#{1,6}\s+\S/.test(line);

export const isCommandLikeLine = (line: string): boolean => {
  const trimmed = line.trim();
  if (!trimmed || isMarkdownHeadingLine(trimmed)) {
    return false;
  }

  return /^(#|oc\s+|kubectl\s+|helm\s+|etcdctl\s+|curl\s+|podman\s+|docker\s+|jq\s+|grep\s+|watch\s+|export\s+)/.test(
    trimmed,
  );
};
