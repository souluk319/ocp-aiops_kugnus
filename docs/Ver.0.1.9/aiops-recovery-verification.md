# Ver.0.1.9 AIOps 기능 복구 검수 기록

생성일: 2026-07-01
브랜치: `feat/v.0.1.9`

## 최신 재검수 상태

재검수 시각: 2026-07-01 09:29 KST

현재 결론:

- 제품 코드, UI, Gateway, RAG, Lightspeed, Action lifecycle, OLM 패키징 검증은 모두 통과했다.
- `task kugnus:aiops:verify`는 오프라인 3인 검수 gate이면서 최신 live report까지 읽어 `fullGoalCompletionProven=true`를 표시한다.
- 검수 gate는 `gateway-execution-reviewer`, `console-ux-reviewer`, `deploy-safety-reviewer` 3개 역할로 11개 검수를 통과했다.
- 챗봇의 조치 계획 답변은 `ActionProposal -> SealedActionPlan -> ApprovalDecision -> ExecutionRecord` 흐름과 `planDigest`를 직접 노출하도록 고정했다.
- 채팅에서 만든 조치 계획이 표준 `/v1/actions/approvals`와 `/v1/actions/execute` 경로로 이어져 `ExecutionRecord`를 남기는 테스트를 추가했다.
- 실행 완료 답변은 실제 normalized parameters, Plan, Approval, Execution, Mutation, Verification 상태를 노출하도록 고정했다.
- read-only 조치 요청은 ActionProposal / SealedActionPlan / ApprovalDecision / ExecutionRecord를 만들지 않고 조치 후보와 안전 경로만 안내하도록 고정했다.
- execute 모드 조치 계획 스트림은 `ToolPlan -> natural_action_plan -> 답변 -> run_status completed -> post_answer RCA Context -> DONE` 순서로 고정했다.
- Gateway는 `.env`를 읽은 상태로 실행되어 RAG가 `pgvector`, `embeddinggemma:latest`, `768`, `semantic-service`로 동작한다.
- Lightspeed 최종 답변은 fallback 없이 수신했다.
- 포트포워드 supervisor가 `PF_HEALTH_FAILURE_THRESHOLD=3`일 때 active stream 중 `18443`을 재시작해 `ConnectError`를 만들던 문제를 확인했고, 기본값을 `12`로 올렸다.

통과한 검증:

```bash
cd komsco-ai-console-plugin && yarn typecheck
node --check scripts/verify-kugnus-ui.mjs
python3 -m py_compile komsco-ai-gateway/komsco_ai_gateway/main.py komsco-ai-gateway/tests/test_health.py
komsco-ai-gateway/.venv/bin/python -m pytest komsco-ai-gateway/tests/test_health.py -k "runtime_tool_plan or rca_context or action_candidates or execute_mode_action_plan_response_has_post_answer_rca or unrestricted_executes_natural_scale_action or read_only_action_request_emits_post_answer_rca_context" -q
komsco-ai-gateway/.venv/bin/python -m pytest komsco-ai-gateway/tests/test_health.py -q -k "chat_action_plan_can_continue_through_standard_approval_api"
task kugnus:aiops:verify
task kugnus:scenario:verify
task kugnus:runtime:smoke
task kugnus:actions:live-verify
task kugnus:lightspeed:live-verify
task kugnus:aiops:live-verify
task kugnus:vpn:doctor
task kugnus:package
git diff --check
python3 - <<'PY'
from pathlib import Path
for path in [
    Path('komsco-ai-gateway/komsco_ai_gateway/main.py'),
    Path('komsco-ai-gateway/tests/test_health.py'),
    Path('docs/Ver.0.1.9/aiops-recovery-verification.md'),
]:
    assert path.read_text(encoding='utf-8').count('\ufffd') == 0
PY
```

결과:

- Console typecheck: PASS
- UI verifier syntax: PASS
- UI verifier: PASS, `122 checked / 0 failed`
- Python compile: PASS
- Gateway ToolPlan/RCA/Action 후보/답변 계약 테스트: PASS
- Gateway 채팅 계획 -> 표준 승인 API -> ExecutionRecord 연결 테스트: PASS, `1 passed`
- 3인 검수 gate: PASS, `reviewerCount=3`, `reviewPassCount=11`, `fullGoalCompletionProven=true`
- 요구사항 매핑: PASS
  - `three-review-agents`: PASS, `gateway-execution-reviewer`, `console-ux-reviewer`, `deploy-safety-reviewer`
  - `at-least-five-review-passes`: PASS, `passedChecks=11`
  - `aiops-answer-has-remediation-capability`: PASS
  - `console-shows-action-workflow`: PASS
  - `deployable-package-and-safe-ops`: PASS
- Scenario contract: PASS, `13 passed / 0 failed`
- Runtime smoke: PASS, `rag=collected`, `backend=pgvector`, `configured=True`, `results=3`
- Live action lifecycle: PASS, `11 passed / 0 failed`
- Live Lightspeed final response: PASS
  - `cluster-summary`: `olsText=44`, `fallback=0`, `streamProbe=succeeded`, `fallbackActive=false`
  - `official-evidence-rca`: `olsText=23`, `fallback=0`, `streamProbe=succeeded`, `fallbackActive=false`
- VPN doctor: PASS, `readyForStrictLightspeedGate=true`
- OLM package: PASS, `komsco-aiops-kugnus-operator.v0.1.9`
- Diff whitespace check: PASS
- 한글 replacement char check: PASS, `0`

현재 남은 주의점:

- 로컬 작업대는 `18080` Gateway, `18443` Lightspeed port-forward, `18083` Action Executor port-forward, `9000` Console bridge가 함께 살아 있어야 한다.
- 재부팅 후에는 이 로컬 프로세스들이 사라지므로 작업대 복구 절차를 다시 실행해야 한다.
- `.env` 없이 Gateway를 띄우면 RAG가 `not_configured`로 보일 수 있다. Gateway 재시작 시 반드시 `.env`를 포함해야 한다.

## 복구 목표

0.1.9의 목표는 문서 확장이 아니라 AIOps 실행 기능 복구다.

현재 화면은 단순 조회 챗봇이 아니라 다음 흐름을 한 화면에서 확인하도록 복구했다.

```text
사용자 질문
  -> Tool Plan 생성
    -> Evidence / RAG 수집
      -> RCA Context 생성
        -> Action Candidate 확인
          -> ActionProposal
            -> SealedActionPlan
              -> ApprovalDecision
                -> ExecutionRecord
```

실제 변경 실행은 승인 전에는 수행하지 않는다. 실행 경로는 사용자 토큰, SSAR, planDigest, approval status, evidence freshness, mutation flag, Action Executor 연결 상태를 통과해야 한다.

## 검수자별 확인

### 검수 1: UI / 사용자 흐름

확인한 문제:

- `승인 계획 만들기` 버튼이 실제 ActionProposal / SealedActionPlan 생성까지 이어지는지 증명해야 했다.
- 진행 단계가 답변 아래에 과도하게 펼쳐지거나 최종 답변을 중복 표시하면 안 된다.
- Tool Plan / RCA Context 상세 JSON은 기본 접힘 상태여야 한다.

반영:

- UI verifier가 `승인 계획 만들기` 버튼을 직접 클릭한다.
- 입력창에 concrete target이 들어가는지 확인한다.
- 전송 후 assistant 응답에 `typed AIOps action`, `Proposal:`, `Plan:`이 나타나는지 확인한다.
- 진행 단계 접힘 상태와 답변 중복 여부를 검증한다.

### 검수 2: Gateway / 실행 계약

확인한 문제:

- Action Candidate 버튼 프롬프트가 Pod 개수 조회 분기로 잘못 라우팅될 수 있었다.
- `ToolPlan`은 답변 장식이 아니라 실행 전 계약으로 유지되어야 한다.
- Action Executor grant는 plan digest만 맞아서는 부족하고 시간 창도 검증해야 한다.

반영:

- `action_proposal_only` 정책이면 Pod count fast path를 타지 않고 action plan 경로로 보낸다.
- 자연어 조치 요청이 `ActionProposal -> SealedActionPlan`으로 이어지는 테스트를 추가했다.
- ExecutionGrant의 `notBefore` / `expiresAt` 검증을 추가했다.

### 검수 3: 운영 / 배포 안전

확인한 문제:

- 0.1.9 참고용 PDF/PNG는 GitHub 업로드 대상에서 제외되어야 한다.
- 0.1.9 문서 폴더에는 현재 작업 산출물과 참고자료만 남겨야 한다.
- 회사 서버 배포는 별도 승인 단계로 남겨야 한다.

반영:

- `docs/Ver.0.1.9/JK_AIOps.png`
- `docs/Ver.0.1.9/KJK_-_AIOps_Semina_slides_01-10.pdf`

위 두 파일은 `.gitignore`에 명시했다.

0.1.9에 있던 미래 문서는 `docs/Ver.0.2.0/`으로 이동했다.

## 이전 라이브 검증 기록

아래 기록은 VPN과 회사 OCP API 경로가 살아 있던 시점의 과거 검증이다. 최신 상태는 위의 `최신 재검수 상태`가 기준이다.

### 전체 게이트

```bash
task kugnus:aiops:verify
```

결과: PASS

주요 확인:

- Console typecheck: PASS
- UI verifier: PASS
- Gateway pytest subset: PASS
- Scenario evaluation: 13/13 PASS
- Runtime smoke: PASS
- Live action lifecycle: PASS
- Live Lightspeed final response: PASS
- OLM package: PASS, `komsco-aiops-kugnus-operator.v0.1.9`

### UI 핵심 확인

```bash
task kugnus:ui:verify
```

결과: PASS

검증된 항목:

- 관제탑 화면 로딩
- Action Candidate 카드
- 승인/보류 버튼
- `승인 계획 만들기` 클릭
- 실제 ActionProposal / SealedActionPlan 생성
- Tool Plan / RCA Context 기본 접힘
- 사용자 질문/답변 시간 표시
- 진행 단계 표시
- 답변 중복 방지

### Gateway 핵심 확인

```bash
komsco-ai-gateway/.venv/bin/python -m pytest komsco-ai-gateway/tests/test_health.py -q -k "chat_stream_emits_rca_context_event or actions_api_rejects_stale_approval_and_blocks_disabled_execution or action_executor_rejects_missing_or_mismatched_execution_grant"
```

결과: PASS, `3 passed`

추가 targeted test:

```bash
komsco-ai-gateway/.venv/bin/python -m pytest komsco-ai-gateway/tests/test_health.py -q -k "action_candidate_pod_prompt or action_candidate_button_prompt or restart_variants or missing_openshift_api or action_executor_rejects_missing_or_mismatched_execution_grant"
```

결과: PASS, `8 passed`

### Scenario / RAG / Runtime

```bash
task kugnus:evaluate
```

결과: PASS, `13 passed / 0 failed`

```bash
task kugnus:runtime:smoke
```

결과: PASS

확인:

- `/healthz` HTTP 200
- `/v1/aiops/overview` HTTP 200
- RAG backend: `pgvector`
- RAG results: 3

### Live action lifecycle

```bash
task kugnus:actions:live-verify
```

결과: PASS

확인:

- action proposal 생성
- sealed action plan 생성
- 거절 후 승인이 차단됨
- 승인 후 거절이 차단됨
- 실제 mutation 실행은 수행하지 않음

### Live Lightspeed

```bash
task kugnus:lightspeed:live-verify
```

결과: PASS

확인:

- `cluster-summary`: OLS text 수신, fallback 0, errors 0
- `official-evidence-rca`: OLS text 수신, fallback 0, errors 0
- `streamProbe=succeeded`
- `fallbackActive=False`

## 남은 운영상 주의점

- 이번 검증은 로컬 개발 작업대 기준이다. 회사 서버에 0.1.9를 publish/install 하려면 별도 승인 후 진행해야 한다.
- 실제 mutation 실행은 의도적으로 하지 않았다. 검증은 승인/거절/차단 경로까지다.
- OLS는 `https://127.0.0.1:18443` 로컬 port-forward 경로를 사용한다. 포트가 열렸더라도 Gateway live verifier가 PASS해야 실제 답변 연결로 본다.
- 회사 서버에 설치된 CSV 버전과 로컬 패키지 버전은 별도 명령으로 확인해야 한다.

## protected artifact 처리

다음 protected artifact는 수정하지 않았다.

- `docs/version-progress-book.html`
- `docs/aiops-beginner-guide.html`
- `docs/Ver.0.1.8/aiops-llm-strategy-brief.html`
- Claude 생성 scenario JSON
