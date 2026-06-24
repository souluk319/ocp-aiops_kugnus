# Ver.0.1.1 Stage 1 Evidence/RCA Context Report

작성 기준일: 2026-06-25 KST  
브랜치: `feat/v.0.1.1`  
기준 문서: `reviewer-gate-protocol.md` Stage 1  
기준 head before report: `bb3060d`

## 목표

Stage 1의 목표는 질문/답변 단위로 수집 evidence, missing evidence, RCA Context JSON을 연결하는 것이다.

이 단계는 공식 회사 OCP에 무언가를 등록, 설치, 배포하는 작업이 아니다. 현재 검증 범위는 로컬 코드, 로컬 테스트, 로컬 콘솔 브리지, 산출물 정리에 한정한다.

## 현재 판단

Stage 1 구현은 현재 코드 기준으로 충족되어 있다.

- `EvidenceRecord`는 evidence reference event의 `result` payload로 생성된다.
- `RcaContext`는 deterministic contract로 생성된다.
- chat stream은 `rca_context` event를 내보내고 `LAST_RCA_CONTEXT`에 최신 context를 남긴다.
- evidence가 있으면 `evidence_refs`, `collectedRefs`, digest, context id가 연결된다.
- evidence가 없거나 실패한 evidence는 `missing` 또는 `failedRefs`로 분리된다.
- evidence가 없으면 confidence가 `insufficient_evidence`로 내려가며, 확인된 사실처럼 단정하지 않는다.
- runtime safety contract는 최신 RCA Context와 evidence status를 노출한다.

## 구현 근거

| 항목 | 파일 | 근거 |
| :--- | :--- | :--- |
| EvidenceRecord 생성 | `komsco-ai-gateway/komsco_ai_gateway/security.py` | `build_evidence_reference()` |
| evidence_ref stream event | `komsco-ai-gateway/komsco_ai_gateway/main.py` | `build_evidence_reference_events()` |
| RCA Context 생성 | `komsco-ai-gateway/komsco_ai_gateway/aiops_contracts.py` | `build_rca_context()` |
| Evidence 정규화 | `komsco-ai-gateway/komsco_ai_gateway/aiops_contracts.py` | `_normalize_evidence_ref()`, `_is_collected_evidence_ref()` |
| digest/context id 생성 | `komsco-ai-gateway/komsco_ai_gateway/aiops_contracts.py` | `metadata.digest`, `metadata.contextId` |
| chat run evidence 연결 | `komsco-ai-gateway/komsco_ai_gateway/main.py` | `evidence_refs_for_run()` |
| stream event 생성 | `komsco-ai-gateway/komsco_ai_gateway/main.py` | `build_rca_context_stream_event()` |
| stream event 발행 | `komsco-ai-gateway/komsco_ai_gateway/main.py` | `yield sse(rca_context_event)` |
| 최신 context status | `komsco-ai-gateway/komsco_ai_gateway/aiops_contracts.py` | `build_runtime_safety_contract()` |

## Acceptance Criteria

| 기준 | 측정 방법 | 결과 |
| :--- | :--- | :--- |
| `EvidenceRecord` runtime schema가 존재한다 | `scripts/verify-stage1-evidence-rca.py`가 `schemaVersion`, `evidenceId`, `contentDigest` 확인 | PASS |
| `RcaContext` runtime schema가 존재한다 | `build_rca_context()` 정적 확인 + smoke | PASS |
| `evidence_ref` event와 `rca_context.evidence_refs`가 연결된다 | JSON artifact의 `evidenceRefEvent.result.evidenceId`와 `rcaContextEvent.context.evidence_refs[0].evidenceId` 비교 | PASS |
| 모든 chat run에서 추적 가능한 `rca_context` event를 만들 수 있다 | verifier source wiring + targeted pytest의 `chat_stream_*rca_context*` tests | PASS |
| evidence가 있으면 `evidence_refs`와 `collectedRefs`가 연결된다 | JSON artifact에서 `contentDigest` link 확인 | PASS |
| evidence가 없으면 missing evidence와 uncertainty reason이 남는다 | JSON artifact에서 `missingRcaContextEvent.context.confidence.level == insufficient_evidence` 확인 | PASS |
| Pod/CronJob/Operator 계열 evidence가 schema 기반으로 분리된다 | targeted pytest의 Pod/CronJob/ClusterOperator evidence tests | PASS |
| Dashboard/assistant에서 collected/missing evidence가 구분된다 | verifier source wiring: `evidenceFooter`, `collectedRefs`, `missing`, collected/missing CSS 확인 | PASS |
| 증거 없는 원인 단정 방지 | verifier missing context + Stage 8 evaluator negative control | PASS |
| 공식 회사 OCP write 없음 | `oc apply`, publish, install, register 명령 미사용 | PASS |

## 로컬 검증 결과

```powershell
python -m py_compile komsco-ai-gateway/komsco_ai_gateway/aiops_contracts.py komsco-ai-gateway/komsco_ai_gateway/main.py komsco-ai-gateway/tests/test_health.py
```

결과: PASS

```powershell
python scripts/verify-stage1-evidence-rca.py --report docs/Ver.0.1.1/stage-1-evidence-rca-context-verification.json
```

결과: `PASS stage1 evidence/RCA verification: docs\Ver.0.1.1\stage-1-evidence-rca-context-verification.json`

검증 artifact:

- `docs/Ver.0.1.1/stage-1-evidence-rca-context-verification.json`

Artifact에서 확인한 것:

- Pod restart 질문이 `pod_restart_rca`로 분류됨
- `evidence_ref` stream event sample이 생성됨
- EvidenceRecord `schemaVersion`, `evidenceId`, `contentDigest`가 생성됨
- evidence_ref `evidenceId`가 `rca_context.evidence_refs[0].evidenceId`에 연결됨
- evidence_ref `contentDigest`가 `rca_context.evidence.collectedRefs[0].contentDigest`와 일치함
- `rca_context.metadata.contextId`와 `metadata.digest`가 생성됨
- evidence가 있을 때 `confidence.level == evidence_based`
- evidence가 없을 때 `confidence.level == insufficient_evidence`
- safety contract의 `evidenceStatus`에 OpenShift collected와 metric missing이 분리됨
- `main.py`에 `build_evidence_reference_events`, `build_rca_context_stream_event`, `yield sse(evidence_event)`, `yield sse(rca_context_event)` wiring이 존재함
- `AssistantLauncher.tsx`와 `assistant.css`에 collected/missing evidence footer wiring이 존재함

```powershell
$venv = Join-Path $env:TEMP 'ocp-aiops-pytest-venv\Scripts\python.exe'
& $venv -m pytest komsco-ai-gateway/tests/test_health.py -k "rca_context or build_evidence_reference_events_supports_gateway_preflight_source or chat_stream_emits_rca_context_event or chat_stream_unexpected_exception_emits_failed_rca_context_before_done or chat_stream_read_only_action_request_emits_post_answer_rca_context or chat_stream_pod_count_question_directly_investigates_cluster or build_cronjob_activity_evidence or build_pod_status_evidence or build_cluster_operator_status_evidence"
```

결과: `17 passed, 139 deselected, 2 warnings`

## 테스트 근거

`komsco-ai-gateway/tests/test_health.py`에서 확인된 Stage 1 관련 테스트:

- `test_rca_context_tracks_evidence_refs_and_missing_evidence`
- `test_rca_context_without_evidence_marks_uncertainty`
- `test_rca_context_treats_skipped_or_failed_refs_as_missing_not_collected`
- `test_rca_context_classifies_clusteroperator_detail_before_pod_status_name`
- `test_runtime_safety_contract_exposes_latest_rca_context`
- `test_chat_stream_emits_rca_context_event`
- `test_chat_stream_unexpected_exception_emits_failed_rca_context_before_done`
- `test_chat_stream_read_only_action_request_emits_post_answer_rca_context`
- `test_chat_stream_pod_count_question_directly_investigates_cluster`
- `test_build_evidence_reference_events_supports_gateway_preflight_source`
- `test_build_cronjob_activity_evidence_includes_schedule_env_and_recent_jobs`
- `test_build_cronjob_activity_evidence_matches_arbitrary_requested_interval`
- `test_build_pod_status_evidence_sorts_container_restart_counts`
- `test_build_pod_status_evidence_includes_requested_namespace_pod_list`
- `test_build_pod_status_evidence_marks_failed_pod_start_time`
- `test_build_pod_status_evidence_includes_unhealthy_spec_and_owner_chain`
- `test_build_cluster_operator_status_evidence_summarizes_operator_health`

Stage 8 evaluator와 연결되는 보조 근거:

- 명령: `python scripts/evaluate-aiops-scenarios.py --scenarios evals/aiops-scenarios --report docs/Ver.0.1.1/aiops-evaluation-report.json`
- artifact: `docs/Ver.0.1.1/aiops-evaluation-report.json`
- scenario ids: `pod-restart-rca`, `crashloopbackoff`, `imagepullbackoff`, `clusteroperator-degraded`, `cronjob-activity`
- negative control: evidence 없이 단정/실행하는 답변이 fail 처리되는지 확인

## 로컬 서버 상태 확인

사용자가 확인 중인 대상은 공식 회사 서버 배포물이 아니라 로컬 콘솔 브리지다.

| URL | 의미 | 확인 결과 |
| :--- | :--- | :--- |
| `http://localhost:9000/dashboards` | 로컬 OpenShift console bridge | HTTP 200 |
| `http://localhost:9001/plugin-manifest.json` | 로컬 plugin dev server | HTTP 200 |
| `http://localhost:18080/healthz` | 로컬 gateway | HTTP 200 |

이 확인은 로컬 HTTP 조회이며 회사 OCP에 리소스를 생성하지 않는다.

## 하지 않은 것

- `task kugnus:publish` 실행 안 함
- `task kugnus:install` 실행 안 함
- `task catalog:register`, `task catalog:deploy`, `task catalog:release` 실행 안 함
- `oc apply`, `oc create`, `oc patch`, `oc delete` 실행 안 함
- 공식 회사 OCP 공용 `komsco-ai-console-plugin`, `lightspeed-console-plugin`, 공용 namespace 변경 안 함
- `.env`, token, kubeconfig, password 커밋 안 함

## Reviewer Gate

| Reviewer | 관점 | 판정 | 메모 |
| :--- | :--- | :--- | :--- |
| A. Product/Requirements | Stage 1 요구사항과 산출물 추적성 | PASS | 1차 FAIL: EvidenceRecord/evidence_ref/chat stream/UI distinction/Gateway tests evidence 부족. Verifier, JSON artifact, targeted pytest 결과로 보강 후 재검수 PASS. |
| B. Backend/Safety | Gateway schema, evidence safety, read-only boundary | PASS | backend/safety blocking gap 없음 |
| C. Frontend/UX/Verification | stream/UI evidence 의미와 검증 신뢰성 | PASS | 1차 FAIL: inline smoke 재현성 부족, Stage 8 근거 모호. Verifier script, artifact, exact commands, targeted test names로 보강 후 재검수 PASS. |

## 남은 리스크

- `pytest` 전체 실행은 이 보고서 작성 시점의 필수 조건으로 다시 돌리지 않았다. 대신 Stage 1 관련 targeted pytest 17개를 통과시켰다.
- `task kugnus:stage1:verify` 경로는 Taskfile에 추가했지만, 현재 부모 PowerShell 세션에서는 `task`가 설치되어 있지 않고 WSL 호출이 `Wsl/Service/0x8007274c`로 실패했다. primary verification은 직접 Python 명령과 targeted pytest 결과로 둔다.
- 로컬 콘솔 브리지는 회사 API를 read/watch 형태로 조회할 수 있지만, 이 단계의 완료 조건은 회사 서버 write가 아니다.
