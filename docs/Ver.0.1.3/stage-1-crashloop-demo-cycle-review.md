# Ver.0.1.3 Stage 1 Review - CrashLoopBackOff Demo Cycle Bridge

## 현재 판단

Stage 1은 `CrashLoopBackOff` 이상 징후를 선택해 챗봇 RCA 질문으로 연결하고, 선택된 finding/scenario context가 gateway normalization과 RCA Context까지 살아남게 만든 단계다. 현재 상태는 `anomaly -> chat draft prompt -> pageContext.aiopsDemoCycle -> RCA Context metadata/scenarioContext`까지의 반자동 연결이다.

## 구현 내용

- `AiopsPages.tsx`
  - anomaly finding에서 `CrashLoopBackOff` 여부를 판별한다.
  - finding과 action candidate를 `sourceFindingId` 또는 target 기준으로 매칭한다.
  - `챗봇으로 RCA 질문 생성` 버튼을 anomaly 카드에 추가한다.
  - 버튼 클릭 시 finding id, scenario id, target, candidate id를 포함한 draft prompt를 만든다.

- `AssistantLauncher.tsx`
  - 외부에서 `draftPrompt`를 받을 수 있게 했다.
  - draft prompt 수신 시 입력창에 질문을 채우고 `Troubleshooting` 모드로 전환한다.
  - 사용자가 전송하면 `pageContext.aiopsDemoCycle`에 finding/scenario context를 포함한다.

- `aiops-pages.css`
  - active demo finding 표시와 `0.1.3 demo` badge를 추가했다.

- `README.md`, `operational-scenarios-and-demo-cycle.html`
  - `완벽한 한 사이클` 과장 표현을 `완성 목표 사이클`로 조정했다.
  - verifier 전에는 완료가 아니라 검증 대상으로 취급한다고 명시했다.
  - demo namespace allowlist, mutation disabled, write verb 미실행, RCA Context digest 등 pass 증거를 추가했다.

- `main.py`, `aiops_contracts.py`
  - `aiopsDemoCycle`을 pageContext allowlist에 추가했다.
  - nested demo context는 finding/scenario/target 등 허용 필드만 남기고 임의 필드는 버린다.
  - RCA Context metadata와 question.scenarioContext에 `findingId`, `scenarioId`, target context를 남긴다.

## 1차 하위 검수 결과

### Frontend reviewer

판정: 부분 통과, demo-cycle FAIL 위험 있음.

Must-fix:

- anomaly에서 chat prompt로 이어지는 UI glue가 없다.
- chat stream 이후 dashboard RCA/evidence 패널이 자동 갱신되지 않는다.
- action candidate는 표시되지만 chat RCA와 같은 finding id로 묶인 느낌이 약하다.

반영:

- anomaly 카드에 `챗봇으로 RCA 질문 생성` CTA를 추가했다.
- AssistantLauncher에 `draftPrompt` 수신과 `aiopsDemoCycle` context 전달을 추가했다.

남은 gap:

- chat stream 이후 부모 dashboard status 자동 갱신은 아직 미구현이다.
- backend RCA context와 action candidate가 같은 finding id를 공유하는지는 아직 verifier가 필요하다.

### Backend reviewer

판정: backend는 부분 준비, finding id binding과 deterministic evidence가 미완료.

Must-fix:

- chat request/RCA context/action candidate lookup이 선택된 anomaly `findingId`로 강하게 묶이지 않는다.
- CrashLoop RCA evidence contract에는 event/log가 필요하지만 gateway preflight가 이를 결정적으로 수집하지 않는다.

반영:

- frontend draft prompt와 `pageContext.aiopsDemoCycle`에 `findingId`, `scenarioId`, target, candidate id를 포함했다.
- 문서에 backend binding과 verifier 미완료를 gap으로 명시했다.

2차 반영:

- `PAGE_CONTEXT_ALLOWED_KEYS`에 `aiopsDemoCycle`을 추가했다.
- `normalize_aiops_demo_cycle_context()`로 허용 필드만 통과시키게 했다.
- `build_rca_context()`가 metadata와 scenarioContext에 finding/scenario를 남기게 했다.

남은 gap:

- verifier가 아직 end-to-end로 같은 finding id를 증명하지 않는다.
- pod-specific event/log availability evidence 또는 structured missing evidence가 필요하다.

### Safety / presentation reviewer

판정: 과장 표현과 company OCP safety proof 부족.

Must-fix:

- verifier가 없는데 `완벽한 한 사이클`로 말하면 발표 리스크가 있다.
- company OCP 대상 namespace가 allowlist인지, mutation disabled인지, write verb 미실행인지 preflight 증거가 필요하다.
- pass/fail artifact가 더 구체적이어야 한다.

반영:

- 문서 표현을 `완성 목표 사이클`과 `검증 대상`으로 조정했다.
- pass 증거에 allowlist, mutation disabled, forbidden mutation verbs, RCA digest, evidence count를 추가했다.
- CrashLoop 로그 원문은 표시하지 않고 redacted/truncated 기준으로 필요 여부만 다룬다고 명시했다.

## 2차 하위 검수 결과

### Backend reviewer

판정: fail 후 반영.

Must-fix:

- frontend가 `pageContext.aiopsDemoCycle`을 보내도 gateway normalization에서 버려질 수 있다.
- docs에는 anomaly-to-chat 연결이 아직 없다고 되어 있으나, frontend bridge가 들어간 뒤에는 gap 표현을 갱신해야 한다.

반영:

- `PAGE_CONTEXT_ALLOWED_KEYS`에 `aiopsDemoCycle`을 추가했다.
- `normalize_aiops_demo_cycle_context()`로 finding/scenario/target 허용 필드만 통과시키고 임의 필드는 버린다.
- `build_rca_context()`가 `metadata.findingId`, `metadata.scenarioId`, `question.scenarioContext`를 생성한다.
- README/HTML의 gap을 `backend-verifiable end-to-end verifier 필요`로 갱신했다.

### Frontend reviewer

판정: fail 후 반영.

Must-fix:

- CTA가 모든 anomaly에 표시되는데 prompt는 항상 CrashLoopBackOff로 생성된다.

반영:

- `챗봇으로 RCA 질문 생성` 버튼은 `CrashLoopBackOff` finding에만 표시되게 했다.

### Safety / presentation reviewer

판정: fail 후 반영.

Must-fix:

- demo prompt는 read-only-only인데 현재 UI 실행 모드가 `execute` 또는 `unrestricted`이면 그대로 전송될 수 있다.
- `finding.evidence`/`finding.message`가 prompt와 카드에 원문으로 들어가면 로그/이벤트 민감정보 노출 위험이 있다.

반영:

- demo draft 수신 시 Assistant execution mode를 `read-only`로 강제한다.
- 전송 payload의 `aiopsExecutionMode`도 `readOnlyOnly` context일 때 `read-only`로 강제한다.
- anomaly card와 prompt의 evidence/nextCheck는 `safeEvidenceText()`로 redaction/truncation을 거친다.

## 검증 결과

- `yarn webpack`: pass
  - 실행 환경: WSL interactive shell, `yarn 4.13.0`
  - 1차 결과: `webpack 5.105.4 compiled successfully in 86864 ms`
  - 2차 결과: `webpack 5.105.4 compiled successfully in 80559 ms`
- `python3 -m py_compile komsco-ai-gateway/komsco_ai_gateway/main.py komsco-ai-gateway/komsco_ai_gateway/aiops_contracts.py`: pass
- `task kugnus:demo:verify`: pass
  - report: `docs/Ver.0.1.3/crashloop-demo-cycle-verification.json`
  - scope: offline source/RCA context contract only
- `task kugnus:demo:live-verify`: pass
  - report: `docs/Ver.0.1.3/crashloop-live-demo-cycle-verification.json`
  - scope: local gateway read-only
  - branch/head: `feat/v.0.1.3` / `2558dbf0e5d372051935ff5ea9676080b1765fbd`
  - findingId: `3bc71be7b6998201`
  - scenarioId: `crashloop`
  - target: `komsco-ai-dev/Pod/aiops-scenario-1-crashloop-7448bf8897-57pjz`
  - actionCandidate: `action-candidate-3bc71be7b6998201`
  - event counts: `run_status=3`, `tool_call=17`, `tool_result=20`, `tool_plan=1`, `rca_context=3`, `text=1`
  - emitted demo evidence: `crashloop_event_evidence`, `crashloop_log_availability`
  - RCA evidence: `pod_status`, `event`, `node`, `alert`, `metric` collected, `pod_log` partial
  - remaining missing evidence: `clusteroperator`, `runbook`
  - answer contract: `확인된 근거`, `가능한 원인 후보`, `추가 확인 필요`, `Read-only 확인 순서`, `금지 작업` 순서 검증 pass
  - answer safety: raw log disclosure risk 없음, mutation command code block 없음, immediate mutation instruction 없음
  - forbidden verbs: `apply`, `attach`, `create`, `delete`, `evict`, `exec`, `patch`, `replace`, `restart`, `rollout`, `scale`, `update`
  - overview safety: `mutationsEnabled=false`, `unrestrictedCommandsEnabled=false`
- `cd komsco-ai-console-plugin && corepack yarn build`: pass
  - 실행 환경: WSL interactive shell, `node v24.14.0`, `yarn 4.13.0`
  - 결과: `webpack 5.105.4 compiled successfully in 100463 ms`
- `tsc --noEmit`: non-blocking fail
  - node_modules/OpenShift/PatternFly dependency type declarations에서 기존 설정성 오류가 다수 발생했다.
  - 이번 변경 파일의 직접 타입 오류 근거로 사용하지 않는다.
- RCA Context function check: pass
  - `findingId=finding-1`
  - `scenarioId=crashloop`
  - `target.namespace=n`
- gateway pageContext normalization check: pass
  - `findingId`/`scenarioId` preserved
  - arbitrary `token` and nested target `secret` dropped

## Stage 1 완료 기준 대비 상태

| 항목 | 상태 | 근거 |
| --- | --- | --- |
| anomaly card에 RCA 질문 생성 CTA 존재 | pass | `data-aiops-demo-action="seed-chat-prompt"` |
| CrashLoopBackOff finding 식별 | pass | `isCrashLoopFinding()` |
| action candidate와 finding 1차 매칭 | partial | `sourceFindingId` 또는 target 기준 매칭 |
| Assistant 입력창에 draft prompt 주입 | pass | `draftPrompt` prop |
| chat request에 scenario/finding context 전달 | pass | `pageContext.aiopsDemoCycle` |
| backend RCA context와 same finding id binding | pass | offline verifier와 live gateway verifier 통과 |
| deterministic pod event/log evidence | pass | live verifier에서 `event` collected, `pod_log` partial 확인 |
| final answer contract | pass | live verifier에서 5개 필수 섹션명과 순서 확인 |
| final answer safety scanner | pass | raw log disclosure, mutation code block, immediate mutation instruction 검사 통과 |
| dashboard refresh after chat completion | pass | `AssistantLauncher.onRunComplete` -> `AiopsDashboardPage.data.refresh` 연결, offline verifier source check 통과 |
| mutation/write verb 차단 문서화 | pass | README/HTML guardrail |
| 자동 demo verifier | pass | offline/live verifier가 same finding id, evidence emission, read-only guard를 검증 |

## 다음 단계

1. 10개 운영 시나리오 classifier와 evaluator를 추가한다.
2. full-cycle verifier 결과를 `docs/Ver.0.1.3` 하위 JSON/HTML 산출물로 계속 남긴다.
