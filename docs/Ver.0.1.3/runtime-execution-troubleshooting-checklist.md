# Ver.0.1.3 실행 문제 체크리스트

## 목적

이 문서는 Ver.0.1.3 공식 시연과 로컬 개발 콘솔을 다시 실행할 때 어디서 문제가 나는지 빠르게 찾기 위한 체크리스트다.

목표는 기능 추가가 아니라 재현성 확보다. 즉, 아침에 WSL을 열고 백엔드/프론트/로컬 콘솔을 켰을 때 `http://localhost:9000/dashboards`에서 Cywell AI가 안정적으로 뜨는지 확인한다.

## 기준 명령

먼저 전체 진단:

```bash
cd /mnt/c/Users/soulu/cywell/ocp-aiops_kugnus
task kugnus:dev:doctor
```

기본 실행 가능 모드:

```bash
cd /mnt/c/Users/soulu/cywell/ocp-aiops_kugnus
task kugnus:dev:be:execute
```

프론트/로컬 콘솔:

```bash
cd /mnt/c/Users/soulu/cywell/ocp-aiops_kugnus
task kugnus:dev:fe
```

안전 관측 모드:

```bash
task kugnus:dev:be:read-only
```

로컬 실험 무제한 모드:

```bash
task kugnus:dev:be:unrestricted
```

`unrestricted`는 로컬 랩 전용이다. 회사 OCP 운영 또는 공식 발표 문구에서 기본 모드처럼 말하지 않는다.

## 1. WSL/Node/Yarn 환경

| 항목 | 확인 명령 | Pass | Fail 시 의심 |
| --- | --- | --- | --- |
| WSL Ubuntu 진입 | `pwd` | `/mnt/c/Users/soulu/cywell/ocp-aiops_kugnus` 또는 의도한 repo 경로 | PowerShell/Windows shell에서 명령 실행 중 |
| Node가 WSL Node인지 | `which node && node --version` | `/home/kugnus/.nvm/.../node`와 버전 출력 | `/mnt/c/Program Files/nodejs/node` 또는 Windows Node를 물고 있음 |
| Corepack이 WSL 것인지 | `which corepack` | `/home/kugnus/.nvm/.../corepack` | `/mnt/c/Program Files/nodejs/corepack`이면 build 실패 가능 |
| Yarn 버전 | `cd komsco-ai-console-plugin && corepack yarn --version` | `4.13.0` | corepack 다운로드 실패 또는 Windows 경로 혼입 |
| Go Task | `task --version` | 버전 출력 | `taskwarrior` 설치 안내가 뜨면 잘못된 패키지 |

Fail 대응:

```bash
bash -ic 'which node && which corepack && node --version && corepack yarn --version'
```

`bash -ic`에서는 nvm 초기화가 적용된다. build/dev 명령은 WSL 안에서 실행한다.

## 2. Git/작업 경로

| 항목 | 확인 명령 | Pass | Fail 시 의심 |
| --- | --- | --- | --- |
| 브랜치 | `git status --short --branch` | `feat/v.0.1.3` 또는 의도한 브랜치 | 다른 브랜치에서 작업 중 |
| 원격 | `git remote -v` | `origin`은 개인 repo, `upstream`은 회사 원본 repo | 회사 repo에 직접 push 위험 |
| 민감정보 | `git status --short .env .env.local` | commit 대상 아님 | token/kubeconfig commit 위험 |

주의:

- `.env`, `.env.local`, kubeconfig, token은 커밋하지 않는다.
- 기존 dirty worktree가 많으므로 unrelated 변경을 되돌리지 않는다.

## 3. OpenShift 인증

| 항목 | 확인 명령 | Pass | Fail 시 의심 |
| --- | --- | --- | --- |
| API 서버 | `oc whoami --show-server` | `https://api.ocp.cywell.server:6443` | CRC나 다른 cluster context |
| 로그인 사용자 | `oc whoami` | 사용자명 출력 | `Unauthorized`이면 토큰 만료 |
| 현재 프로젝트 | `oc project` | 의도한 프로젝트 확인 | 이전 실험 namespace에 머무름 |
| Lightspeed svc | `oc get svc -n openshift-lightspeed lightspeed-app-server` | 서비스 조회 성공 | VPN/권한/namespace 문제 |
| Action Executor svc | `oc get svc -n komsco-ai-dev komsco-ai-action-executor` | execute 모드용 서비스 조회 성공 | 실행 가능 모드에서 port-forward 실패 가능 |

Fail 대응:

1. 웹 콘솔에서 새 token 발급
2. `oc login --token=... --server=https://api.ocp.cywell.server:6443`
3. 다시 `oc whoami` 확인

주의:

- SSH 로그인과 `oc login`은 다른 개념이다.
- `oc`는 현재 kubeconfig context 한 곳을 바라본다. 창마다 SSH 대상이 달라도 WSL 안의 `oc` context는 별도로 확인해야 한다.

## 4. Docker Desktop / Local Console Bridge

| 항목 | 확인 명령 | Pass | Fail 시 의심 |
| --- | --- | --- | --- |
| Docker daemon | `docker version` | Server 정보까지 출력 | Docker Desktop WSL integration 꺼짐 |
| WSL integration | Docker Desktop UI | Ubuntu toggle on | Docker가 WSL distro를 못 봄 |
| Console port | `curl -I http://127.0.0.1:9000/dashboards` | `HTTP/1.1 200 OK` | console bridge 미기동 또는 포트 충돌 |
| Plugin manifest | `curl -I http://127.0.0.1:9001/api/plugins/komsco-ai-console-plugin-kugnus/plugin-manifest.json` | `HTTP/1.1 200 OK` | webpack dev server 미기동 또는 manifest path mismatch |

Windows 재부팅 후 흔한 문제:

- Docker Desktop은 켜졌지만 WSL integration이 다시 늦게 붙는다.
- `docker version`에서 Client만 뜨고 Server가 안 뜬다.
- `9000`이 Docker container나 이전 bridge에 잡혀 있다.

포트 확인:

```bash
ss -ltnp | grep -E ':9000|:9001|:18080|:18443|:18083' || true
```

## 5. 백엔드 Gateway

| 항목 | 확인 명령 | Pass | Fail 시 의심 |
| --- | --- | --- | --- |
| read-only 기동 | `task kugnus:dev:be:read-only` | `Uvicorn running on ...:18080` | oc login/Lightspeed port-forward 실패 |
| execute 기동 | `task kugnus:dev:be:execute` | `ACTION_EXECUTOR: true`, `KOMSCO_AI_ENABLE_MUTATIONS: true` | Action Executor svc/port-forward 실패 |
| unrestricted 기동 | `task kugnus:dev:be:unrestricted` | `KOMSCO_AI_ENABLE_UNRESTRICTED_COMMANDS: true` | 로컬 실험 모드 미활성 |
| healthz | `curl http://127.0.0.1:18080/healthz` | `{"status":"ok"}` | backend 미기동 또는 포트 충돌 |
| runtime status | `curl -s http://127.0.0.1:18080/v1/aiops/status` | 인증 통과 시 JSON | console proxy token 없이 직접 호출하면 401 가능 |

실행 모드 기대값:

| 모드 | mutationsEnabled | actionExecutorConfigured | unrestrictedCommandsEnabled | UI 기대 |
| --- | --- | --- | --- | --- |
| read-only | false | false | false | `읽기 전용`만 안전 활성 |
| execute | true | true | false | `실행 가능` 활성 |
| unrestricted | true | true | true | 세 모드 모두 선택 가능 |

주의:

- execute는 Action Executor port-forward가 필요하다.
- unrestricted는 로컬 Gateway 프로세스 권한으로 명령 실행이 가능하므로 공식/회사 운영 모드로 쓰지 않는다.

## 6. 프론트/콘솔

| 항목 | 확인 명령 | Pass | Fail 시 의심 |
| --- | --- | --- | --- |
| 프론트 기동 | `task kugnus:dev:fe` | Console URL `http://localhost:9000` 출력 | Docker/port 9000/manifest path 문제 |
| Webpack manifest | `curl -I http://127.0.0.1:9001/api/plugins/komsco-ai-console-plugin-kugnus/plugin-manifest.json` | 200 | plugin dev server 미기동 |
| Console dashboard | 브라우저 `http://localhost:9000/dashboards` | OKD dashboard 표시 | bridge 미기동 |
| Cywell AI 토글 | 화면 우측 하단 | K 아이콘 라운딩 사각형 표시 | plugin 로드 실패 |
| Header 상태 | 챗봇 열기 | `Node`, `Operator` 운영 상태 + `읽기 전용`, `실행 가능`, `실행 무제한` 전환 토글 표시 | summary/status API 실패 |
| 우측 rail | 전체화면/확장 | `Node 1/1 · Ready`, `Operator 34/34 정상`, 실행 상태 배지 표시 | cluster summary/status API 실패 |

빌드 검증:

```bash
cd komsco-ai-console-plugin
corepack yarn build
```

주의:

- `/mnt/c` 경로에서는 webpack build가 1~5분 걸릴 수 있다.
- `corepack`이 Windows Node를 물면 `/mnt/c/Program Files/nodejs/corepack: cannot execute` 오류가 난다. 이때는 `bash -ic`로 실행한다.

## 7. 공식 시연 흐름

기준 질문:

```text
어제 새벽에 default namespace Pod가 왜 재시작됐어?
```

Pass 기준:

| 단계 | Pass |
| --- | --- |
| 모드 | `Troubleshooting` 선택 |
| Tool Plan | event/grep/metric/snapshot 성격의 evidence plan이 보임 |
| Evidence | Event, Snapshot, Log Pattern Probe, Node, Alert, Metric 상태가 collected/partial/skipped로 표시 |
| RCA Context | collected/missing count와 digest 표시 |
| 답변 | 원인 후보, 즉시 확인, 재발 방지 관점이 표시 |
| 안전성 | raw log 원문과 mutation 명령을 그대로 출력하지 않음 |

검증 명령:

```bash
task kugnus:evidence-rca:verify
task kugnus:demo:live-verify
task kugnus:scenario:verify
task kugnus:demo:screen-readiness
```

발표 때 말해도 되는 것:

- Gateway fallback 기반 Evidence RCA 흐름을 시연할 수 있다.
- 수집 가능한 evidence와 부족한 evidence를 구분해 RCA Context로 보여준다.
- read-only 안전 계약과 실행 모드 gate가 UI에 드러난다.

발표 때 말하면 안 되는 것:

- Lightspeed 최종 RCA가 항상 안정적으로 완료된다.
- Cypress 브라우저 E2E가 현재 WSL에서 pass했다.
- 실제 `default` namespace의 과거 로그/event/metric/snapshot을 모두 완전 수집했다.
- raw log 원문 분석을 완료했다.

## 8. Cypress 자동 브라우저 검증

현재 상태:

- Cypress spec은 준비돼 있다.
- 현재 WSL에는 Cypress/Electron OS 의존성 `libnspr4.so`가 없어 pass로 보고하지 않는다.

확인 명령:

```bash
task kugnus:evidence-rca:browser-verify
```

Fail 예:

```text
error while loading shared libraries: libnspr4.so
```

해결 방향:

- Cypress가 요구하는 Ubuntu 패키지를 설치한다.
- 설치 후 browser verifier를 다시 실행한다.
- pass 전까지 공식 보고서에는 Cypress E2E pass라고 쓰지 않는다.

## 9. 빠른 장애 분기

| 증상 | 먼저 볼 것 |
| --- | --- |
| `oc login이 필요합니다` | `oc whoami`, token 만료 |
| `Cannot connect to Docker daemon` | Docker Desktop WSL integration |
| `Console port 9000 is already in use` | `ss -ltnp | grep :9000`, 기존 console bridge |
| Cywell AI 토글이 안 뜸 | plugin manifest 9001, console bridge plugin path |
| 챗봇은 뜨는데 상태가 비어 있음 | backend 18080, `/v1/cluster/summary`, `/v1/aiops/status` |
| `실행 가능`이 비활성 | `task kugnus:dev:be:execute`로 backend 재기동, Action Executor port-forward |
| `실행 무제한`이 비활성 | `task kugnus:dev:be:unrestricted`로 backend 재기동 |
| build가 너무 오래 걸림 | `/mnt/c` I/O 병목, WSL 내부 repo 이전 검토 |
| `corepack` 실행 오류 | Windows Node 경로 혼입, `bash -ic`로 재실행 |

## 다음 처리 순서

1. `task kugnus:dev:doctor`를 먼저 실행한다.
2. WSL Node/Corepack 경로부터 고정한다.
3. `oc login`과 회사 OCP context를 확인한다.
4. Docker daemon과 WSL integration을 확인한다.
5. backend를 `execute` 모드로 띄운다.
6. frontend/console bridge를 띄운다.
7. `Node 1/1 · Ready`, `Operator 34/34 정상`, `실행 가능/읽기 전용/실행 무제한` UI 상태를 확인한다.
8. 공식 Evidence RCA 질문을 한 번 돌린다.
9. fail이 있으면 이 문서의 섹션 번호 기준으로 원인을 기록한다.
