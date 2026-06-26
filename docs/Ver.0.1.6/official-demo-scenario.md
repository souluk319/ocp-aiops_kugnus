# Ver.0.1.6 Official Demo Scenario

작성 기준일: 2026-06-26 KST  
목적: Ver.0.1.6 시연을 매번 같은 순서로 재현하고, 가능한 것과 말하면 안 되는 것을 분리한다.

## 시작 전 조건

먼저 preflight report를 생성한다.

```bash
task kugnus:demo:preflight
```

PASS 기준:

- `docs/Ver.0.1.6/preflight-report.json`의 `summary.result`가 `pass` 또는 발표자가 설명 가능한 `warn`이다.
- Gateway, Console, RAG, OpenShift identity, Lightspeed/Action Executor service read가 report에 표시된다.
- `summary.blockers`가 비어 있다.

preflight가 fail이면 시연을 시작하지 않고 report의 `nextAction`을 먼저 수행한다.

## 공식 질문

```text
최근 OpenShift 경고와 우선 확인할 항목을 실제 근거와 추가 확인 필요 항목으로 구분해서 정리해줘.
```

## 시연 흐름

1. 관제탑 열기
   - URL: `http://localhost:9000/aiops-kugnus`
   - 확인: health score, Ready nodes, Operator issues, Evidence posture, Lightspeed link.
   - 말할 것: "이 화면은 회사 OCP에 설치한 제품이 아니라 로컬 개발 콘솔에서 회사 OCP를 read-only로 관측하는 시연 작업대입니다."

2. 이상 징후와 조치 후보 확인
   - 확인: `Cywell AI 이상 징후 자동 정리`, `Cywell AI 조치 후보`.
   - 말할 것: "조치 후보는 제안이며 승인 전 실행하지 않습니다."
   - 말하지 말 것: "자동으로 장애를 고쳤다", "회사 OCP에 변경을 적용했다".

3. Cywell AI 질문
   - 공식 질문을 입력한다.
   - 확인: 답변 본문이 수집 근거, 추가 확인 필요 항목, 우선순위를 분리한다.
   - 확인: fallback이면 `Gateway fallback`이 명시적으로 보인다.

4. Evidence footer 확인
   - 답변 하단에서 collected evidence와 missing evidence를 확인한다.
   - 말할 것: "확인한 사실과 확인이 필요한 항목을 분리해 근거 없는 단정을 막습니다."

5. Docs/RAG 확인
   - URL: `http://localhost:9000/aiops-kugnus/docs`
   - 확인: 업로드 문서 수, chunk 수, raw content hidden, checksum, ACL, redacted chunk preview.
   - 말할 것: "원문 전체가 아니라 Gateway가 redaction 후 반환한 chunk preview만 화면에 노출합니다."

6. 안전 경계 설명
   - 정책 화면 또는 조치 후보 board에서 read-only/mutation disabled 상태를 확인한다.
   - 말할 것: "승인, sealed plan, freshness, SSAR, mutation flag가 맞지 않으면 실행하지 않습니다."

## 실패 시 복구 루트

| 증상 | 먼저 볼 report/check | 다음 행동 |
| --- | --- | --- |
| `oc whoami` 실패 | preflight `openshift.identity` | `oc login`, 반복되면 `task kugnus:ocp:doctor` |
| Gateway health 실패 | preflight `gateway.healthz` | `task kugnus:demo:resume`, `.tmp-kugnus-demo/gateway.log` 확인 |
| Console route 실패 | preflight `console.dashboard` | `task kugnus:dev:fe`, port 9000 stale process 확인 |
| RAG 문서/검색 실패 | preflight `rag.*` | `task kugnus:rag:dev:up`, `task kugnus:rag:file-upload:smoke` |
| UI verifier 실패 | `task kugnus:ui:verify` report | screenshot path와 failed check를 기준으로 수정 |
| Lightspeed final 실패 | `task kugnus:lightspeed:live-verify` | fallback으로 명시하고, strict success로 말하지 않는다 |

## 최종 검증 명령

공식 시연 전 전체 증거를 갱신하려면 아래 순서로 실행한다.

```bash
task kugnus:demo:preflight
task kugnus:runtime:smoke
task kugnus:rag:file-upload:smoke
task kugnus:rag:chat:smoke
task kugnus:ui:verify
```

## 말하면 안 되는 것

- 회사 OCP/OKD에 제품을 설치했다고 말하지 않는다.
- Gateway fallback을 Lightspeed 최종 성공이라고 말하지 않는다.
- RAG smoke 성공을 production RAG 품질 완료라고 말하지 않는다.
- read-only 조치 후보를 실제 실행 완료로 말하지 않는다.
- report에 없는 원인이나 수치를 확인된 사실처럼 말하지 않는다.
