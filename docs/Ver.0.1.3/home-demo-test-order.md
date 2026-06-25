# Ver.0.1.3 집에서 바로 실행/검증 순서

작성일: 2026-06-25  
작업 기준 경로: `/home/kugnus/cywell/ocp-aiops_kugnus`  
브랜치: `feat/v.0.1.3`  
현재 기준 HEAD: `1b37485 fix dev doctor task shell invocation`

## 1. 현재 판단

지금 Ver.0.1.3의 우선 목표는 **공식 시연 시나리오 한 사이클**을 로컬 개발 콘솔에서 안정적으로 보여주는 것이다.

이번 시연은 회사 OCP에 새 설치를 박는 단계가 아니다. 로컬 WSL 개발 서버가 회사 OCP를 read/port-forward 대상으로 바라보고, 로컬 Gateway와 Console Plugin이 다음 흐름을 보여주는 단계다.

- 로컬 콘솔: `http://localhost:9000/dashboards`
- 로컬 Gateway: `http://127.0.0.1:18080`
- Plugin webpack: `http://127.0.0.1:9001`
- Lightspeed port-forward: `18443`
- Action Executor port-forward: `18083`
- RAG pgvector dev DB: `127.0.0.1:15432`

## 2. 지금 통과한 검증

2026-06-25 기준 다음 검증은 pass 했다.

| 검증 | 명령 | 결과 |
|---|---|---|
| 런타임 smoke | `task kugnus:runtime:smoke` | PASS |
| Evidence/RCA 공식 장면 계약 | `task kugnus:evidence-rca:verify` | PASS |
| CrashLoop live demo cycle | `task kugnus:demo:live-verify` | PASS |
| 10개 운영 시나리오 계약 | `task kugnus:scenario:verify` | 10/10 PASS |
| 화면 시연 준비도 | `task kugnus:demo:screen-readiness` | PASS |
| 개발 환경 doctor | `task kugnus:dev:doctor` | FAIL 0, WARN은 이미 떠 있는 포트 때문 |

`task kugnus:runtime:smoke`의 핵심 출력:

```text
Runtime smoke: PASS
health=92 nodes=1/1 operators=34/34
rag=collected backend=pgvector configured=True results=3
```

## 3. 집에서 시작할 때 제일 먼저 할 것

반드시 WSL Ubuntu 터미널에서 시작한다. PowerShell이 아니라 Ubuntu다.

```bash
cd /home/kugnus/cywell/ocp-aiops_kugnus
```

먼저 상태 확인:

```bash
task kugnus:dev:doctor
```

정상 기준:

- `FAIL=0`이면 진행 가능하다.
- `9000`, `9001`, `18080`, `18443`, `18083` 포트가 이미 떠 있어서 `WARN`이면 보통 정상이다.
- `oc login` 실패, Docker daemon 실패, Gateway healthz 실패는 진짜 문제다.

## 4. 재부팅 후 전체 실행 순서

### 4.1 사전 조건

- Docker Desktop 실행
- VPN/회사망 연결
- `oc login` 완료
- WSL Ubuntu에서 작업

현재 회사 OCP 확인:

```bash
oc whoami --show-server
oc whoami
```

기대값:

```text
https://api.ocp.cywell.server:6443
admin
```

### 4.2 RAG pgvector dev DB 실행

```bash
task kugnus:rag:dev:up
```

이 작업은 로컬 Docker 컨테이너 `kugnus-rag-pgvector`를 준비한다. 회사 OCP에 설치하는 작업이 아니다.

### 4.3 백엔드 실행

새 터미널 A에서 실행하고 계속 켜 둔다.

```bash
cd /home/kugnus/cywell/ocp-aiops_kugnus && task kugnus:dev:be:execute:rag
```

이 명령의 의미:

- Gateway를 `0.0.0.0:18080`에 띄운다.
- Lightspeed를 `18443`으로 port-forward 한다.
- Action Executor를 `18083`으로 port-forward 한다.
- RAG backend를 pgvector로 연결한다.
- 실행 모드는 `execute`다.
- `unrestrictedCommands`는 기본적으로 꺼져 있다.

### 4.4 프론트/로컬 콘솔 실행

새 터미널 B에서 실행하고 계속 켜 둔다.

```bash
cd /home/kugnus/cywell/ocp-aiops_kugnus && task kugnus:dev:fe
```

정상 출력에는 다음이 포함된다.

```text
Plugin dev server: http://127.0.0.1:9001
Console URL: http://localhost:9000
```

`Console port 9000 is already in use`가 떠도 브라우저에서 `http://localhost:9000/dashboards`가 열리면 기존 콘솔이 이미 떠 있는 것이다.

### 4.5 smoke 검증

새 터미널 C에서 실행한다.

```bash
cd /home/kugnus/cywell/ocp-aiops_kugnus && task kugnus:runtime:smoke
```

반드시 봐야 할 값:

```text
Runtime smoke: PASS
rag=collected backend=pgvector configured=True results=3
```

## 5. 공식 시연 시나리오 검증 순서

시연 전에 아래 순서로 한 번 돌린다.

```bash
task kugnus:evidence-rca:verify
```

```bash
task kugnus:scenario:verify
```

```bash
task kugnus:demo:live-verify
```

```bash
task kugnus:demo:screen-readiness
```

기대값:

- Evidence/RCA: `pass`
- Scenario: `scenarioCount=10`, `passed=10`, `failed=0`
- Live demo: `pass`
- Screen readiness: `pass`

## 6. 브라우저에서 볼 것

브라우저 주소:

```text
http://localhost:9000/dashboards
```

챗봇을 열고 공식 질문을 넣는다.

```text
어제 새벽에 default namespace Pod가 왜 재시작됐어?
```

시연에서 확인할 흐름:

1. 사용자가 운영 사고 질문을 입력한다.
2. Gateway가 현재 OCP 컨텍스트와 Evidence/RCA 계약을 기준으로 응답한다.
3. RAG runbook 검색 상태가 `collected/configured`로 잡힌다.
4. 답변에는 원인 후보, 근거, 조치 순서, 재발 방지 관점이 포함되어야 한다.
5. UI 상단 상태는 노드 수, Health, Operator 상태, 실행 모드를 구분해서 보여줘야 한다.
6. 실행 모드는 `읽기 전용`, `실행 가능`, `실험 무제한`이 구분되어야 한다.

## 7. 실행 모드 해석

| 모드 | 의미 | 기본 사용 여부 |
|---|---|---|
| 읽기 전용 | 조회와 분석만 수행 | 안전 점검용 |
| 실행 가능 | 승인된 Action Executor 경로만 사용 | Ver.0.1.3 시연 기본 |
| 실험 무제한 | 로컬 lab에서 강한 실험용 | 기본 사용 금지 |

현재 시연 기본은 `실행 가능`이다. 다만 회사 OCP를 바라보고 있으므로 `실험 무제한`은 기본값으로 쓰지 않는다.

## 8. 자주 터지는 문제와 바로 확인할 것

### 8.1 oc login 만료

증상:

```text
You must be logged in to the server (Unauthorized)
```

조치:

```bash
oc login --token=<웹콘솔에서 받은 토큰> --server=https://api.ocp.cywell.server:6443
```

토큰은 문서나 git에 남기지 않는다.

### 8.2 Docker daemon 불가

증상:

```text
Cannot connect to the Docker daemon
```

조치:

- Docker Desktop 실행
- WSL integration에서 Ubuntu 활성화
- 다시 `docker version` 확인

### 8.3 RAG not configured

증상:

```text
rag=missing 또는 configured=False
```

조치:

```bash
task kugnus:rag:dev:up
```

그 다음 백엔드를 `task kugnus:dev:be:execute:rag`로 다시 실행한다.

### 8.4 Action Executor 18083이 안 떠 있음

확인:

```bash
ss -ltnp | grep ':18083' || true
```

정상 확인:

```bash
curl http://127.0.0.1:18083/healthz
```

백엔드를 `task kugnus:dev:be:execute:rag`로 정상 실행하면 보통 같이 열린다. 이미 백엔드만 떠 있고 포트포워딩만 죽은 경우에는 임시로 다음을 실행할 수 있다.

```bash
nohup oc -n komsco-ai-dev port-forward --address 0.0.0.0 svc/komsco-ai-action-executor 18083:8080 >> .dev-action-executor-port-forward.log 2>&1 &
```

### 8.5 9000 already in use

브라우저에서 아래 주소가 200이면 보통 문제 아니다.

```bash
curl -I http://127.0.0.1:9000/dashboards
```

응답이 없거나 오래된 화면이면 기존 콘솔 bridge를 종료하고 다시 `task kugnus:dev:fe`를 실행한다.

## 9. 하지 않을 것

아직 공식 회사 서버에 설치/배포하는 단계가 아니다. 아래는 별도 승인 전 금지다.

```bash
task kugnus:install
task kugnus:publish
task catalog:deploy
task catalog:release
task olm:install
task olm:deploy
```

또한 아래 mutation 명령은 시연 준비 중 임의 실행 금지다.

```bash
oc apply
oc delete
oc patch
oc scale
oc exec
```

## 10. 아직 pass라고 말하면 안 되는 것

- Cypress 브라우저 E2E는 WSL 브라우저 의존성 문제 때문에 pass라고 보고하면 안 된다.
- 실제 `default` namespace에 과거 재시작 Pod 로그가 항상 존재한다고 말하면 안 된다.
- 회사 OCP에 신규 설치/카탈로그 등록을 완료했다고 말하면 안 된다.
- `실험 무제한`이 회사 OCP에서 안전하다고 말하면 안 된다.

## 11. 현재 완료 기준

집에서 다음 네 가지가 되면 Ver.0.1.3 시연 준비는 진행 가능 상태다.

1. `task kugnus:runtime:smoke` PASS
2. `task kugnus:scenario:verify` 10/10 PASS
3. `http://localhost:9000/dashboards` 열림
4. 챗봇 공식 질문에 Evidence/RCA + RAG 기반 답변 흐름 확인
