# v0.2.5 AIOps for OCP Reference Porting Plan

## 목적

상위 엔지니어가 공유한 `cywell-rnd-team/aiops-ocp`를 정답지로 보고, 현재 repo에 `AIOps for OCP` 제품 경험을 안전하게 이식한다.

이번 작업의 핵심은 "우리 것을 조금 고치는 것"이 아니다. 정답지의 구조를 기준으로 우리 repo를 재정렬하되, 기존 OLM/회사 배포/보호 문서를 망가뜨리지 않는 것이다.

## 현재 확인한 사실

| 항목 | 값 |
| --- | --- |
| 정답지 로컬 경로 | `/home/kugnus/cywell/AIOps-Ref/aiops-ocp` |
| 정답지 브랜치 | `dev` |
| 정답지 HEAD | `a7bd16b` |
| 정답지 포털 package | `komsco-ai-portal` |
| 정답지 포털 dev URL | `http://localhost:5173/` |
| 정답지 Gateway 기본 URL | `http://127.0.0.1:18080` |
| 사용자가 확인한 Gateway URL | `http://127.0.0.1:18081/healthz` |
| 현재 확인 상태 | 포털 `5173`은 응답, `18081` Gateway는 현재 내려간 상태 |
| 제품명 기준 | `AIOps for OCP` |

주의: 직전 로컬 서버 정리 요청에서 AIOps 계열 process를 내리는 과정이 있었으므로, 참조 Gateway가 내려가 있어도 코드 문제로 단정하지 않는다. 필요하면 정답지 repo에서 `task be:dev` 또는 해당 uvicorn 명령으로 다시 띄워 확인한다.

## 안전 원칙

1. `dev`는 배포 기준점으로 보호한다.
2. 모든 이식은 `feature/v0.2.5-aiops-for-ocp-port`에서 한다.
3. 정답지 코드는 통째 덮어쓰지 않는다.
4. 먼저 inventory를 작성하고, 그 다음 작은 커밋으로 이식한다.
5. 포털, Gateway, action logic, console plugin, 배포 산출물을 한 커밋에 섞지 않는다.
6. 회사 서버 배포는 이번 범위 밖이다.
7. 테스트가 없는 "완료" 보고를 금지한다.

## 이식 Lane

### Lane 1: Reference Inventory

목표: 정답지와 우리 repo의 차이를 파일/계약 단위로 분류한다.

산출물:

```text
docs/Ver.0.2.5/aiops-for-ocp-reference-inventory.md
```

분류 기준:

| 분류 | 의미 |
| --- | --- |
| `copy` | 거의 그대로 가져와도 되는 새 package 또는 독립 산출물 |
| `merge` | 우리 구현과 합쳐야 하는 로직 |
| `rename` | 제품명/라벨만 바꿀 것 |
| `defer` | 배포/OLM처럼 나중에 별도 검토할 것 |
| `do not port` | 정답지에도 있지만 우리 repo에는 가져오지 않을 것 |

우선 확인 파일:

```text
/home/kugnus/cywell/AIOps-Ref/aiops-ocp/README.md
/home/kugnus/cywell/AIOps-Ref/aiops-ocp/Taskfile.yml
/home/kugnus/cywell/AIOps-Ref/aiops-ocp/komsco-ai-portal/*
/home/kugnus/cywell/AIOps-Ref/aiops-ocp/komsco-ai-gateway/komsco_ai_gateway/main.py
/home/kugnus/cywell/AIOps-Ref/aiops-ocp/komsco-ai-gateway/komsco_ai_gateway/aiops_core.py
/home/kugnus/cywell/AIOps-Ref/aiops-ocp/komsco-ai-gateway/komsco_ai_gateway/action_executor.py
/home/kugnus/cywell/AIOps-Ref/aiops-ocp/scripts/dev-gateway-lightspeed.sh
```

완료 기준:

- 어떤 파일을 그대로 가져오고, 어떤 파일은 병합하고, 어떤 파일은 보류할지 문서에 있다.
- `AIOps for OCP` 명칭 반영 대상이 목록화되어 있다.
- Gateway API shape 차이가 표로 있다.

### Lane 2: Portal Package Port

목표: 정답지의 `komsco-ai-portal`을 우리 repo에 별도 package로 가져온다.

대상:

```text
komsco-ai-portal/package.json
komsco-ai-portal/package-lock.json
komsco-ai-portal/tsconfig.json
komsco-ai-portal/vite.config.ts
komsco-ai-portal/index.html
komsco-ai-portal/src/App.tsx
komsco-ai-portal/src/api.ts
komsco-ai-portal/src/main.tsx
komsco-ai-portal/src/styles.css
komsco-ai-portal/src/types.ts
komsco-ai-portal/README.md
```

이식 방식:

- 우리 repo에 `komsco-ai-portal/`이 없다면 정답지 package를 새 package로 추가한다.
- 기존 `komsco-ai-console-plugin/src/standalone`은 즉시 삭제하지 않는다.
- 포털이 안정화되면 standalone을 deprecated 후보로 문서화한다.
- package 내부 import/path만 조정하고, 기능 변경은 하지 않는다.

검증:

```bash
cd komsco-ai-portal
npm install
npm run build
```

완료 기준:

- `komsco-ai-portal`이 build 된다.
- Gateway가 없어도 demo fallback으로 화면이 렌더링 가능하다.
- 화면 기본 명칭이 `AIOps for OCP`이다.

### Lane 3: Local Dev Task And Proxy Contract

목표: 포털을 로컬에서 같은 방식으로 띄울 수 있게 한다.

대상:

```text
Taskfile.yml
README.md
```

반영:

- `task portal:dev`
- `task portal:build`
- `AIOPS_GATEWAY_ORIGIN`
- `AIOPS_DEV_OPENSHIFT_TOKEN`
- `/v1/*` Vite proxy

검증:

```bash
task portal:build
```

브라우저 확인은 사용자의 동의를 받고 수행한다. WSL fan/CPU 부하가 있을 수 있다.

### Lane 4: Gateway API Contract Port

목표: 포털이 기대하는 `/v1` API를 우리 Gateway가 안정적으로 제공하게 한다.

우선 API:

```text
GET /healthz
GET /v1/cluster/summary
GET /v1/aiops/status
GET /v1/aiops/events
```

후속 API:

```text
GET /v1/actions/registry
POST /v1/actions/proposals
POST /v1/actions/plans
POST /v1/actions/approvals
POST /v1/actions/execute
GET /v1/runbooks/registry
GET /v1/evidence
GET /v1/workflows/{run_id}
```

이식 방식:

- 우리 Gateway에 이미 있는 endpoint는 shape 차이만 비교한다.
- 없는 endpoint만 추가한다.
- 기존 console plugin proxy 경로는 깨지지 않게 유지한다.
- 포털 전용 API와 콘솔 플러그인 API가 같은 데이터 타입을 공유하게 한다.

검증:

```bash
python3 -m py_compile komsco-ai-gateway/komsco_ai_gateway/main.py
komsco-ai-gateway/.venv/bin/python -m pytest -q komsco-ai-gateway/tests/test_health.py -k "cluster_summary or aiops_status or aiops_events or action"
curl -sS http://127.0.0.1:18081/healthz
curl -sS http://127.0.0.1:18081/v1/cluster/summary
curl -sS http://127.0.0.1:18081/v1/aiops/status
curl -sS http://127.0.0.1:18081/v1/aiops/events
```

### Lane 5: Agentic Action Logic Port

목표: 정답지의 실질적 로직 강점을 우리 Gateway/action engine에 흡수한다.

비교 대상:

```text
parse_natural_action_intent
recent_natural_action_request
resolve_natural_action_target
create_natural_action_plan
execute_natural_action_plan_result
ACTION_REGISTRY_ENTRIES
RUNBOOK_REGISTRY_ENTRIES
build_mutation_request
execute_typed_action_plan
classify_request_policy
```

우선 반영:

- scale/restart/rollback/evict/HPA intent
- 3/4/5턴 `진행해` followup 복원
- ambiguous mutation 차단
- read-only RCA와 mutation record 분리
- unrestricted mode auto approval/execution
- execution verification result를 event/status feed에 연결

검증:

```bash
komsco-ai-gateway/.venv/bin/python -m pytest -q komsco-ai-gateway/tests/test_health.py -k "agentic_action or natural_action or followup or unrestricted or rollback or hpa or eviction"
```

### Lane 6: Console Plugin And Launcher Integration

목표: OpenShift 상단 Application Launcher에서 `AIOps for OCP` 독립 포털로 연결한다.

반영:

- 제품명: `AIOps for OCP`
- 내부 콘솔 좌측 메뉴는 기존 AIOps 운영 화면 유지 여부를 별도 판단
- Application Launcher는 독립 포털 URL로 연결
- 기존 FAB/assistant overlay는 콘솔 내부 보조 경험으로 유지

주의:

- 이번 lane에서도 회사 서버 배포는 하지 않는다.
- Route, Caddy, DNS, TLS는 배포 계약 문서에서 별도 처리한다.

### Lane 7: Decommission Or Reconcile Existing Standalone

목표: 기존 `komsco-ai-console-plugin/src/standalone`과 새 `komsco-ai-portal`의 역할을 정리한다.

선택지:

| 선택 | 설명 |
| --- | --- |
| Portal wins | `komsco-ai-portal`을 공식 독립페이지로 삼고 기존 standalone은 폐기 후보 |
| Bridge temporarily | 기존 standalone은 유지하되 launcher는 portal로 연결 |
| Merge later | portal 안정화 후 standalone에서 필요한 코드만 이동 |

기본 선택은 `Portal wins`이다. 단, 삭제는 별도 커밋에서만 한다.

## Branch / Commit Strategy

브랜치는 이미 아래로 분리했다.

```text
feature/v0.2.5-aiops-for-ocp-port
```

권장 커밋 단위:

```text
docs: add v0.2.5 AIOps for OCP porting plan
docs: add v0.2.5 reference inventory
feat(portal): add AIOps for OCP portal package
build(portal): add portal task and build wiring
feat(gateway): align AIOps portal API contract
feat(gateway): port agentic action lifecycle gaps
feat(console): point launcher to AIOps for OCP portal
docs: record v0.2.5 verification results
```

절대 금지:

```text
git add .
git restore .
git reset --hard
전체 폴더 덮어쓰기
배포 산출물과 UI/로직을 한 커밋에 섞기
```

## Acceptance Criteria

| ID | Pass/Fail 기준 | 측정 방법 | Evidence |
| --- | --- | --- | --- |
| V025-01 | `docs/Ver.0.2.5`에 정답지 이식 계획과 inventory가 있다. | file check | docs |
| V025-02 | `komsco-ai-portal` package가 추가되고 build 된다. | `npm run build` | build output |
| V025-03 | 포털 기본 브랜드가 `AIOps for OCP`이다. | source grep / browser | App text |
| V025-04 | 포털이 `/v1/cluster/summary`, `/v1/aiops/status`, `/v1/aiops/events`를 호출한다. | source grep / network | api.ts |
| V025-05 | Gateway가 포털 필수 API를 제공한다. | curl / pytest | API response |
| V025-06 | Gateway가 unavailable이면 포털이 reviewable demo data를 표시한다. | local browser/build | UI evidence |
| V025-07 | natural action followup, ambiguous mutation, read-only RCA, unrestricted execution이 테스트된다. | pytest | test output |
| V025-08 | Application Launcher의 제품명은 `AIOps for OCP`로 통일된다. | source grep | plugin/OLM config |
| V025-09 | 회사 서버 배포 리소스는 이번 작업에서 변경하지 않는다. | `git diff --name-only` | diff check |
| V025-10 | protected artifacts와 `evals/aiops-scenarios/*`는 수정하지 않는다. | git status | diff check |

## Test Plan

문서:

```bash
git diff --check
rg -n "AIOps for OCP|komsco-ai-portal|/v1/aiops/events|V025" docs/Ver.0.2.5
```

포털:

```bash
cd komsco-ai-portal
npm install
npm run build
```

Gateway:

```bash
python3 -m py_compile komsco-ai-gateway/komsco_ai_gateway/main.py komsco-ai-gateway/komsco_ai_gateway/aiops_core.py komsco-ai-gateway/komsco_ai_gateway/action_executor.py
komsco-ai-gateway/.venv/bin/python -m pytest -q komsco-ai-gateway/tests/test_health.py -k "aiops_status or aiops_events or cluster_summary or agentic_action or natural_action or followup"
```

로컬 실행:

```bash
task be:dev
task portal:dev
curl -sS http://127.0.0.1:18081/healthz
curl -sS http://127.0.0.1:18081/v1/cluster/summary
curl -sS http://127.0.0.1:18081/v1/aiops/status
curl -sS http://127.0.0.1:18081/v1/aiops/events
```

주의: `task be:dev`는 OpenShift/Lightspeed port-forward를 만들 수 있으므로 회사 서버 대상 여부를 먼저 확인한다.

## 완료 판단

v0.2.5 완료는 아래가 모두 참일 때만 선언한다.

```text
1. AIOps for OCP 포털이 우리 repo에서 build 된다.
2. Gateway 필수 API가 포털과 맞는다.
3. 자연어 action lifecycle 핵심 테스트가 통과한다.
4. launcher/문서/브랜드 명칭이 AIOps for OCP로 정렬된다.
5. 회사 서버 배포 산출물은 건드리지 않았다.
```

이 작업의 목적은 빠르게 화면 하나를 띄우는 것이 아니라, 상위 엔지니어가 준 정답지를 우리 제품의 새 기준점으로 만드는 것이다.

