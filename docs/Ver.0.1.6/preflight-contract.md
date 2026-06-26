# Ver.0.1.6 Demo Preflight Contract

작성 기준일: 2026-06-26 KST  
브랜치: `feat/v.0.1.6`  
목적: 로컬 WSL/Ubuntu 시연 작업대가 공식 데모를 시작할 수 있는지 한 번에 판정하고, 실패 원인과 복구 명령을 JSON/HTML report로 남긴다.

## 원칙

- preflight는 회사 OCP/OKD에 제품 설치, 배포, 변경성 명령을 수행하지 않는다.
- preflight는 OpenShift에 대해 `get`, `whoami`, read-only HTTP/API 확인만 수행한다.
- `.env`, token, kubeconfig, password, bearer token 값은 report와 stdout에 남기지 않는다.
- 로컬 개발 스택을 자동으로 띄우는 일은 `task kugnus:demo:resume`의 책임이다.
- preflight는 현재 상태를 판정하고, 필요한 다음 행동을 알려준다.

## 금지 명령

아래 명령은 preflight 내부에서 호출하지 않는다.

```bash
task catalog:deploy
task catalog:release
task catalog:runtime:apply
task olm:deploy
task olm:release
task olm:install
task kugnus:install
oc apply
oc delete
oc patch
oc scale
oc exec
```

## 산출물

기본 명령:

```bash
task kugnus:demo:preflight
```

기본 report:

| 파일 | 역할 |
| --- | --- |
| `docs/Ver.0.1.6/preflight-report.json` | 자동 판정용 canonical report |
| `docs/Ver.0.1.6/preflight-report.html` | 사용자/발표자용 시각 report |

## 판정 등급

| 등급 | 의미 | 다음 행동 |
| --- | --- | --- |
| `pass` | 공식 시연 시작에 필요한 핵심 조건이 모두 통과했다. | 시연 시나리오를 진행한다. |
| `warn` | 시연은 가능하지만 선택 검증이나 증거가 부족하다. | report의 warning과 보강 task를 확인한다. |
| `fail` | 공식 시연을 시작하면 중간에 멈출 가능성이 높다. | blocker의 `nextAction`을 먼저 수행한다. |

## 필수 점검 항목

| 그룹 | 항목 | PASS 기준 | 실패 시 다음 행동 |
| --- | --- | --- | --- |
| Workspace | repo 위치 | `/home/kugnus/...` 네이티브 Linux filesystem | Ubuntu workspace로 다시 열기 |
| Workspace | `.env` hygiene | 파일 존재, 권한 `600` 이하, CRLF 0, Git ignored | `.env`를 다시 가져오고 `chmod 600 .env` |
| Toolchain | `task`, `python3`, `node`, `yarn`, `docker`, `oc`, `curl` | 모두 Ubuntu/WSL 경로에서 실행 가능 | 누락 도구 설치 또는 PATH 정리 |
| Browser | `google-chrome` | Ubuntu Chrome for Testing 또는 Linux Chrome 실행 가능 | `~/.local/bin/google-chrome` wrapper 확인 |
| Docker | daemon | `docker info` 성공 | Docker Desktop/daemon 시작 |
| OpenShift | identity | `oc whoami`, `oc whoami --show-server` 성공 | `oc login` 후 `task kugnus:ocp:doctor` |
| OpenShift | service read | Lightspeed, Action Executor service read 가능 | VPN/RBAC/namespace/service 이름 확인 |
| Local stack | Gateway | `/healthz`, `/v1/aiops/status`, `/v1/cluster/summary` 성공 | `task kugnus:demo:resume` 또는 Gateway 로그 확인 |
| Local stack | Console | `9000` console route와 `9001` plugin manifest HTTP OK | `task kugnus:dev:fe` 또는 stale port 정리 |
| RAG | pgvector | `kugnus-rag-pgvector` container와 `pg_isready` 성공 | `task kugnus:rag:dev:up` |
| RAG | Gateway RAG API | `/v1/rag/uploads`, `/v1/rag/search` 성공, raw content 미반환 | Gateway RAG env와 DB 상태 확인 |

## 선택 보강 검증

preflight report는 아래 task를 다음 단계 evidence로 연결한다. 이 task들은 별도 실행으로 남겨도 된다.

```bash
task kugnus:runtime:smoke
task kugnus:rag:file-upload:smoke
task kugnus:rag:chat:smoke
task kugnus:ui:verify
```

## 공식 시연 루프

preflight가 `pass`면 아래 순서로 공식 시연을 진행한다.

1. `http://localhost:9000/aiops-kugnus`를 연다.
2. 관제탑에서 클러스터 상태, 이상 징후, Evidence posture, RAG/ToolPlan 상태를 확인한다.
3. Cywell AI에 공식 질문을 입력한다.
4. 답변 하단의 수집 근거와 추가 확인 필요 근거를 확인한다.
5. Docs 화면에서 업로드 문서와 redacted chunk preview를 확인한다.
6. 조치 후보는 read-only/승인 경계를 설명하고, 승인 없는 변경은 수행하지 않는다.

공식 질문:

```text
최근 OpenShift 경고와 우선 확인할 항목을 실제 근거와 추가 확인 필요 항목으로 구분해서 정리해줘.
```

## 완료 기준

- `task kugnus:demo:preflight`가 JSON/HTML report를 생성한다.
- report에 핵심 endpoint와 실패 원인이 포함된다.
- report가 비밀값을 노출하지 않는다.
- preflight 실패 시 `task kugnus:demo:resume`, `task kugnus:rag:dev:up`, `task kugnus:ocp:doctor` 중 어떤 복구 루트를 써야 하는지 드러난다.
- 공식 시연 시나리오 문서가 preflight report와 연결된다.
