# Ubuntu Codex Handoff

## 목적

이 문서는 Windows 경로에서 작업하던 혼선을 끊고, 새 Ubuntu/WSL Codex 세션이 현재 작업을 바로 이어받기 위한 인수인계 문서다.

새 Codex의 첫 임무는 코드를 무작정 수정하는 것이 아니라, **현재 기준점, 안전 경계, 검증 루프, 다음 작업 목표**를 확인하고 Ver.0.1.6 작업을 이어가는 것이다.

## 현재 기준점

| 항목 | 값 |
| --- | --- |
| 실제 작업 repo | `/home/kugnus/cywell/ocp-aiops_kugnus` |
| Codex Desktop workspace 권장 경로 | `\\wsl.localhost\Ubuntu\home\kugnus\cywell\ocp-aiops_kugnus` |
| 현재 브랜치 | `feat/v.0.1.6` |
| 원격 추적 | `origin/feat/v.0.1.6` |
| Ver.0.1.5 마감 커밋 | `1351dfc complete ver.0.1.5 docs rag controls` |
| Ver.0.1.6 시작 커밋 | `382c885 start ver.0.1.6 demo readiness plan` |
| 로컬 콘솔 URL | `http://localhost:9000/dashboards` |
| 기본 작업 원칙 | 회사 OCP/OKD 설치 없이 로컬 개발 콘솔에서 연결 검증 |

## 새 Codex가 처음 해야 할 일

아래 명령은 Ubuntu/WSL 터미널 기준이다.

```bash
cd /home/kugnus/cywell/ocp-aiops_kugnus
pwd
git status --short --branch
git log -1 --oneline
```

정상 기준:

```text
/home/kugnus/cywell/ocp-aiops_kugnus
## feat/v.0.1.6...origin/feat/v.0.1.6
382c885 start ver.0.1.6 demo readiness plan
```

그 다음 아래 문서를 순서대로 읽는다.

1. `docs/Ver.0.1.6/README.md`
2. `docs/Ver.0.1.6/demo-readiness-and-rag-docs-plan.html`
3. `docs/Ver.0.1.5/zero-base-setup-and-reboot-recovery-guide.html`
4. `docs/version-progress-book.html`
5. `docs/Ver.0.1.5/docs-rag-management-brief.html`

## 현재까지 완료된 핵심

- WSL native repo로 실제 작업대를 이전했다.
- `feat/v.0.1.5`에서 Docs/RAG 관리 화면과 직접 실행 안내서를 마감했다.
- `feat/v.0.1.6` 브랜치를 새로 만들고 Demo Readiness & RAG Docs Control 계획을 시작했다.
- 앞으로 버전이 올라가면 현재 버전 커밋/푸시 후 새 `feat/v.X.Y.Z` 브랜치를 먼저 만드는 규칙을 산출물에 박아두었다.

## Ver.0.1.6 목표

1. **시연 Preflight 자동화**
   - `oc login`, Docker, RAG DB, Gateway, Console, Lightspeed, ActionExecutor, UI route 상태를 한 번에 점검한다.
   - 실패하면 원인 계층과 다음 행동을 HTML/JSON report로 남긴다.

2. **공식 시연 시나리오 한 사이클 고정**
   - 운영 질문 하나로 상태 확인 -> Evidence/RAG/ToolPlan/Runbook -> 조치 후보까지 이어지는 흐름을 고정한다.

3. **Docs/RAG 화면 제품화**
   - 업로드 문서가 실제 RAG 근거로 쓰였는지 운영자가 화면에서 확인할 수 있게 다듬는다.
   - PBS의 업로드/뷰어 감성은 참고하되, raw 문서 전체 노출보다 redacted chunk/evidence preview를 우선한다.

4. **UI 의미 정돈**
   - 헤더 상태칩, 실행 모드칩, Docs 탭, 새 대화 버튼, 전송/정지 버튼의 의미와 형태를 통일한다.

5. **시연 책자 보강**
   - 실행 전 점검, 시연 멘트, 실패 시 복구 루트, 현재 가능한 것과 말하면 안 되는 것을 책자에 연결한다.

## 안전 경계

별도 사용자 승인 전까지 아래는 실행하지 않는다.

```bash
task catalog:deploy
task catalog:release
task catalog:runtime:apply
task olm:deploy
task olm:release
task olm:install
task kugnus:install
```

또한 아래 작업을 하지 않는다.

- 회사 OCP/OKD 리소스에 대한 임의 `apply/delete/patch/scale/exec`
- 기존 회사 공용 `komsco-ai-console-plugin` 또는 `lightspeed-console-plugin` 교체
- `.env`, token, kubeconfig, password, 인증정보 읽기/커밋
- 로컬 smoke 성공을 production RAG 품질 완료로 보고
- 로컬 개발 콘솔 검증을 회사 OCP 설치 완료로 보고

## 검증 명령

기본 검증:

```bash
task kugnus:dev:doctor
task kugnus:runtime:smoke
task kugnus:rag:file-upload:smoke
task kugnus:rag:chat:smoke
task kugnus:ui:verify
```

로컬 시연 복구:

```bash
task kugnus:rag:dev:up
task kugnus:demo:resume
```

엄격한 Lightspeed gate를 잠깐 분리해야 할 때:

```bash
KUGNUS_RESUME_RUN_STRICT_GATE=false task kugnus:demo:resume
```

## 실패 시 원인 분리

| 증상 | 먼저 의심할 것 | 다음 행동 |
| --- | --- | --- |
| `oc login` 필요 | 토큰 만료, VPN 끊김, 회사 API 접근 불가 | `oc whoami`, 필요 시 다시 로그인, 반복 시 `task kugnus:ocp:doctor` |
| Docker daemon 연결 불가 | Docker Desktop 미실행 또는 WSL integration 꺼짐 | Windows Docker Desktop 확인 후 WSL에서 `docker version` |
| 9000/9001/18080 port WARN | 이전 console/webpack/Gateway가 이미 떠 있음 | 정상 응답이면 허용, 이상하면 `task kugnus:dev:doctor`와 `.tmp-kugnus-demo/*.log` 확인 |
| UI가 안 바뀜 | console bridge와 webpack dev server 불일치 | `curl -I http://127.0.0.1:9000/dashboards`, `curl -I http://127.0.0.1:9001/plugin-manifest.json` |
| RAG 결과 없음 | pgvector 미실행, 업로드 문서 없음, 검색어 불일치 | `task kugnus:rag:dev:up`, `task kugnus:rag:file-upload:smoke` |
| 직접 Gateway API 401 | console proxy/UserToken 경로가 아닌 직접 호출 | smoke task 또는 브라우저 plugin proxy로 검증 |

## 작업 방식

- 큰 변경 전에는 `목표`, `완료 조건`, `검증 방법`, `하지 않을 것`을 먼저 잠근다.
- 구현은 작게 나누고 각 단계마다 가까운 검증을 돌린다.
- 실패 원인은 `PowerShell 탓`, `도구 탓`으로 뭉개지 말고 `route missing`, `manifest mismatch`, `stale state`, `auth expired`, `port stale`, `data gap`처럼 실제 단위로 이름 붙인다.
- UI 작업은 겉보기 수정 후 반드시 `task kugnus:ui:verify` 또는 해당 DOM/route 검증을 붙인다.
- 새 버전으로 넘어갈 때는 사용자가 따로 말하지 않아도 브랜치를 먼저 만든다.

## 다음 추천 작업

1. `task kugnus:demo:preflight`로 현재 작업대 report를 갱신한다.
2. `docs/Ver.0.1.6/preflight-report.html/json`의 blocker를 먼저 해소한다.
3. `docs/Ver.0.1.6/official-demo-scenario.md` 순서로 공식 시연 한 사이클을 재현한다.
4. 필요하면 `task kugnus:runtime:smoke`, `task kugnus:rag:file-upload:smoke`, `task kugnus:rag:chat:smoke`, `task kugnus:ui:verify`로 보강 evidence를 갱신한다.
5. Docs/RAG 화면에서 report와 실제 chunk preview가 어긋나면 UI/verifier를 보강한다.

## 새 Codex에게 주는 첫 지시 예시

```text
이 repo는 WSL native /home/kugnus/cywell/ocp-aiops_kugnus 기준이다.
먼저 docs/Ver.0.1.6/ubuntu-codex-handoff.md, README.md, demo-readiness-and-rag-docs-plan.html을 읽고
Ver.0.1.6의 첫 작업으로 task kugnus:demo:preflight report를 갱신하고 blocker를 확인해라.
회사 OCP/OKD 설치나 OLM install은 하지 마라.
```

2026-06-26 KST 기준으로 preflight contract/task/scenario 초안은 추가됐다. 새 세션은 먼저 report를 재생성하고 현재 blocker 여부를 확인한다.
