# Ver.0.1.3 Stage 3 Review - Official Evidence RCA Scene

## 기준

공식 시연 기준은 `docs/Ver.0.1.3/Evidence_RCA_Scene.md`다.

공식 질문:

```text
어제 새벽에 default namespace Pod가 왜 재시작됐어?
```

이 단계는 CrashLoopBackOff 화면 smoke test를 공식 목표로 착각하지 않게 분리한다. CrashLoopBackOff 검증은 dashboard anomaly, chat stream, RCA Context, action candidate 연결을 확인하는 보조 smoke test다.

## 완료 조건

- Tool Plan에 `event_tool`, `grep_tool`, `metric_tool`, `snapshot_tool` 대응 항목이 있다.
- RCA Context에 event, pod log pattern/digest, metric, snapshot evidence가 구조화된다.
- RCA Context에 cause candidates, confidence, action candidates가 first-class 필드로 있다.
- final answer contract에 RCA, 즉시 조치, 재발 방지책, 참고 증적 관점이 있다.
- `readOnlyOnly: true` demo context는 서버에서 read-only로 강제된다.
- raw log 원문과 mutation 명령은 답변/검증 산출물에 남기지 않는다.

## 검수자 지적과 반영

| 지적 | 반영 |
| --- | --- |
| 공식 목표와 CrashLoop smoke test가 문서에서 섞여 있었다. | README, HTML 산출물, Stage 2 review에 공식 Evidence RCA를 상위 기준으로 명시했다. |
| live report가 fail 상태로 남아 있었다. | raw log 검증식이 패턴명 `traceback`을 원문 로그로 오탐하지 않게 조정하고 live verifier를 재실행 대상으로 고정했다. |
| `snapshot_tool` 계약은 있으나 runtime evidence collector가 없었다. | Pod status preflight와 CrashLoop demo evidence collector가 `snapshot` evidence ref를 별도로 발행하도록 수정했다. |
| 공식 질문은 `default namespace`인데 demo allowlist 기본값은 `komsco-ai-dev`뿐이었다. | `KOMSCO_AIOPS_DEMO_NAMESPACE_ALLOWLIST` 기본값에 `default`를 추가했다. |
| official verifier가 fixture만으로 pass할 수 있었다. | required evidence가 RCA Context missing에 남으면 fail하도록 하고, runtime snapshot collector source wiring을 검사한다. |
| `GatewayContext` version이 `0.1.1`로 남아 있었다. | GatewayContext metadata version을 `0.1.3`으로 갱신했다. |
| 브라우저 증거가 없어 공식 질문을 실제 화면에 올렸다고 말하기 어려웠다. | in-app browser로 `/dashboards`를 열고 Cywell AI Troubleshooting 모드에 공식 질문을 입력한 증거를 `official-evidence-rca-browser-verification.json`과 `official-evidence-rca-browser-screen.png`로 남겼다. |
| submit 이후 답변 본문 화면 증거가 없었다. | 공식 질문을 전송해 `Gateway fallback` RCA 답변, 수집 근거, RCA digest, evidence별 collected/partial/skipped 상태가 보이는 화면 증거를 `official-evidence-rca-browser-answer-verification.json`과 `official-evidence-rca-browser-answer-screen.png`로 남겼다. |
| Cypress 스펙이 실제 UI 라벨과 맞지 않을 수 있었다. | Assistant surface에 `aria-label="Cywell AI assistant"`를 추가해 Cypress selector와 접근성 계약을 맞췄다. |
| 공식 질문의 `default namespace`를 pageContext 없이 파싱하지 못했다. | `default namespace`, `namespace default`, `default 네임스페이스` 형태를 모두 namespace mention으로 인식하게 수정하고 회귀 테스트를 추가했다. |
| `current-state`/운영 시나리오 HTML이 실제 수집과 안정적인 Lightspeed 완료처럼 읽힐 수 있었다. | browser proof는 staging과 Gateway fallback answer proof이며, 안정적인 Lightspeed 최종 RCA와 실제 default namespace 과거 증적 완전 수집은 아직 과장 금지라고 문구를 낮췄다. |
| 공식 질문에 Pod 이름이 없어 CrashLoop 전용 collector가 붙지 않았다. | `pod_restart_rca` Tool Plan의 namespace를 기준으로 Event, Pod snapshot, previous log pattern probe를 read-only로 시도하는 `official_namespace_restart_*` collector를 추가했다. |
| browser answer proof가 collector 추가 전 상태라 `event/snapshot/pod_log` 최신 경로를 증명하지 못했다. | local console bridge의 plugin manifest base URL을 dev server 실제 경로와 맞추고, 공식 질문을 Troubleshooting 모드로 재전송해 최신 answer proof를 `official-evidence-rca-browser-answer-verification.json`과 `official-evidence-rca-browser-answer-screen.png`로 갱신했다. |
| RCA Context missing reason에 과거 `pod_log not fetched yet` 문구가 남아 실제 log pattern probe 시도와 충돌했다. | 공식 Pod restart RCA Tool Plan의 기본 missing 목록에서 `event`, `snapshot`, `pod_log`를 제거하고, 이 evidence들은 런타임 collected/partial/skipped 상태로만 표현되게 정리했다. |

## 현재 남은 gap

- official verifier는 offline/source contract 검증이다. 실제 브라우저에서 공식 질문 staging과 submit-to-answer 화면 증거를 갱신했지만, 이 답변은 `Gateway fallback` 경로다.
- `task kugnus:evidence-rca:browser-verify`는 Cypress 기반 재현 가능 검증으로 준비돼 있다. 현재 WSL 환경에서는 Cypress/Electron OS 의존성 `libnspr4.so`가 없어 실행 pass로 보고하지 않는다.
- runtime evidence collector는 공식 event/log-pattern/metric/snapshot 계약을 표현하고 namespace 단위 restart evidence collection을 시도한다. 최신 browser proof에서는 Event와 Snapshot은 완료, Log Pattern Probe는 재시작 후보 Pod 부재로 skipped 상태가 드러난다. 다만 실제 회사 OCP `default` namespace에서 특정 과거 Pod 재시작 사건을 항상 완전히 수집한다고 말하지 않는다.
- 실제 회사 OCP의 `default` namespace에 재시작 Pod가 존재한다고 가정하면 안 된다. 발표 시에는 공식 질문과 실제 demo target을 분리해서 말해야 한다.
- Lightspeed가 항상 최종 RCA를 안정적으로 생성한다고 과장하면 안 된다. Gateway에는 fallback answer path가 있다.
- raw log 분석은 원문 출력이 아니라 pattern/digest evidence로 표현한다.

## 발표 문구

말해도 되는 것:

- Ver.0.1.3은 공식 Evidence RCA 시나리오의 Tool Plan, RCA Context, read-only safety contract를 고정했다.
- CrashLoopBackOff 흐름은 대시보드와 chat stream 연결을 검증하는 smoke test로 유지한다.
- 로컬 OKD 콘솔에서 Cywell AI 패널을 열고 공식 질문을 Troubleshooting 모드에 올린 뒤, Gateway fallback RCA 답변이 렌더링되는 화면 증거를 남겼다.
- 현재 답변은 원인 확정이 아니라 evidence 기반 원인 후보와 추가 확인 순서를 제시한다.

말하면 안 되는 것:

- 실제 클러스터에서 event/log/metric/snapshot 과거 증적을 모두 완전 수집했다.
- Lightspeed 최종 RCA가 모든 환경에서 안정적으로 완료된다.
- 화면 클릭부터 안정적인 Lightspeed 최종 RCA까지 UI E2E가 이미 완전 검증됐다.
- Cypress 기반 브라우저 검증이 현재 WSL에서 pass했다.
- raw log 분석을 원문 기준으로 완료했다.

## 검증 명령

```bash
task kugnus:evidence-rca:verify
task kugnus:demo:live-verify
task kugnus:demo:screen-readiness
task kugnus:scenario:verify
```

브라우저 증거 산출물:

- `official-evidence-rca-browser-verification.json`
- `official-evidence-rca-browser-screen.png`
- `official-evidence-rca-browser-answer-verification.json`
- `official-evidence-rca-browser-answer-screen.png`

Cypress 기반 자동 브라우저 검증은 다음 명령으로 재시도한다. 단, 현재 WSL에 `libnspr4.so` 등 Cypress/Electron OS 의존성이 없으면 실패한다.

```bash
task kugnus:evidence-rca:browser-verify
```
