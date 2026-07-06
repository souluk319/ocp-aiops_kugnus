import * as React from 'react';

import {
  ANSWER_STREAM_STEP_ID,
  GATEWAY_PREP_STEP_ID,
  PREP_SUBTASKS,
  RESPONSE_WAIT_PHASES,
  RESPONSE_WAIT_STEP_ID,
  RUN_LOOP_STEP_ID,
  TOOL_LABELS,
} from './assistant.constants';
import type { ProgressStep } from './assistant.types';

export const normalizeToolName = (name: string): string =>
  name
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, '_');

export const formatToolTitle = (name: string): string => {
  const normalizedName = normalizeToolName(name);

  if (TOOL_LABELS[normalizedName]) {
    return TOOL_LABELS[normalizedName];
  }

  return normalizedName
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
};

const formatDuration = (milliseconds: number): string => {
  const safeMilliseconds = Math.max(0, milliseconds);

  if (safeMilliseconds < 1000) {
    return `${Math.max(1, Math.round(safeMilliseconds))}ms`;
  }

  const totalSeconds = Math.round(safeMilliseconds / 1000);

  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;

  if (minutes > 0) {
    return `${minutes}분 ${seconds}초`;
  }

  return `${seconds}초`;
};

const getElapsedMs = (step: ProgressStep): number => {
  if (step.status === 'running') {
    return Date.now() - step.startedAt;
  }

  return step.elapsedMs ?? (step.endedAt ?? step.startedAt) - step.startedAt;
};

const isResponseWaitStep = (step: ProgressStep): boolean =>
  step.id.startsWith(RESPONSE_WAIT_STEP_ID);

const isAnswerStreamStep = (step: ProgressStep): boolean => step.id === ANSWER_STREAM_STEP_ID;

const getResponseWaitMessageIndex = (startedAt: number): number => {
  const elapsedSeconds = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));

  return Math.min(RESPONSE_WAIT_PHASES.length - 1, Math.floor(elapsedSeconds / 3));
};

const getResponseWaitMessage = (startedAt: number): string => {
  const phase = RESPONSE_WAIT_PHASES[getResponseWaitMessageIndex(startedAt)];

  return `${phase.title} 중`;
};

export const rcaContextPhaseLabel = (phase?: string): string => {
  const normalized = String(phase || '')
    .trim()
    .toLowerCase();
  if (normalized === 'post_answer') {
    return '답변 근거 연결 완료';
  }
  if (normalized === 'pre_answer' || normalized === 'plan_ready') {
    return '답변 근거 준비 완료';
  }
  return '답변 근거 연결 완료';
};

const productProgressText = (value?: string): string => {
  const text = String(value || '').trim();
  if (!text) {
    return '';
  }

  const phaseMatch = text.match(/^RCA\s*문맥\s*연결\s*:\s*([a-z_]+)/i);
  if (phaseMatch) {
    return rcaContextPhaseLabel(phaseMatch[1]);
  }
  if (/^RCA\s*문맥\s*연결$/i.test(text)) {
    return '답변 근거';
  }
  if (text === 'RCA 문맥 연결 실패') {
    return '답변 근거 연결 실패';
  }
  const legacyRcaDigestText = ['RCA Context', 'digest와', ['evidence', 'refs'].join(' ')].join(' ');
  if (text.includes(legacyRcaDigestText)) {
    return '최종 답변에 사용한 근거를 연결했습니다.';
  }
  if (text.includes('수집/누락/실패 근거를 RCA Context로 연결')) {
    return '답변 전에 수집 근거와 추가 확인 항목을 정리했습니다.';
  }
  if (/^ev-[a-z0-9-]+\s+기록$/i.test(text)) {
    return '근거 기록 완료';
  }
  if (text === '증거 참조 기록 시작') {
    return '근거 기록 시작';
  }
  if (text === '증거 참조 기록') {
    return '근거 기록';
  }
  if (text === 'Rag Context Evidence') {
    return '문서 근거';
  }
  if (text === 'oc read-only namespace inventory') {
    return '네임스페이스 사용 여부 조회';
  }
  if (/^namespace\s+\d+개\s+read-only\s+조회$/i.test(text)) {
    const count = text.match(/^namespace\s+(\d+)개/i)?.[1] ?? '';
    return count ? `네임스페이스 ${count}개 조회 완료` : '네임스페이스 조회 완료';
  }
  if (/^intent\s+/i.test(text)) {
    return '요청 해석 완료';
  }
  if (text === 'RCA Context' || text === 'RCA Evidence Context' || text === 'RCA 근거 문맥') {
    return '답변 근거';
  }
  if (text === 'Active Alerts Evidence') {
    return '경고 근거';
  }
  if (text === 'Node Status Evidence') {
    return '노드 상태 근거';
  }
  if (text === 'Restart Metric Evidence') {
    return '재시작 지표 근거';
  }
  const ragSearchMatch = text.match(/^RAG 근거\s+(\d+)건\s+검색$/);
  if (ragSearchMatch) {
    return `문서 근거 ${ragSearchMatch[1]}건 확인`;
  }

  return text
    .replace(/Node 상태 RCA 증거 수집 완료/g, '노드 상태 근거 수집 완료')
    .replace(/Active Alert RCA 증거 수집 완료/g, '경고 근거 수집 완료')
    .replace(/Restart metric RCA 증거 수집 완료/g, '재시작 지표 수집 완료')
    .replace(/oc read-only namespace inventory/gi, '네임스페이스 사용 여부 조회')
    .replace(/request intent classifier/gi, '요청 해석 확인')
    .replace(/Node Status Evidence 시작/g, '노드 상태 근거 확인 시작')
    .replace(/Active Alerts Evidence 시작/g, '경고 근거 확인 시작')
    .replace(/Restart Metric Evidence 시작/g, '재시작 지표 확인 시작')
    .replace(/Node 상태 근거 수집 완료/g, '노드 상태 근거 수집 완료')
    .replace(/Active Alert 근거 수집 완료/g, '경고 근거 수집 완료')
    .replace(/Restart metric 근거 수집 완료/g, '재시작 지표 수집 완료')
    .replace(/문서 근거 시작/g, '문서 근거 확인 시작')
    .replace(/Rag Context Evidence 시작/g, '문서 근거 확인 시작')
    .replace(/Rag Context Evidence/g, '문서 근거')
    .replace(/RCA Evidence Context/g, '답변 근거')
    .replace(/RCA 근거 문맥/g, '답변 근거')
    .replace(/Node Status 근거 시작/g, '노드 상태 근거 확인 시작')
    .replace(/Active Alerts 근거 시작/g, '경고 근거 확인 시작')
    .replace(/Restart Metric 근거 시작/g, '재시작 지표 확인 시작')
    .replace(/문서 Context 근거 시작/g, '문서 근거 확인 시작')
    .replace(/RCA 증거/g, '근거')
    .replace(/실행형 Tool Plan/g, '증거 수집 계획')
    .replace(/Tool Plan/g, '증거 수집 계획')
    .replace(/RCA Context/g, '답변 근거')
    .replace(/RCA\s*문맥/g, '답변 근거')
    .replace(/\bEvidence\b/g, '근거')
    .replace(/\bRag\b/g, '문서')
    .replace(/evidence\s+refs/g, '근거')
    .replace(/digest/g, '연결 정보')
    .replace(/post_answer/g, '답변 완료 후')
    .replace(/pre_answer/g, '답변 전')
    .replace(/plan_ready/g, '답변 준비');
};

const getStepActivity = (step: ProgressStep): string => {
  const summary = productProgressText(step.summary);

  if (step.status === 'failed') {
    return '오류 확인 필요';
  }

  if (step.id === GATEWAY_PREP_STEP_ID) {
    if (step.status === 'completed') {
      return '요청 준비 완료';
    }

    const completedCount = PREP_SUBTASKS.filter((item) =>
      step.detail?.includes(formatToolTitle(item.toolName)),
    ).length;
    const currentTask = PREP_SUBTASKS[Math.min(completedCount, PREP_SUBTASKS.length - 1)];

    return `${currentTask.label} 중`;
  }

  if (isResponseWaitStep(step) && step.status === 'running') {
    return getResponseWaitMessage(step.startedAt);
  }

  if (step.name === RUN_LOOP_STEP_ID) {
    return step.status === 'running' ? summary || '장기 실행 루프 유지 중' : '실행 루프 완료';
  }

  if (isAnswerStreamStep(step)) {
    return step.status === 'running' ? '답변을 화면에 표시하는 중입니다.' : '답변 표시 완료';
  }

  if (step.status === 'running') {
    return summary || '도구 응답을 기다리는 중입니다.';
  }

  return summary || '완료';
};

const getProgressSummary = (steps: ProgressStep[], active: boolean): string => {
  const firstStartedAt = steps[0]?.startedAt ?? Date.now();
  const lastEndedAt = steps.reduce(
    (latest, step) => Math.max(latest, step.endedAt ?? step.startedAt),
    firstStartedAt,
  );
  const elapsedMs = (active ? Date.now() : lastEndedAt) - firstStartedAt;
  const runningStep = steps.find((step) => step.status === 'running');

  if (active && runningStep) {
    return `${formatDuration(elapsedMs)} 동안 작업 중`;
  }

  return `${formatDuration(elapsedMs)} 동안 작업 완료`;
};

const getStepElapsed = (step: ProgressStep): string => formatDuration(getElapsedMs(step));

const expandProgressStep = (step: ProgressStep): ProgressStep[] => {
  return [step];
};

const getDisplaySteps = (steps: ProgressStep[]): ProgressStep[] =>
  steps
    .flatMap(expandProgressStep)
    .filter((step) => step.name !== RUN_LOOP_STEP_ID)
    .filter(
      (step) =>
        !(isAnswerStreamStep(step) && step.status === 'completed' && getElapsedMs(step) < 300),
    );

const getCurrentProgressStep = (steps: ProgressStep[]): ProgressStep =>
  steps.find((step) => step.status === 'running') ?? steps[steps.length - 1];

const ProgressTimeline: React.FC<{ active: boolean; steps: ProgressStep[] }> = ({
  active,
  steps,
}) => {
  const displaySteps = getDisplaySteps(steps);

  if (displaySteps.length === 0) {
    return null;
  }

  const currentStep = getCurrentProgressStep(displaySteps);

  return (
    <div className="komsco-ai__progress-wrap">
      <details className="komsco-ai__progress" key={active ? 'active' : 'complete'}>
        <summary className="komsco-ai__progress-summary" aria-live="polite">
          <span
            className={`komsco-ai__flow-pulse komsco-ai__flow-pulse--${currentStep.status}`}
            aria-hidden="true"
          />
          <span className="komsco-ai__progress-activity">{getStepActivity(currentStep)}</span>
          <span className="komsco-ai__progress-title">
            {getProgressSummary(displaySteps, active)}
          </span>
        </summary>
        <div className="komsco-ai__progress-list">
          {displaySteps.map((step) => {
            return (
              <div
                className={`komsco-ai__progress-step komsco-ai__progress-step--${step.status}`}
                key={step.id}
              >
                <span
                  className={`komsco-ai__progress-status komsco-ai__progress-status--${step.status}`}
                  aria-hidden="true"
                />
                <span className="komsco-ai__progress-step-copy">
                  <span className="komsco-ai__progress-step-title">
                    {productProgressText(step.title)}
                  </span>
                  <span className="komsco-ai__progress-step-separator" aria-hidden="true">
                    ·
                  </span>
                  <span className="komsco-ai__progress-step-activity">{getStepActivity(step)}</span>
                </span>
                <span className="komsco-ai__progress-step-meta">{getStepElapsed(step)}</span>
              </div>
            );
          })}
        </div>
      </details>
    </div>
  );
};

export default ProgressTimeline;
