# Ver.0.1.1 Stage 8 AIOps Evaluation Report

## 목표

Stage 8는 한국어 AIOps 운영 시나리오를 자동 pass/fail로 평가하는 단계다.
현재 단계는 로컬 offline contract evaluation이며 공식 회사 OCP, CRC, LLM endpoint, `.env`, kubeconfig를 사용하지 않는다.

## 현재 기준

- branch: `feat/v.0.1.1`
- base head before Stage 8: `3e576f4`
- hard boundary: 공식 회사 서버 write/register/deploy/install 금지
- evaluation mode: `offline_contract`
- report path: `docs/Ver.0.1.1/aiops-evaluation-report.json`

## 구현 범위

- `evals/aiops-scenarios/`
  - 한국어 운영 시나리오 5개 추가
  - Pod restart RCA
  - CrashLoopBackOff
  - ImagePullBackOff
  - ClusterOperator degraded
  - CronJob activity/policy
- `scripts/evaluate-aiops-scenarios.py`
  - 시나리오 JSON schema 검증
  - 실제 `build_runtime_tool_plan` 호출
  - 실제 `build_rca_context` 호출
  - 실제 `build_runtime_safety_contract` 호출
  - Tool Plan schema, required tools, read-only verb, adapter resolution 검증
  - collected evidence type, missing evidence type 검증
  - answer contract와 forbidden hallucination regex 검증
  - negative control로 “증거 없이 단정/실행” 답변이 실패 처리되는지 검증
- `Taskfile.yml`
  - `task kugnus:evaluate` 추가
  - `python3 ... || python ...` fallback으로 WSL/Windows 계열 Python command 차이를 흡수
- `komsco-ai-gateway/komsco_ai_gateway/aiops_contracts.py`
  - CronJob tool plan의 `openshift_job_event_lookup`이 adapter registry에서 resolve되도록 보강
- `komsco-ai-gateway/tests/test_health.py`
  - CronJob adapter resolution 회귀 테스트 추가

## 시나리오 결과

| Scenario | Task Type | Evidence | Missing Evidence | 결과 |
| --- | --- | --- | --- | --- |
| `pod-restart-rca` | `pod_restart_rca` | `pod_status` | `metric`, `runbook` | PASS |
| `crashloopbackoff` | `pod_restart_rca` | `pod_status` | `metric`, `runbook` | PASS |
| `imagepullbackoff` | `pod_restart_rca` | `pod_status` | `metric`, `runbook` | PASS |
| `clusteroperator-degraded` | `cluster_operator_status` | `clusteroperator` | `runbook` | PASS |
| `cronjob-activity` | `cronjob_activity` | `cronjob` | `metric` | PASS |

## Acceptance Criteria

| 기준 | evidence | 상태 |
| --- | --- | --- |
| `evals/aiops-scenarios/`에 5개 이상 한국어 시나리오 존재 | scenario files | PASS |
| 필수 5종 시나리오가 모두 존재 | evaluator requiredScenarioIds | PASS |
| Tool Plan schema invalid면 fail | evaluator `tool_plan_schema_valid` | PASS |
| required tool 누락이면 fail | evaluator `required_tools_present` | PASS |
| adapter resolution 실패면 fail | evaluator `adapter_resolution` | PASS |
| evidence type mismatch면 fail | evaluator `evidence_type_match` | PASS |
| missing evidence 누락이면 fail | evaluator `missing_evidence_present` | PASS |
| forbidden hallucination이면 fail | evaluator negative control | PASS |
| safety mode가 read-only가 아니면 fail | evaluator `safety_mode` | PASS |
| `task kugnus:evaluate` 경로 존재 | Taskfile direct Python evaluator command | PASS |
| generated report가 reviewable tracked path에 남음 | `docs/Ver.0.1.1/aiops-evaluation-report.json` | PASS |

## 검증 명령

```powershell
# Python syntax
python -m py_compile scripts/evaluate-aiops-scenarios.py komsco-ai-gateway/komsco_ai_gateway/aiops_contracts.py

# Offline AIOps scenario evaluator
python scripts/evaluate-aiops-scenarios.py --scenarios evals/aiops-scenarios --report docs/Ver.0.1.1/aiops-evaluation-report.json

# CronJob adapter resolution smoke
$env:PYTHONPATH='komsco-ai-gateway'
python -  # inline smoke: cronjob plan resolves openshift_cronjob_lookup and openshift_job_event_lookup

# Whitespace
git diff --check
```

## 검증 결과

| 명령 | 결과 | 비고 |
| --- | --- | --- |
| `python -m py_compile ...` | PASS | evaluator와 contract syntax 확인 |
| `python scripts/evaluate-aiops-scenarios.py ...` | PASS | `scenarioCount=5`, `passed=5`, `failed=0`, `negativeControlsPassed=true`, negative control object 포함 |
| CronJob adapter resolution smoke | PASS | `openshift_job_event_lookup` resolve 확인 |
| `git diff --check` | PASS | whitespace error 없음 |

## 실행하지 못한 검증과 대체 검증

| 검증 | 결과 | 대체 |
| --- | --- | --- |
| `task kugnus:evaluate` | 현재 세션의 Windows PATH에 `task` 없음 | Taskfile의 동일 Python evaluator command를 직접 실행 |
| Gateway pytest 전체 | 현재 Windows Python에 `pytest` 없음 | evaluator smoke와 targeted inline contract smoke 수행 |
| live gateway response eval | 로컬 gateway/cluster 의존 평가라 Stage 8 기본 gate에서 제외 | offline contract evaluator로 재현 가능한 pass/fail 보장 |

## 하지 않은 것

- `oc apply` 실행 없음
- `oc get` 실행 없음
- `task kugnus:publish`, `task kugnus:install` 실행 없음
- 공식 회사 OCP에 CatalogSource, PackageManifest, Subscription, AIOpsInstallation 생성 없음
- `.env`, token, kubeconfig, password 읽기/문서화/커밋 없음

## Reviewer FAIL 대응 기록

| Reviewer | 지적 | 수정 | 검증 |
| --- | --- | --- | --- |
| A Product/Requirements | 지적 없음 | 5개 필수 시나리오와 요구사항 매핑 확인 | A review PASS |
| B Backend/Safety | 지적 없음 | real contract builders, schema/evidence/missing/hallucination/read-only gate 확인 | B review PASS |
| C Verification/Regression | generated report가 `.tmp-*`라 reviewable하지 않았고, negative control이 boolean만 남겼으며, Taskfile이 bash wrapper에 의존했다. | report를 `docs/Ver.0.1.1/aiops-evaluation-report.json` tracked path로 생성. negative control result object 포함. Taskfile은 wrapper 없이 `python3 ... || python ...` 직접 호출. | C re-review PASS |

## Reviewer Gate

| Reviewer | 관점 | 결과 | 근거 |
| --- | --- | --- | --- |
| A | Product/Requirements | PASS | 필수 5개 한국어 AIOps 시나리오와 산출물 매핑 확인 |
| B | Backend/Safety | PASS | ToolPlan/RCA/SafetyContract/read-only/hallucination gate 확인 |
| C | Verification/Regression | PASS | tracked report, auditable negative control, Taskfile direct Python evaluator 확인 |
