# Ver.0.1.1 Stage 6 Action Lifecycle UX Report

## 목표

Stage 6는 `proposal -> sealed plan -> approval -> execution` 흐름을 사용자가 이해할 수 있게 만들고, read-only 상태에서 왜 실행이 불가능한지 UI와 검증으로 고정하는 단계다.
현재 단계는 로컬 개발/검증 단계이며 공식 회사 OCP에 CatalogSource, PackageManifest, Subscription, AIOpsInstallation, ConsolePlugin, Service, Route를 생성하거나 변경하지 않는다.

## 현재 기준

- branch: `feat/v.0.1.1`
- base head before Stage 6: `4240aa7`
- runtime target: local console `http://localhost:9000/aiops-kugnus`
- local gateway: `http://127.0.0.1:18080`
- hard boundary: 공식 회사 서버 write/register/deploy/install 금지

## 구현 범위

- `komsco-ai-console-plugin/src/components/AssistantLauncher.tsx`
  - 우측 rail `승인·실행` 섹션에 Action Lifecycle stepper 추가
  - `Proposal`, `Sealed plan`, `Approval`, `Execution` 단계와 각 record count 표시
  - Action Executor configured 여부와 disabled reason 표시
  - read-only/mutation disabled 상태를 명시
  - execute guard가 `sealed plan digest`, `active approval`, `evidence freshness`, `SSAR`, `mutation flag`를 확인한다고 표시
  - pending runtime status를 `not configured`로 오인하지 않도록 `pending` 상태를 분리
  - approval record proof는 `approved`일 때만 `active approval`로 표시하고, 그 외 status는 실제 approval status로 표시
  - action record가 있을 때 stage label과 digest/approval proof를 같이 표시
- `komsco-ai-console-plugin/src/components/assistant.css`
  - rail 내부 lifecycle UI 스타일 추가
  - 좁은 rail에서 가로 스크롤이 생기지 않도록 lifecycle stepper를 2열로 접힘 처리
  - gate row가 rail 안에서 자연스럽게 줄바꿈되도록 정리
  - RCA Context digest 등 긴 rail code를 rail 너비 안에서 ellipsis 처리
- `scripts/verify-kugnus-ui.mjs`
  - lifecycle 단계 4개가 실제 fullscreen visible rail에 노출되는지 검증
  - `proposal|plan|approval|execution` 정확한 순서 검증
  - 안정적인 `data-*` 상태값으로 Action Executor, mutation flag, UI execution mode 검증
  - execute guard proof token과 expired/stale evidence failure 문구 검증
  - 우측 rail action lifecycle 가로 overflow가 없는지 visible rail 기준으로 검증
- `komsco-ai-gateway/tests/test_health.py`
  - expired evidence freshness failure가 `409`와 `create a new plan and approval` detail을 반환하는지 고정

## 하지 않은 것

- `oc apply` 실행 없음
- `helm install/upgrade` 실행 없음
- `task kugnus:publish`, `task kugnus:install`, `task catalog:register`, `task catalog:deploy` 실행 없음
- 공식 회사 OCP에 CatalogSource, PackageManifest, Subscription, AIOpsInstallation 생성 없음
- 기존 `komsco-ai-console-plugin`, `lightspeed-console-plugin`, `komsco-ai`, `komsco-ai-dev` 리소스 변경 없음
- `.env`, token, kubeconfig, password 읽기/문서화/커밋 없음

## Acceptance Criteria

| 기준 | evidence | 상태 |
| --- | --- | --- |
| proposal -> sealed plan -> approval -> execution 단계가 보임 | UI verifier lifecycle stage check | PASS |
| Action Executor 미구성 reason이 보임 | UI verifier disabled gate check | PASS |
| read-only에서 mutation execution disabled가 명확함 | UI verifier read-only gate check | PASS |
| execute guard가 digest/approval/freshness/SSAR/mutation flag를 설명함 | UI verifier proof check | PASS |
| evidence freshness 실패가 execution 차단 사유로 설명됨 | UI verifier proof check | PASS |
| read-only에서 mutation 실행 불가 backend 계약 유지 | targeted Gateway action pytest | PASS |
| approval 없이 execute 불가, stale approval 차단 | targeted Gateway action pytest | PASS |
| rail lifecycle UI 가로 overflow 없음 | UI verifier overflow check | PASS |
| 공식 회사 서버 write 없음 | 실행 명령 목록 | PASS |

## 검증 명령

```bash
# Frontend build
cd komsco-ai-console-plugin
corepack yarn build

# Gateway action lifecycle safety tests
python -m py_compile komsco-ai-gateway/komsco_ai_gateway/main.py
python -m pytest komsco-ai-gateway/tests/test_health.py -q -k "action_proposal_digest or action_access_review_request_is_derived_from_sealed_plan_target or sealed_action_plan_digest_excludes_mutable_status_and_digest_fields or execution_evidence_freshness_rejects_expired_evidence_refs or actions_api_rejects_stale_approval_and_blocks_disabled_execution or approved_different_subject_can_execute_with_product_access"

# Local UI verifier
KUGNUS_UI_URL=http://localhost:9000/aiops-kugnus node scripts/verify-kugnus-ui.mjs

# Git whitespace check
git diff --check
```

## 검증 결과

| 명령 | 결과 | 비고 |
| --- | --- | --- |
| `git diff --check` | PASS | whitespace error 없음 |
| `corepack yarn build` | PASS | vendor chunk size warning only |
| `python -m py_compile .../main.py` | PASS | Python 문법 확인 |
| targeted Gateway action pytest 6건 | PASS | `6 passed, 145 deselected` |
| `node scripts/verify-kugnus-ui.mjs` | PASS | `89 checked, 0 failed`, visible fullscreen rail 기준 |
| screenshot inspection | PASS | rail lifecycle overflow 0 확인 후 재검증 |

## Reviewer FAIL 대응 기록

| Reviewer | 지적 | 수정 | 검증 |
| --- | --- | --- | --- |
| A Visual/Product UX | lifecycle gate card 5개가 rail에서 과밀하고, pending runtime을 disabled처럼 보이며, overflow를 숨기는 방식이었다. | gate copy를 current blocker/proof 2줄 구조로 압축하고, runtime pending을 별도 상태로 분리했다. `overflow-x:hidden` 제거 후 긴 proof/code 줄임 처리. | UI verifier 89 checked 0 failed |
| B Security/Action Lifecycle | approval proof가 모든 approval을 `active approval`로 표시했다. freshness test가 409/detail을 고정하지 않았다. | `approved` 상태일 때만 `active approval` 표시. expired freshness test에서 `409`, `evidence is no longer fresh`, `create a new plan and approval` 확인. | targeted pytest 6 passed |
| C Verification/Regression | hidden rail textContent로 lifecycle 검증이 통과할 수 있었고, stage order와 overflow 검증이 약했다. | fullscreen visible rail에서 lifecycle rect, exact order, stable data attrs, overflow를 검증하도록 변경. | UI verifier 89 checked 0 failed |

## Local Runtime Evidence

- local console: `http://localhost:9000/aiops-kugnus` returned HTTP 200
- local gateway: `http://127.0.0.1:18080/healthz` returned `{"status":"ok"}`
- verifier screenshot:
  - `.tmp-aiops-kugnus-ui-verify-fullscreen.png`
  - `.tmp-aiops-kugnus-ui-verify-resize.png`
  - `.tmp-aiops-kugnus-ui-verify-evidence-footer.png`

## Reviewer Gate

| Reviewer | 관점 | 결과 | 근거 |
| --- | --- | --- | --- |
| A | Visual/Product UX | PASS | compact lifecycle summary, pending 분리, proof ID 축약, rail wrapping/truncation 확인 |
| B | Security/Action Lifecycle | PASS | `active approval` 오표시 제거, freshness 409/detail 고정 확인 |
| C | Verification/Regression | PASS | visible fullscreen rail 기준 exact order/data attrs/overflow 검증 확인 |
