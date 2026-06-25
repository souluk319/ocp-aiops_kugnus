# Ver.0.1.3 런타임 정상화 및 검증 보고

작성일: 2026-06-25  
브랜치: `feat/v.0.1.3`  
기준 HEAD: `1b37485 fix dev doctor task shell invocation`  
작업 경로: `/home/kugnus/cywell/ocp-aiops_kugnus`

## 현재 판단

Ver.0.1.3 로컬 시연 환경은 WSL native repo 기준으로 정상화됐다. 회사 OCP에는 설치/배포를 수행하지 않았고, 로컬 Gateway/Console/RAG dev DB/port-forward 조합으로 검증했다.

## 확인한 런타임

| 항목 | 포트/주소 | 상태 |
|---|---|---|
| Local Console | `http://localhost:9000/dashboards` | HTTP 200 |
| Plugin webpack | `http://127.0.0.1:9001` | manifest HTTP 200 |
| Gateway | `http://127.0.0.1:18080` | healthz OK |
| Lightspeed port-forward | `18443` | listening |
| Action Executor port-forward | `18083` | healthz OK |
| pgvector RAG dev DB | `127.0.0.1:15432` | Docker container running |

## 발견한 문제

### Action Executor port-forward 누락

증상:

- Gateway는 execute 모드로 떠 있었다.
- `task kugnus:dev:doctor`에서 `Action Executor service is readable`은 PASS였다.
- 하지만 `ss -ltnp | grep ':18083'` 기준으로 로컬 `18083` 포트가 리슨 중이 아니었다.

의미:

- UI에서 `실행 가능`이 보이더라도, 실제 Action Executor 호출 경로가 끊길 수 있는 상태였다.
- 서비스 자체 문제는 아니고 로컬 port-forward 누락이었다.

조치:

```bash
nohup oc -n komsco-ai-dev port-forward --address 0.0.0.0 svc/komsco-ai-action-executor 18083:8080 >> .dev-action-executor-port-forward.log 2>&1 &
```

검증:

```bash
curl http://127.0.0.1:18083/healthz
```

결과:

```json
{"status":"ok"}
```

## 통과한 검증

| 검증 | 결과 | 산출물 |
|---|---|---|
| Runtime smoke | PASS | `docs/Ver.0.1.3/runtime-smoke-report.json` |
| Evidence RCA scene | PASS | `docs/Ver.0.1.3/evidence-rca-scene-verification.json` |
| CrashLoop live demo cycle | PASS | `docs/Ver.0.1.3/crashloop-live-demo-cycle-verification.json` |
| 10 scenario evaluation | 10/10 PASS | `docs/Ver.0.1.3/aiops-scenario-evaluation-report.json` |
| Screen readiness | PASS | `docs/Ver.0.1.3/crashloop-screen-cycle-readiness-verification.json` |
| Dev doctor | FAIL 0 | warning은 이미 떠 있는 포트 때문 |

## smoke 핵심 증거

```text
Runtime smoke: PASS
health=92 nodes=1/1 operators=34/34
rag=collected backend=pgvector configured=True results=3
```

## 아직 완료로 말하면 안 되는 것

- Cypress 브라우저 E2E는 이번 정상화에서 실행하지 않았다.
- 회사 OCP에 신규 설치, 카탈로그 등록, 배포를 수행하지 않았다.
- `default` namespace에 과거 재시작 Pod 로그가 반드시 있다고 가정하면 안 된다.
- `실험 무제한` 모드를 회사 OCP 대상으로 기본 사용하면 안 된다.

## 다음 행동

집에서는 `docs/Ver.0.1.3/home-demo-test-order.md` 순서대로 실행한다. 우선순위는 다음이다.

1. `task kugnus:dev:doctor`
2. `task kugnus:runtime:smoke`
3. `task kugnus:scenario:verify`
4. `task kugnus:demo:live-verify`
5. `http://localhost:9000/dashboards`에서 공식 질문 시연
