#!/usr/bin/env node

const fs = require('fs');

const DEFAULT_STATUS_URL =
  process.env.AIOPS_FEEDBACK_STATUS_URL ||
  `${(process.env.AIOPS_GATEWAY_URL || 'http://127.0.0.1:5174').replace(/\/+$/, '')}/v1/aiops/status`;

const usage = () => `Usage:
  node scripts/export-aiops-chat-feedback.cjs [--url URL] [--format json|jsonl|csv] [--output FILE]

Environment:
  AIOPS_FEEDBACK_STATUS_URL  Full /v1/aiops/status URL
  AIOPS_GATEWAY_URL          Gateway base URL, default http://127.0.0.1:5174
  AIOPS_BEARER_TOKEN         Optional bearer token for deployed Gateway access

Examples:
  node scripts/export-aiops-chat-feedback.cjs --format csv --output /tmp/aiops-feedback.csv
  AIOPS_BEARER_TOKEN="$(oc whoami -t)" node scripts/export-aiops-chat-feedback.cjs --url http://127.0.0.1:18080/v1/aiops/status --format jsonl
`;

const parseArgs = (argv) => {
  const options = {
    format: 'json',
    output: '',
    url: DEFAULT_STATUS_URL,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--help' || arg === '-h') {
      options.help = true;
    } else if (arg === '--url') {
      options.url = argv[++i] || '';
    } else if (arg.startsWith('--url=')) {
      options.url = arg.slice('--url='.length);
    } else if (arg === '--format') {
      options.format = argv[++i] || '';
    } else if (arg.startsWith('--format=')) {
      options.format = arg.slice('--format='.length);
    } else if (arg === '--output') {
      options.output = argv[++i] || '';
    } else if (arg.startsWith('--output=')) {
      options.output = arg.slice('--output='.length);
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }

  if (!['json', 'jsonl', 'csv'].includes(options.format)) {
    throw new Error(`Unsupported format: ${options.format}`);
  }
  if (!options.url) {
    throw new Error('Missing --url');
  }
  return options;
};

const asObject = (value) =>
  value && typeof value === 'object' && !Array.isArray(value) ? value : {};

const asText = (value) => (value == null ? '' : String(value));

const normalizedSource = (spec) => {
  const source = asText(spec.source).trim();
  const answerSource = asText(spec.answerSource).trim();
  if (source && source !== 'unknown') {
    return source;
  }
  if (answerSource && answerSource !== 'unknown') {
    return answerSource;
  }
  return 'unclassified_legacy';
};

const feedbackRows = (payload) => {
  const records = asObject(asObject(payload.spec).records).chatFeedback;
  if (!Array.isArray(records)) {
    return [];
  }

  return records.map((record) => {
    const metadata = asObject(record.metadata);
    const spec = asObject(record.spec);
    const subject = asObject(record.subject);
    return {
      answerContract: asText(spec.answerContract),
      answerSource: asText(spec.answerSource),
      conversationId: asText(spec.conversationId),
      createdAt: asText(metadata.createdAt),
      feedbackId: asText(metadata.name),
      intent: asText(spec.intent),
      messageId: asText(spec.messageId),
      mode: asText(spec.mode),
      optionalComment: asText(spec.optionalComment),
      rating: asText(spec.rating),
      route: asText(spec.route),
      source: normalizedSource(spec),
      subjectUsername: asText(subject.username),
      submittedAt: asText(spec.submittedAt),
    };
  });
};

const csvEscape = (value) => {
  const text = asText(value).replace(/\r?\n/g, ' ');
  if (/[",\n\r]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
};

const bucketText = (value) => {
  const text = asText(value).trim();
  return text || '(empty)';
};

const incrementCounter = (counter, value) => {
  const key = bucketText(value);
  counter[key] = (counter[key] || 0) + 1;
};

const sortCounter = (counter) =>
  Object.fromEntries(
    Object.entries(counter).sort(([leftKey, leftValue], [rightKey, rightValue]) => {
      if (rightValue !== leftValue) {
        return rightValue - leftValue;
      }
      return leftKey.localeCompare(rightKey);
    }),
  );

const latestTimestamp = (current, candidate) => {
  const text = asText(candidate).trim();
  if (!text) {
    return current;
  }
  if (!current) {
    return text;
  }

  const currentTime = Date.parse(current);
  const candidateTime = Date.parse(text);
  if (!Number.isNaN(currentTime) && !Number.isNaN(candidateTime)) {
    return candidateTime > currentTime ? text : current;
  }
  return text > current ? text : current;
};

const summarizeRows = (rows) => {
  const counters = {
    byIntent: {},
    byMode: {},
    byRating: {},
    byRoute: {},
    bySource: {},
  };
  let latestSubmittedAt = '';
  let negativeWithComment = 0;
  let withComment = 0;

  rows.forEach((row) => {
    incrementCounter(counters.byIntent, row.intent);
    incrementCounter(counters.byMode, row.mode);
    incrementCounter(counters.byRating, row.rating);
    incrementCounter(counters.byRoute, row.route);
    incrementCounter(counters.bySource, row.source);

    if (bucketText(row.optionalComment) !== '(empty)') {
      withComment += 1;
      if (bucketText(row.rating) === 'down') {
        negativeWithComment += 1;
      }
    }
    latestSubmittedAt = latestTimestamp(latestSubmittedAt, row.submittedAt || row.createdAt);
  });

  return {
    total: rows.length,
    withComment,
    negativeWithComment,
    latestSubmittedAt,
    byRating: sortCounter(counters.byRating),
    bySource: sortCounter(counters.bySource),
    byMode: sortCounter(counters.byMode),
    byIntent: sortCounter(counters.byIntent),
    byRoute: sortCounter(counters.byRoute),
  };
};

const serialize = (rows, options) => {
  if (options.format === 'jsonl') {
    return `${rows.map((row) => JSON.stringify(row)).join('\n')}${rows.length ? '\n' : ''}`;
  }
  if (options.format === 'csv') {
    const headers = [
      'feedbackId',
      'createdAt',
      'submittedAt',
      'conversationId',
      'messageId',
      'rating',
      'optionalComment',
      'mode',
      'source',
      'answerSource',
      'intent',
      'route',
      'answerContract',
      'subjectUsername',
    ];
    return [
      headers.join(','),
      ...rows.map((row) => headers.map((header) => csvEscape(row[header])).join(',')),
    ].join('\n') + '\n';
  }
  return JSON.stringify(
    {
      count: rows.length,
      exportedAt: new Date().toISOString(),
      summary: summarizeRows(rows),
      records: rows,
      sourceUrl: options.url,
    },
    null,
    2,
  ) + '\n';
};

const fetchStatus = async (url) => {
  const headers = { Accept: 'application/json' };
  if (process.env.AIOPS_BEARER_TOKEN) {
    headers.Authorization = `Bearer ${process.env.AIOPS_BEARER_TOKEN}`;
  }

  const response = await fetch(url, { headers });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`${url} -> ${response.status} ${response.statusText}: ${body.slice(0, 300)}`);
  }
  return response.json();
};

const main = async () => {
  const options = parseArgs(process.argv.slice(2));
  if (options.help) {
    process.stdout.write(usage());
    return;
  }

  const payload = await fetchStatus(options.url);
  const rows = feedbackRows(payload);
  const output = serialize(rows, options);

  if (options.output) {
    fs.writeFileSync(options.output, output, 'utf8');
    process.stderr.write(`Exported ${rows.length} feedback records to ${options.output}\n`);
  } else {
    process.stdout.write(output);
  }
};

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
});
