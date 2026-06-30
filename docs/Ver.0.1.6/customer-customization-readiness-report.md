# Customer Customization Readiness Report

Generated: 2026-06-29 KST  
Workspace: `/home/kugnus/cywell/ocp-aiops_kugnus`  
Branch: `feat/v.0.1.6`

## 결론

현재 로컬 OKD 콘솔은 `http://127.0.0.1:9000/dashboards` 기준으로 복구되어 있고, bridge API health도 `200`이다.

다음에 콘솔 연결이 끊기면 브라우저를 먼저 다시 여는 것이 아니라 아래 한 줄로 복구한다.

```bash
task kugnus:dev:console:repair
```

이 명령은 기본적으로 브라우저를 열지 않는다. `9000` console bridge의 Kubernetes API health를 확인하고, stale token/죽은 bridge이면 현재 `oc` token으로 bridge container를 다시 만든다.

## OKD 콘솔 장애 원인

이번 장애의 원인은 URL path가 아니라 local console bridge 인증 상태였다.

| 항목 | 판단 |
| --- | --- |
| 정답 URL | `http://127.0.0.1:9000/dashboards` |
| 잘못 잡으면 안 되는 URL | `http://127.0.0.1:9000/dashboard` |
| `8080` | OKD console이 아니다. 다른 nginx/playbookstudio 쪽이라 `404 page not found`가 정상적으로 나올 수 있다. |
| 실제 장애 신호 | `http://127.0.0.1:9000/api/kubernetes/version` 이 `401 Unauthorized` |
| 원인 | `origin-console` bridge container가 오래된 `oc` bearer token으로 떠 있었다. |
| 복구 | `oc login` 갱신 후 console bridge container 재생성 |

## 다음 복구 절차

1. 브라우저를 반복해서 열지 않는다.
2. 먼저 health를 본다.

```bash
curl -ksS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:9000/api/kubernetes/version
```

3. `200`이면 이미 정상이다. 콘솔은 `http://127.0.0.1:9000/dashboards` 로 보면 된다.
4. `401`, `000`, `5xx`이면 아래 명령으로 복구한다.

```bash
task kugnus:dev:console:repair
```

5. `oc` login 자체가 만료되어 있으면 repair script가 web login URL을 출력한다. 이때도 기본값은 browser open skip이다. 명시적으로 열고 싶을 때만 아래를 쓴다.

```bash
task kugnus:dev:console:open
```

## 구현 반영

| 영역 | 반영 내용 |
| --- | --- |
| 콘솔 복구 | `scripts/open-okd-console.sh` 추가. `9000/api/kubernetes/version`이 `200`이 아니면 stale bridge를 재시작한다. |
| Taskfile | `kugnus:dev:console:repair`, `kugnus:dev:console:open` 추가. |
| Doctor | `scripts/kugnus-dev-doctor.sh`가 console HTML이 아니라 Kubernetes API health `200`을 본다. |
| LLM Wiki | console nav와 화면명을 `LLM Wiki`로 정리하고, customer RAG upload dashboard 관점으로 metric을 보강했다. |
| Upload dashboard | `RAG backend`, `Documents`, `Chunks`, `ACL`, `Raw content`, `Size`를 노출한다. raw content는 hidden/redacted posture를 유지한다. |
| Customer topology | Dashboard에 `고객 OCP -> 관측 신호 -> LLM Wiki/RAG -> LLM 경로 -> 정책/감사` 운영 토폴로지를 추가했다. |
| UI verifier | LLM Wiki route, upload dashboard, customer topology, no-overflow, header runtime timing까지 검증한다. |

## 고객맞춤 시스템 아이디어

현재 구현은 고객맞춤 MVP이다. 전용 topology backend나 고객별 지식 lifecycle API를 만든 척하지 않는다. 대신 지금 화면은 이미 있는 gateway/status/RAG 데이터를 이용해 고객 운영 흐름을 보여준다.

다음 제품화 아이디어는 아래 순서가 맞다.

| 우선순위 | 아이디어 | 제품 가치 |
| --- | --- | --- |
| P0 | 고객 LLM Wiki | 고객 runbook, 장애 이력, SOP, 벤더 문서, 변경 정책을 RAG 근거로 묶는다. |
| P0 | Namespace/tenant scope | 사용자의 OpenShift subject와 namespace 권한에 맞춰 문서와 근거를 제한한다. |
| P0 | Citation-first answer | 답변마다 어떤 고객 문서/cluster evidence를 썼는지 footer와 JSON trace로 남긴다. |
| P1 | Customer topology API | workload, namespace, route, operator, alert, RAG corpus, LLM 경로, policy/audit를 graph로 묶는다. |
| P1 | Incident memory | 현재 장애를 과거 고객 장애/업로드 문서와 매칭해서 재발/유사도/기존 조치 결과를 보여준다. |
| P1 | Evidence freshness | 오래된 runbook, 실패한 collector, 낮은 RAG hit quality를 운영자에게 경고한다. |
| P2 | Customer prompt pack | 고객별 말투가 아니라 고객별 SOP, 금지 명령, 승인 문구, 장애 분류 체계를 prompt pack으로 둔다. |
| P2 | Reindex/delete lifecycle | 업로드 문서의 reindex, delete, version, owner, ACL, chunk count를 대시보드에서 관리한다. |

## 검증 결과

| 명령 | 결과 |
| --- | --- |
| `task kugnus:dev:console:repair` | PASS. Browser open skipped, `9000/api/kubernetes/version -> 200`. |
| `task kugnus:dev:doctor` | PASS/WARN only. console API health check 포함. |
| `task kugnus:runtime:smoke` | PASS. report: `docs/Ver.0.1.6/runtime-smoke-report.json`. |
| `task kugnus:rag:upload:smoke` | PASS. report: `docs/Ver.0.1.4/rag-upload-smoke-report.json`. |
| `task kugnus:rag:file-upload:smoke` | PASS. PDF parser `pypdf`, 15 chunks, raw content not returned. |
| `task kugnus:rag:mock-customer:smoke` | PASS. MockPay PDF 4종 생성, pypdf parsing, pgvector 적재, marker 검색, stale 문서 기본 검색 제외 확인. |
| `task kugnus:rag:chat:smoke` | PASS. citation/evidence source visible. |

Mock customer PDF 생성은 repo 밖 `/home/kugnus/.local/share/kugnus-pdf-tools/.venv`에 설치한 open source `reportlab`을 사용한다. `pypdf` 추출과 `pypdfium2` 렌더링 이미지로 한글 깨짐이 없음을 확인했다.
| `task kugnus:scenario:verify` | PASS. 10/10 scenarios, negative controls passed. |
| `task kugnus:demo:preflight` | PASS/WARN only. no blockers after Lightspeed/ActionExecutor port-forward resume. |
| `corepack yarn typecheck` | PASS. |
| `corepack yarn build` | PASS. |
| `node --check scripts/verify-kugnus-ui.mjs` | PASS. |
| `task kugnus:ui:verify` | PASS. `ok: true`, `checked: 112`, `failed: []`. |

## 현재 열려 있어야 하는 로컬 포트

| 포트 | 역할 |
| --- | --- |
| `9000` | local OKD console bridge |
| `9001` | console plugin webpack dev server |
| `18080` | AIOps Gateway |
| `15432` | local pgvector/RAG DB |
| `18443` | OpenShift Lightspeed port-forward |
| `18083` | Action Executor port-forward |

## 운영 원칙

- 콘솔 문제는 `9000/dashboards`와 `9000/api/kubernetes/version` 기준으로 판단한다.
- `8080`의 `404`는 OKD console 장애 증거로 보지 않는다.
- 브라우저를 계속 여는 행동은 복구가 아니다.
- 회사 OCP/OKD에는 임의 `apply/delete/patch/scale/exec`를 하지 않는다.
- 고객 문서 raw content는 기본적으로 숨기고, chunk/citation/evidence preview 중심으로 보여준다.
