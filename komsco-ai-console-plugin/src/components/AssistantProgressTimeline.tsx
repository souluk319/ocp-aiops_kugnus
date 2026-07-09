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
import type { ProgressStep, UiLanguage } from './assistant.types';

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

const formatDuration = (milliseconds: number, language: UiLanguage): string => {
  const safeMilliseconds = Math.max(0, milliseconds);

  if (safeMilliseconds < 1000) {
    return `${Math.max(1, Math.round(safeMilliseconds))}ms`;
  }

  const totalSeconds = Math.round(safeMilliseconds / 1000);

  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;

  if (language === 'en') {
    if (minutes > 0) {
      return `${minutes}m ${seconds}s`;
    }

    return `${seconds}s`;
  }

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
    return '확인 결과 정리 완료';
  }
  if (normalized === 'pre_answer' || normalized === 'plan_ready') {
    return '확인 결과 준비 완료';
  }
  return '확인 결과 정리 완료';
};

const translateProductProgressText = (text: string, language: UiLanguage): string => {
  if (language !== 'en') {
    return text;
  }

  const namespaceCountMatch = text.match(/^네임스페이스\s+(\d+)개\s+조회 완료$/);
  if (namespaceCountMatch) {
    return `Checked ${namespaceCountMatch[1]} namespaces`;
  }

  const namespaceCheckMatch = text.match(/^(.+?)\s+네임스페이스\s+확인$/);
  if (namespaceCheckMatch) {
    return `Checked ${namespaceCheckMatch[1]} namespace`;
  }

  const ragCountMatch = text.match(/^참고 문서\s+(\d+)건 확인$/);
  if (ragCountMatch) {
    return `Checked ${ragCountMatch[1]} document sources`;
  }

  return text
    .replace(/보안 경계 확인/g, 'Security boundary check')
    .replace(/Gateway credential boundary 확인/g, 'Gateway credential boundary checked')
    .replace(/사용자 주체 확인/g, 'Subject review')
    .replace(/주체 확인 완료/g, 'Subject review complete')
    .replace(/제품 접근 권한 확인/g, 'Product access review')
    .replace(/제품 접근 SelfSubjectAccessReview 확인/g, 'Product access review')
    .replace(/제품 접근 확인 완료/g, 'Product access confirmed')
    .replace(/제품 접근 확인/g, 'Product access confirmed')
    .replace(/정책 확인/g, 'Policy check')
    .replace(/확인 결과 collection allowed/g, 'Evidence collection allowed')
    .replace(/확인 결과 수집 허용/g, 'Evidence collection allowed')
    .replace(/조회\/증거 수집 허용/g, '조회 허용')
    .replace(/감사 레코드 기록/g, 'Audit record written')
    .replace(/감사 기록/g, 'Audit record')
    .replace(/조회 계획 검증 완료/g, '조회 계획 검증 완료')
    .replace(/실행형 Tool Plan 검증 완료/g, 'Evidence plan validation complete')
    .replace(/요청 준비 완료/g, 'Request ready')
    .replace(/요청 준비/g, 'Request setup')
    .replace(/사용자 권한 및 요청 확인/g, 'Access and request check')
    .replace(/사용자 권한과 요청 본문을 확인합니다\./g, 'Checking access and request body.')
    .replace(/접근 권한 확인/g, 'Access check')
    .replace(/이미지 첨부 확인/g, 'Attachment check')
    .replace(/모델 답변 생성 중/g, 'Generating model answer')
    .replace(/모델 답변 생성/g, 'Model answer generation')
    .replace(/모델 응답 대기/g, 'Waiting for model response')
    .replace(/네임스페이스 사용 여부 확인/g, 'Namespace usage check')
    .replace(/네임스페이스 사용 여부 조회/g, 'Namespace usage lookup')
    .replace(/네임스페이스 조회 완료/g, 'Namespace check complete')
    .replace(/대상 네임스페이스 및 서버 확인/g, 'Target namespace and server check')
    .replace(/테스트 Pod 생성 사전 확인/g, 'Test Pod creation preflight')
    .replace(/테스트 Pod 생성 Action Plan 사전 확인/g, 'Test Pod Action Plan preflight')
    .replace(/요청 해석 확인/g, 'Request interpretation')
    .replace(/요청 해석 완료/g, 'Request interpreted')
    .replace(/요청 확인 중/g, 'Checking request')
    .replace(/첨부 확인 중/g, 'Checking attachments')
    .replace(/답변 요청 중/g, 'Requesting answer')
    .replace(/질문 처리 중/g, 'Processing question')
    .replace(/답변 준비 중/g, 'Preparing answer')
    .replace(/답변 작성 시작/g, 'Answer writing started')
    .replace(/답변 작성 중/g, 'Writing answer')
    .replace(/답변 작성 완료/g, 'Answer written')
    .replace(/답변 작성/g, 'Answer writing')
    .replace(/답변 본문을 작성하는 중입니다\./g, 'Writing the answer.')
    .replace(/Evidence plan 검증 Complete/g, 'Evidence plan validation complete')
    .replace(/증거 수집 계획 검증 완료/g, 'Evidence plan validation complete')
    .replace(/증거 수집 계획 생성/g, 'Evidence plan created')
    .replace(/증거 수집 계획 실패/g, 'Evidence plan failed')
    .replace(/증거 수집 계획/g, 'Evidence plan')
    .replace(/조회 계획 생성/g, 'Evidence plan created')
    .replace(/조회 계획 실패/g, 'Evidence plan failed')
    .replace(/조회 계획/g, 'Evidence plan')
    .replace(/확인 결과 정리 완료/g, 'Answer context ready')
    .replace(/확인 결과 준비 완료/g, 'Answer context prepared')
    .replace(/확인 결과 정리 실패/g, 'Answer context failed')
    .replace(/답변 확인 결과/g, 'Answer context')
    .replace(/확인 결과/g, 'Answer context')
    .replace(/확인 결과 기록 완료/g, 'Evidence recorded')
    .replace(/확인 결과 기록 시작/g, 'Recording evidence')
    .replace(/확인 결과 기록/g, 'Evidence record')
    .replace(/참고 문서 확인 시작/g, 'Checking document sources')
    .replace(/참고 문서/g, 'Document sources')
    .replace(/경고 조회 결과 확인 시작/g, 'Checking alert data')
    .replace(/경고 조회 결과 수집 완료/g, 'Alert data collected')
    .replace(/경고 조회 결과/g, 'Alert data')
    .replace(/노드 상태 조회 결과 확인 시작/g, 'Checking node data')
    .replace(/노드 상태 조회 결과 수집 완료/g, 'Node data collected')
    .replace(/노드 상태 조회 결과/g, 'Node data')
    .replace(/재시작 지표 확인 시작/g, 'Checking restart metrics')
    .replace(/재시작 지표 수집 완료/g, 'Restart metrics collected')
    .replace(/재시작 지표 확인 결과/g, 'Restart metric data')
    .replace(/오류 확인 필요/g, 'Needs error review')
    .replace(/오류 응답 수신/g, 'Error response received')
    .replace(/장기 실행 루프 유지 중/g, 'Keeping the run loop alive')
    .replace(/실행 루프 완료/g, 'Run loop complete')
    .replace(/실행 루프/g, 'Run loop')
    .replace(/스트림 종료/g, 'Stream ended')
    .replace(/도구 응답을 기다리는 중입니다\./g, 'Waiting for tool response.')
    .replace(/시작/g, 'Started')
    .replace(/완료/g, 'Complete')
    .replace(/확인/g, 'check')
    .replace(/검증/g, 'validation')
    .replace(/조회/g, 'query')
    .replace(/허용/g, 'allowed')
    .replace(/기록/g, 'record');
};

const productProgressText = (value?: string, language: UiLanguage = 'ko'): string => {
  const text = String(value || '').trim();
  if (!text) {
    return '';
  }

  const phaseMatch = text.match(/^RCA\s*문맥\s*연결\s*:\s*([a-z_]+)/i);
  if (phaseMatch) {
    return translateProductProgressText(rcaContextPhaseLabel(phaseMatch[1]), language);
  }
  if (/^RCA\s*문맥\s*연결$/i.test(text)) {
    return translateProductProgressText('답변 확인 결과', language);
  }
  if (text === 'RCA 문맥 연결 실패') {
    return translateProductProgressText('확인 결과 정리 실패', language);
  }
  if (/^실제\s+.+로 요청 전달$/.test(text)) {
    return translateProductProgressText('모델에 확인 결과 전달', language);
  }
  const legacyRcaDigestText = ['RCA Context', 'digest와', ['evidence', 'refs'].join(' ')].join(' ');
  if (text.includes(legacyRcaDigestText)) {
    return language === 'en'
      ? 'Prepared the data used in the final answer.'
      : '최종 답변의 확인 결과를 정리했습니다.';
  }
  if (text.includes('수집/누락/실패 근거를 RCA Context로 연결')) {
    return language === 'en'
      ? 'Prepared collected evidence and follow-up checks before answering.'
      : '답변 전에 조회 결과와 추가 확인 항목을 정리했습니다.';
  }
  if (/^ev-[a-z0-9-]+\s+기록$/i.test(text)) {
    return translateProductProgressText('확인 결과 기록 완료', language);
  }
  if (text === '증거 참조 기록 시작') {
    return translateProductProgressText('확인 결과 기록 시작', language);
  }
  if (text === '증거 참조 기록') {
    return translateProductProgressText('확인 결과 기록', language);
  }
  if (text === 'Rag Context Evidence') {
    return translateProductProgressText('참고 문서', language);
  }
  if (text === 'oc read-only namespace inventory') {
    return translateProductProgressText('네임스페이스 사용 여부 조회', language);
  }
  if (text === 'namespace and server preflight') {
    return translateProductProgressText('대상 네임스페이스 및 서버 확인', language);
  }
  if (/^namespace\s+\d+개\s+read-only\s+조회$/i.test(text)) {
    const count = text.match(/^namespace\s+(\d+)개/i)?.[1] ?? '';
    return translateProductProgressText(
      count ? `네임스페이스 ${count}개 조회 완료` : '네임스페이스 조회 완료',
      language,
    );
  }
  if (/^intent\s+/i.test(text)) {
    return translateProductProgressText('요청 해석 완료', language);
  }
  if (text === 'RCA Context' || text === 'RCA Evidence Context' || text === 'RCA 근거 문맥') {
    return translateProductProgressText('답변 확인 결과', language);
  }
  if (text === 'Active Alerts Evidence') {
    return translateProductProgressText('경고 조회 결과', language);
  }
  if (text === 'Node Status Evidence') {
    return translateProductProgressText('노드 상태 조회 결과', language);
  }
  if (text === 'Restart Metric Evidence') {
    return translateProductProgressText('재시작 지표 확인 결과', language);
  }
  const ragSearchMatch = text.match(/^RAG\s+(?:근거|참고 문서)\s+(\d+)건\s+검색$/);
  if (ragSearchMatch) {
    return translateProductProgressText(`참고 문서 ${ragSearchMatch[1]}건 확인`, language);
  }

  const normalized = text
    .replace(/보안 경계 확인/g, 'Security boundary check')
    .replace(/Gateway credential boundary 확인/g, 'Gateway credential boundary checked')
    .replace(/사용자 주체 확인/g, 'Subject review')
    .replace(/제품 접근 권한 확인/g, 'Product access review')
    .replace(/제품 접근 SelfSubjectAccessReview 확인/g, 'Product access review')
    .replace(/정책 확인/g, 'Policy check')
    .replace(/조회\/증거 수집 허용/g, 'Evidence collection allowed')
    .replace(/감사 레코드 기록/g, 'Audit record written')
    .replace(/감사 기록/g, 'Audit record')
    .replace(/조회 계획 검증 완료/g, 'Evidence plan validation complete')
    .replace(/Node 상태 RCA 증거 수집 완료/g, '노드 상태 조회 결과 수집 완료')
    .replace(/Active Alert RCA 증거 수집 완료/g, '경고 조회 결과 수집 완료')
    .replace(/Restart metric RCA 증거 수집 완료/g, '재시작 지표 수집 완료')
    .replace(/oc read-only namespace inventory/gi, '네임스페이스 사용 여부 조회')
    .replace(/oc_test_pod_create_preflight/gi, '테스트 Pod 생성 사전 확인')
    .replace(/namespace and server preflight/gi, '대상 네임스페이스 및 서버 확인')
    .replace(/request intent classifier/gi, '요청 해석 확인')
    .replace(/Node Status Evidence 시작/g, '노드 상태 조회 결과 확인 시작')
    .replace(/Active Alerts Evidence 시작/g, '경고 조회 결과 확인 시작')
    .replace(/Restart Metric Evidence 시작/g, '재시작 지표 확인 시작')
    .replace(/Node 상태 근거 수집 완료/g, '노드 상태 조회 결과 수집 완료')
    .replace(/Active Alert 근거 수집 완료/g, '경고 조회 결과 수집 완료')
    .replace(/Restart metric 근거 수집 완료/g, '재시작 지표 수집 완료')
    .replace(/문서 근거 시작/g, '참고 문서 확인 시작')
    .replace(/Rag Context Evidence 시작/g, '참고 문서 확인 시작')
    .replace(/Rag Context Evidence/g, '참고 문서')
    .replace(/RCA Evidence Context/g, '답변 확인 결과')
    .replace(/RCA 근거 문맥/g, '답변 확인 결과')
    .replace(/Node Status 근거 시작/g, '노드 상태 조회 결과 확인 시작')
    .replace(/Active Alerts 근거 시작/g, '경고 조회 결과 확인 시작')
    .replace(/Restart Metric 근거 시작/g, '재시작 지표 확인 시작')
    .replace(/문서 Context 근거 시작/g, '참고 문서 확인 시작')
    .replace(/RCA 증거/g, '확인 결과')
    .replace(/실행형 Tool Plan/g, '조회 계획')
    .replace(/Tool Plan/g, '조회 계획')
    .replace(/RCA Context/g, '답변 확인 결과')
    .replace(/RCA\s*문맥/g, '답변 확인 결과')
    .replace(/\bEvidence\b/g, '확인 결과')
    .replace(/\bRag\b/g, '문서')
    .replace(/evidence\s+refs/g, '확인 결과')
    .replace(/digest/g, '연결 정보')
    .replace(/post_answer/g, '답변 완료 후')
    .replace(/pre_answer/g, '답변 전')
    .replace(/plan_ready/g, '답변 준비');

  return translateProductProgressText(normalized, language);
};

const getStepActivity = (step: ProgressStep, language: UiLanguage): string => {
  const summary = productProgressText(step.summary, language);

  if (step.status === 'failed') {
    return productProgressText('오류 확인 필요', language);
  }

  if (step.id === GATEWAY_PREP_STEP_ID) {
    if (step.status === 'completed') {
      return productProgressText('요청 준비 완료', language);
    }

    const completedCount = PREP_SUBTASKS.filter((item) =>
      step.detail?.includes(formatToolTitle(item.toolName)),
    ).length;
    const currentTask = PREP_SUBTASKS[Math.min(completedCount, PREP_SUBTASKS.length - 1)];

    return productProgressText(`${currentTask.label} 중`, language);
  }

  if (isResponseWaitStep(step) && step.status === 'running') {
    return productProgressText(getResponseWaitMessage(step.startedAt), language);
  }

  if (step.name === RUN_LOOP_STEP_ID) {
    return step.status === 'running'
      ? summary || productProgressText('장기 실행 루프 유지 중', language)
      : productProgressText('실행 루프 완료', language);
  }

  if (isAnswerStreamStep(step)) {
    return step.status === 'running'
      ? productProgressText('답변이 도착하는 대로 작성하고 있습니다.', language)
      : productProgressText('답변 작성 완료', language);
  }

  if (step.status === 'running') {
    return summary || productProgressText('도구 응답을 기다리는 중입니다.', language);
  }

  return summary || productProgressText('완료', language);
};

const getProgressSummary = (
  steps: ProgressStep[],
  active: boolean,
  language: UiLanguage,
): string => {
  const firstStartedAt = steps[0]?.startedAt ?? Date.now();
  const lastEndedAt = steps.reduce(
    (latest, step) => Math.max(latest, step.endedAt ?? step.startedAt),
    firstStartedAt,
  );
  const elapsedMs = (active ? Date.now() : lastEndedAt) - firstStartedAt;
  const runningStep = steps.find((step) => step.status === 'running');
  const duration = formatDuration(elapsedMs, language);

  if (active && runningStep) {
    return language === 'en' ? `Working for ${duration}` : `${duration} 동안 작업 중`;
  }

  return language === 'en' ? `Completed in ${duration}` : `${duration} 동안 작업 완료`;
};

const getStepElapsed = (step: ProgressStep, language: UiLanguage): string =>
  formatDuration(getElapsedMs(step), language);

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

const ProgressTimeline: React.FC<{
  active: boolean;
  language: UiLanguage;
  steps: ProgressStep[];
}> = ({
  active,
  language,
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
          <span className="komsco-ai__progress-activity">
            {getStepActivity(currentStep, language)}
          </span>
          <span className="komsco-ai__progress-title">
            {getProgressSummary(displaySteps, active, language)}
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
                    {productProgressText(step.title, language)}
                  </span>
                  <span className="komsco-ai__progress-step-separator" aria-hidden="true">
                    ·
                  </span>
                  <span className="komsco-ai__progress-step-activity">
                    {getStepActivity(step, language)}
                  </span>
                </span>
                <span className="komsco-ai__progress-step-meta">
                  {getStepElapsed(step, language)}
                </span>
              </div>
            );
          })}
        </div>
      </details>
    </div>
  );
};

export default ProgressTimeline;
