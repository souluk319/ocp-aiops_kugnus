import type * as React from 'react';
import {
  ANSWER_STREAM_STEP_ID,
  FAILED_TOOL_STATUSES,
  GATEWAY_PREP_STEP_ID,
  GATEWAY_PREP_TOOLS,
  RCA_CONTEXT_STEP_ID,
  RCA_PLAN_STEP_ID,
  RESPONSE_WAIT_STEP_ID,
  RUN_LOOP_STEP_ID,
} from './assistant.constants';
import { buildEvidenceFooter } from './assistant.evidence';
import {
  attachEvidenceFooterToLastAssistant,
  attachToolPlanToLastAssistant,
  markLastAssistantAnswerContract,
  markLastAssistantFallback,
  markLastAssistantSource,
} from './assistant.messageState';
import {
  formatToolTitle,
  normalizeToolName,
  rcaContextPhaseLabel,
} from './AssistantProgressTimeline';
import { createPendingAiopsStatus } from './assistant.aiopsRuntimeStatus';
import { buildToolPlanFooter } from './assistant.toolPlan';
import type {
  LightspeedStatusUpdate,
  Message,
  ProgressStatus,
  ProgressStep,
  RunStatusEvent,
  ToolStreamEvent,
  UiLanguage,
} from './assistant.types';
import {
  type AiopsRuntimeStatus,
  type ChatContextMessage,
  type ImageAttachment,
  streamChat,
} from '../services/aiGateway';

type AssistantStreamControllerOptions = {
  attachments: ImageAttachment[];
  conversationId?: string;
  enqueueAssistantText: (content: string) => void;
  flushAssistantTextQueueNow: () => void;
  markRunningProgressFailed: (summary: string) => void;
  pageContext: Record<string, unknown>;
  question: string;
  recentMessages: ChatContextMessage[];
  runId: string;
  setAiopsStatus: React.Dispatch<React.SetStateAction<AiopsRuntimeStatus | null>>;
  setConversationId: React.Dispatch<React.SetStateAction<string | undefined>>;
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>;
  signal: AbortSignal;
  uiLanguage: UiLanguage;
  updateLightspeedStatus: (updates: LightspeedStatusUpdate) => void;
  upsertProgressStep: (step: ProgressStep) => void;
};

const stringifyDetail = (value: unknown): string => {
  if (value === undefined || value === null) {
    return '';
  }

  if (typeof value === 'string') {
    return value;
  }

  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
};

const getToolDetail = (event: ToolStreamEvent): string => {
  if (event.detail) {
    return event.detail;
  }

  if (event.type === 'tool_call') {
    return stringifyDetail(event.args);
  }

  return stringifyDetail(event.result);
};

const getToolSummary = (event: ToolStreamEvent): string => {
  if (event.summary) {
    return event.summary;
  }

  if (event.type === 'tool_call') {
    return `${formatToolTitle(event.name)} 시작`;
  }

  return event.status ? `상태: ${event.status}` : '도구 실행 완료';
};

export const runAssistantStream = async ({
  attachments,
  conversationId,
  enqueueAssistantText,
  flushAssistantTextQueueNow,
  markRunningProgressFailed,
  pageContext,
  question,
  recentMessages,
  runId,
  setAiopsStatus,
  setConversationId,
  setMessages,
  signal,
  uiLanguage,
  updateLightspeedStatus,
  upsertProgressStep,
}: AssistantStreamControllerOptions): Promise<{
  finishAnswerStreamStep: () => void;
  runCompleted: boolean;
}> => {
  const activeStepIdsByName = new Map<string, string>();
  const activeStepStartedAt = new Map<string, number>();
  const gatewayPrepDetails: string[] = [];
  let gatewayPrepStartedAt: number | undefined;
  let responseWaitStartedAt: number | undefined;
  let responseWaitStepId: string | undefined;
  let responseWaitSequence = 0;
  let answerStreamStartedAt: number | undefined;
  let runLoopStartedAt: number | undefined;
  let runCompleted = false;
  let fallbackAnswerSeen = false;
  let clarificationAnswerSeen = false;
  let copilotReplySeen = false;
  let lightspeedStageSeen = false;
  let stepSequence = 0;

  const upsertGatewayPrepStep = (status: ProgressStatus) => {
    const now = Date.now();
    const startedAt = gatewayPrepStartedAt ?? now;

    gatewayPrepStartedAt = startedAt;
    upsertProgressStep({
      detail: gatewayPrepDetails.join('\n') || '사용자 권한과 요청 본문을 확인합니다.',
      elapsedMs: status === 'running' ? undefined : now - startedAt,
      endedAt: status === 'running' ? undefined : now,
      id: GATEWAY_PREP_STEP_ID,
      name: GATEWAY_PREP_STEP_ID,
      startedAt,
      status,
      summary: '사용자 권한 및 요청 확인',
      title: '요청 준비',
    });
  };

  const startResponseWaitStep = () => {
    if (responseWaitStartedAt) {
      return;
    }

    const now = Date.now();
    const id = `${RESPONSE_WAIT_STEP_ID}-${responseWaitSequence}`;

    responseWaitSequence += 1;
    responseWaitStartedAt = now;
    responseWaitStepId = id;
    upsertProgressStep({
      detail: 'Gateway 또는 모델이 다음 답변 조각을 준비하는 중입니다.',
      id,
      name: RESPONSE_WAIT_STEP_ID,
      startedAt: now,
      status: 'running',
      summary: '모델 답변 생성 중',
      title: '모델 답변 생성',
    });
  };

  const finishResponseWaitStep = (summary: string) => {
    if (!responseWaitStartedAt || !responseWaitStepId) {
      return;
    }

    const now = Date.now();
    upsertProgressStep({
      detail: summary,
      elapsedMs: now - responseWaitStartedAt,
      endedAt: now,
      id: responseWaitStepId,
      name: RESPONSE_WAIT_STEP_ID,
      startedAt: responseWaitStartedAt,
      status: 'completed',
      summary,
      title: '모델 답변 생성',
    });
    responseWaitStartedAt = undefined;
    responseWaitStepId = undefined;
  };

  const startAnswerStreamStep = () => {
    if (answerStreamStartedAt) {
      return;
    }

    const now = Date.now();
    answerStreamStartedAt = now;
    upsertProgressStep({
      detail: '답변 본문을 스트리밍으로 받아 대화창에 작성합니다.',
      id: ANSWER_STREAM_STEP_ID,
      name: ANSWER_STREAM_STEP_ID,
      startedAt: now,
      status: 'running',
      summary: '답변 작성 중',
      title: '답변 작성',
    });
  };

  const finishAnswerStreamStep = () => {
    if (!answerStreamStartedAt) {
      return;
    }

    const now = Date.now();
    upsertProgressStep({
      detail: '답변 본문 표시가 완료되었습니다.',
      elapsedMs: now - answerStreamStartedAt,
      endedAt: now,
      id: ANSWER_STREAM_STEP_ID,
      name: ANSWER_STREAM_STEP_ID,
      startedAt: answerStreamStartedAt,
      status: 'completed',
      summary: '답변 작성 완료',
      title: '답변 작성',
    });
    answerStreamStartedAt = undefined;
  };

  const handleGatewayPrepEvent = (event: ToolStreamEvent) => {
    upsertGatewayPrepStep('running');
    const normalizedName = normalizeToolName(event.name);

    if (event.type === 'tool_result') {
      gatewayPrepDetails.push(`${formatToolTitle(event.name)}: ${getToolSummary(event)}`);
    }

    if (
      event.type === 'tool_result' &&
      ((normalizedName === 'access_check' && attachments.length === 0) ||
        normalizedName === 'attachment_check')
    ) {
      upsertGatewayPrepStep('completed');
      startResponseWaitStep();
    }
  };

  const handleRunStatusEvent = (event: RunStatusEvent) => {
    const now = Date.now();
    const startedAt = runLoopStartedAt ?? now - (event.elapsedMs ?? 0);
    const failed = event.stage === 'failed';
    const completed = event.stage === 'completed';

    runLoopStartedAt = startedAt;
    if (completed) {
      runCompleted = true;
    }

    upsertProgressStep({
      detail: event.message,
      elapsedMs: completed || failed ? now - startedAt : undefined,
      endedAt: completed || failed ? now : undefined,
      id: `${RUN_LOOP_STEP_ID}-${event.runId ?? runId}`,
      name: RUN_LOOP_STEP_ID,
      startedAt,
      status: failed ? 'failed' : completed ? 'completed' : 'running',
      summary: event.message,
      title: '실행 루프',
    });

    if (event.stage === 'lightspeed' || event.stage === 'waiting') {
      startResponseWaitStep();
    }
  };

  const startProgressStep = (event: ToolStreamEvent) => {
    const now = Date.now();
    const id = String(event.id ?? `${event.name}-${stepSequence}`);

    stepSequence += 1;
    activeStepIdsByName.set(event.name, id);
    activeStepStartedAt.set(id, now);
    upsertProgressStep({
      detail: getToolDetail(event),
      id,
      name: event.name,
      serverName: event.serverName,
      startedAt: now,
      status: 'running',
      summary: getToolSummary(event),
      title: formatToolTitle(event.name),
    });
  };

  const finishProgressStep = (event: ToolStreamEvent) => {
    const now = Date.now();
    const id = String(
      event.id ?? activeStepIdsByName.get(event.name) ?? `${event.name}-${stepSequence}`,
    );
    const startedAt = activeStepStartedAt.get(id) ?? now;
    const failed = FAILED_TOOL_STATUSES.has((event.status ?? '').toLowerCase());

    if (!event.id && !activeStepIdsByName.has(event.name)) {
      stepSequence += 1;
    }

    activeStepIdsByName.delete(event.name);
    activeStepStartedAt.delete(id);
    upsertProgressStep({
      detail: getToolDetail(event),
      elapsedMs: now - startedAt,
      endedAt: now,
      id,
      name: event.name,
      serverName: event.serverName,
      startedAt,
      status: failed ? 'failed' : 'completed',
      summary: getToolSummary(event),
      title: formatToolTitle(event.name),
    });
  };

  for await (const event of streamChat(
    {
      attachments,
      conversationId,
      language: uiLanguage,
      message: question,
      pageContext,
      recentMessages,
      runId,
    },
    { signal },
  )) {
    if (event.type === 'run_status') {
      handleRunStatusEvent(event);
      if (event.stage === 'lightspeed') {
        lightspeedStageSeen = true;
        updateLightspeedStatus({
          fallbackActive: false,
          lastContextDigest: event.gatewayContextDigest,
          lastStatus: 'started',
          streamProbe: 'started',
        });
        setMessages((prev) => markLastAssistantSource(prev, 'ols', event.gatewayContextDigest));
      }
      if (
        event.stage === 'completed' &&
        !lightspeedStageSeen &&
        !fallbackAnswerSeen &&
        !clarificationAnswerSeen &&
        !copilotReplySeen
      ) {
        updateLightspeedStatus({
          fallbackActive: false,
          lastStatus: 'gateway_direct',
          streamProbe: 'not_used',
        });
        setMessages((prev) =>
          markLastAssistantSource(prev, 'gateway_direct', event.gatewayContextDigest),
        );
      }
    }

    if (event.type === 'tool_plan') {
      const now = Date.now();
      upsertProgressStep({
        detail:
          event.status === 'success'
            ? '질문을 조회 계획으로 분해하고 필요한 확인 순서를 고정했습니다.'
            : '질문별 조회 계획 검증에 실패했습니다. 답변은 부족한 확인 결과를 명시해야 합니다.',
        elapsedMs: 0,
        endedAt: now,
        id: RCA_PLAN_STEP_ID,
        name: 'runtime_tool_plan',
        startedAt: now,
        status: event.status === 'success' ? 'completed' : 'failed',
        summary: event.status === 'success' ? '조회 계획 생성' : '조회 계획 실패',
        title: '조회 계획',
      });
      setAiopsStatus((prev) => {
        const base = prev ?? createPendingAiopsStatus();
        const safetyContract =
          base.spec.safetyContract ?? createPendingAiopsStatus().spec.safetyContract!;
        return {
          ...base,
          spec: {
            ...base.spec,
            safetyContract: {
              ...safetyContract,
              toolPlanStatus: {
                latestRuntimePlan: event.plan,
                source: 'chat_stream',
                status: event.status === 'success' ? 'runtime_generated' : 'runtime_failed',
              },
            },
          },
        };
      });
      setMessages((prev) => attachToolPlanToLastAssistant(prev, buildToolPlanFooter(event.plan)));
    }

    if (event.type === 'rca_context') {
      const now = Date.now();
      const evidenceFooter = buildEvidenceFooter(event.context, event.evidenceStatus, event.status);
      upsertProgressStep({
        detail:
          event.phase === 'post_answer'
            ? '최종 답변의 확인 결과를 정리했습니다.'
            : '답변 전에 조회 결과와 추가 확인 항목을 정리했습니다.',
        elapsedMs: 0,
        endedAt: now,
        id: `${RCA_CONTEXT_STEP_ID}-${event.phase || 'unknown'}`,
        name: 'rca_context',
        startedAt: now,
        status: event.status === 'success' ? 'completed' : 'failed',
        summary:
          event.status === 'success' ? rcaContextPhaseLabel(event.phase) : '확인 결과 정리 실패',
        title: '확인 결과',
      });
      setMessages((prev) => attachEvidenceFooterToLastAssistant(prev, evidenceFooter));
      setAiopsStatus((prev) => {
        const base = prev ?? createPendingAiopsStatus();
        const safetyContract =
          base.spec.safetyContract ?? createPendingAiopsStatus().spec.safetyContract!;
        return {
          ...base,
          spec: {
            ...base.spec,
            safetyContract: {
              ...safetyContract,
              evidenceStatus: event.evidenceStatus ?? safetyContract.evidenceStatus,
              rcaContextStatus: {
                digest:
                  event.context && typeof event.context === 'object'
                    ? String(
                        (
                          (event.context as Record<string, unknown>).metadata as
                            | Record<string, unknown>
                            | undefined
                        )?.digest ?? '',
                      )
                    : '',
                latestContext: event.context,
                source: 'chat_stream',
                status: event.status === 'success' ? 'available' : 'failed',
              },
            },
          },
        };
      });
    }

    if (event.type === 'text') {
      if (event.answerContract) {
        setMessages((prev) => markLastAssistantAnswerContract(prev, event.answerContract));
      }
      if (event.fallbackAnswer || event.source === 'gateway_fallback') {
        fallbackAnswerSeen = true;
        setMessages((prev) => markLastAssistantFallback(prev, event.gatewayContextDigest));
        updateLightspeedStatus({
          fallbackActive: true,
          lastContextDigest: event.gatewayContextDigest,
          lastStatus: event.streamProbe ?? 'failed',
          streamProbe: event.streamProbe ?? 'failed',
        });
      } else if (event.source === 'copilot_clarification') {
        clarificationAnswerSeen = true;
        setMessages((prev) =>
          markLastAssistantSource(prev, 'copilot_clarification', event.gatewayContextDigest),
        );
      } else if (event.source === 'copilot_reply') {
        copilotReplySeen = true;
        setMessages((prev) =>
          markLastAssistantSource(prev, 'copilot_reply', event.gatewayContextDigest),
        );
      } else if (event.source === 'ols_required_notice') {
        setMessages((prev) =>
          markLastAssistantSource(prev, 'ols_unavailable', event.gatewayContextDigest),
        );
        updateLightspeedStatus({
          fallbackActive: false,
          lastContextDigest: event.gatewayContextDigest,
          lastStatus: event.streamProbe ?? 'failed',
          streamProbe: event.streamProbe ?? 'failed',
        });
      } else {
        setMessages((prev) =>
          markLastAssistantSource(
            prev,
            lightspeedStageSeen ? 'ols' : 'gateway_direct',
            event.gatewayContextDigest,
          ),
        );
      }
      if (event.content.trim()) {
        finishResponseWaitStep('답변 작성 시작');
        startAnswerStreamStep();
      }
      enqueueAssistantText(event.content);
    }

    if (event.type === 'tool_call') {
      if (GATEWAY_PREP_TOOLS.has(normalizeToolName(event.name))) {
        handleGatewayPrepEvent(event);
        continue;
      }

      finishResponseWaitStep(`${formatToolTitle(event.name)} 시작`);
      startProgressStep(event);
    }

    if (event.type === 'tool_result') {
      if (GATEWAY_PREP_TOOLS.has(normalizeToolName(event.name))) {
        handleGatewayPrepEvent(event);
        continue;
      }

      if (normalizeToolName(event.name) === 'lightspeed_stream' && event.fallbackAnswer) {
        fallbackAnswerSeen = true;
        updateLightspeedStatus({
          fallbackActive: true,
          lastContextDigest: event.gatewayContextDigest,
          lastError: event.detail ?? event.summary ?? '',
          lastStatus: 'failed',
          streamProbe: 'failed',
        });
      }

      finishResponseWaitStep(`${formatToolTitle(event.name)} 완료`);
      finishProgressStep(event);
    }

    if (event.type === 'error') {
      finishResponseWaitStep('오류 응답 수신');
      markRunningProgressFailed(event.message || 'AI response failed.');
      flushAssistantTextQueueNow();
      setMessages((prev) => [
        ...prev,
        {
          role: 'system',
          content: event.message || 'AI response failed.',
          timestamp: Date.now(),
        },
      ]);
    }

    if (event.type === 'end' && event.conversationId) {
      setConversationId(event.conversationId);
    }
  }

  finishResponseWaitStep('스트림 종료');
  return { finishAnswerStreamStep, runCompleted };
};
