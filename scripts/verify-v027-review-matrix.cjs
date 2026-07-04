#!/usr/bin/env node

const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const reportPath = path.join(root, 'docs/Ver.0.2.7/chatbot-action-ui-test-review-report.md');

const mustContain = [
  {
    id: 'fixed_pdf',
    pattern: /verify-v027-fixed-pdf\.py[\s\S]*docs\/AIOps-For-OCP\.pdf/,
  },
  {
    id: 'toolplan_ui',
    pattern: /verify-v027-toolplan-chat-ui\.cjs[\s\S]*조회 계획/,
  },
  {
    id: 'action_plan_safety',
    pattern: /evaluate-aiops-actions-e2e\.py[\s\S]*--plan-only[\s\S]*--confirm-live-mutations/,
  },
  {
    id: 'ui_balance',
    pattern: /verify-v027-ui-balance\.cjs[\s\S]*failedCount=0/,
  },
  {
    id: 'portal_routes',
    pattern: /verify-v027-portal-routes\.cjs[\s\S]*failedCount=0/,
  },
  {
    id: 'refactor_progress',
    pattern: /AssistantLauncher\.tsx[\s\S]*(reduced to|줄에서|줄로 감소|3173 lines)/,
  },
  {
    id: 'local_9000_blocker_named',
    pattern: /api\.ocp\.cywell\.server:6443 TCP 연결 실패/,
  },
  {
    id: 'protected_artifacts',
    pattern: /docs\/version-progress-book\.html[\s\S]*docs\/aiops-beginner-guide\.html[\s\S]*evals\/aiops-scenarios\/\*/,
  },
];

const protectedPaths = [
  'docs/version-progress-book.html',
  'docs/aiops-beginner-guide.html',
  'docs/Ver.0.1.8/aiops-llm-strategy-brief.html',
  'evals/aiops-scenarios',
];

const readReport = () => {
  if (!fs.existsSync(reportPath)) {
    throw new Error(`Missing report: ${path.relative(root, reportPath)}`);
  }
  return fs.readFileSync(reportPath, 'utf8');
};

const uniqueNumbers = (matches) =>
  [...new Set(matches.map((match) => Number(match[1])).filter((value) => Number.isFinite(value)))];

const gitStatusFor = (paths) => {
  const output = execFileSync('git', ['status', '--short', '--', ...paths], {
    cwd: root,
    encoding: 'utf8',
  });
  return output
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
};

const main = () => {
  const report = readReport();
  const reviewRows = uniqueNumbers([...report.matchAll(/^\|\s*R(\d+)\s*\|/gm)]);
  const sectionRounds = uniqueNumbers([...report.matchAll(/^###\s+R(\d+)\b/gm)]);
  const allRounds = [...new Set([...reviewRows, ...sectionRounds])].sort((a, b) => a - b);
  const latestRound = allRounds.at(-1) || 0;
  const missingEvidence = mustContain
    .filter((item) => !item.pattern.test(report))
    .map((item) => item.id);
  const protectedStatus = gitStatusFor(protectedPaths);

  const checks = {
    actionAndUiReviewCountAtLeastFive: reviewRows.length >= 5,
    hasRecentContinuationRounds: latestRound >= 52,
    requiredEvidencePresent: missingEvidence.length === 0,
    protectedArtifactsUntouched: protectedStatus.length === 0,
  };

  const ok = Object.values(checks).every(Boolean);
  const result = {
    checks,
    latestRound,
    missingEvidence,
    ok,
    protectedStatus,
    reviewRowCount: reviewRows.length,
    sectionRoundCount: sectionRounds.length,
    verifier: 'verify-v027-review-matrix',
  };
  console.log(JSON.stringify(result, null, 2));

  if (!ok) {
    process.exitCode = 1;
  }
};

main();
