# Ver.0.1.2 작업 세션 운영 규칙

이 문서는 작업이 끊겼다가 다시 시작될 때 같은 삽질을 반복하지 않기 위한 운영 규칙이다. 목표는 빠르게 재개하되, 사용자가 기술시연에서 구조와 원리를 설명할 수 있을 만큼 작업 과정을 이해하게 만드는 것이다.

## 1. 기본 원칙

- 기본 작업 환경은 Windows PowerShell이 아니라 WSL Ubuntu다.
- 프로젝트 기준 경로는 `/mnt/c/Users/soulu/cywell/ocp-aiops_kugnus`다.
- 회사 OCP는 read-only 관측 대상으로 사용한다.
- 로컬 개발 콘솔은 `http://localhost:9000/dashboards`에서 확인한다.
- 실제 회사 서버 설치, Subscription 생성, AIOpsInstallation 생성, 기존 ConsolePlugin 교체는 별도 승인 전까지 하지 않는다.

## 2. 세션 시작 순서

새 세션이나 재부팅 후에는 기능 작업을 바로 시작하지 않는다. 먼저 현재 상태를 고정한다.

```bash
cd /mnt/c/Users/soulu/cywell/ocp-aiops_kugnus
```

```bash
git status --short --branch
```

```bash
git rev-parse --short HEAD
```

```bash
oc whoami
oc whoami --show-server
```

```bash
docker version
```

확인해야 할 의미:

- `git status`: 지금 어떤 브랜치와 미커밋 변경이 있는지 확인한다.
- `HEAD`: 보고서와 커밋 기준점을 남긴다.
- `oc whoami`: 회사 OCP 로그인 토큰이 살아있는지 확인한다.
- `docker version`: 로컬 OpenShift console bridge를 띄울 수 있는지 확인한다.

## 3. 명령어 안내 규칙

사용자에게 명령어를 줄 때는 한 번에 여러 갈래를 던지지 않는다.

반드시 아래 순서로 말한다.

1. 지금 이 명령이 무엇을 하는지
2. 왜 지금 필요한지
3. 가장 권장하는 명령어 하나
4. 성공하면 보여야 하는 결과
5. 실패하면 다음에 확인할 것

금지:

- 선호 명령어를 아래쪽에 숨기지 않는다.
- 실행 환경이 다른 명령어를 같은 블록에 섞지 않는다.
- WSL 명령과 PowerShell 명령을 같은 흐름처럼 쓰지 않는다.
- 실패한 명령을 원인 확인 없이 반복해서 시키지 않는다.
- 사용자가 이해해야 하는 개념을 생략하고 단순노동처럼 지시하지 않는다.

예외:

- `netsh interface portproxy`, `Start-Service com.docker.service`, `wsl --shutdown`처럼 Windows host 제어가 필요한 경우만 PowerShell을 쓴다.
- 이 경우 반드시 `Windows PowerShell에서 실행`이라고 먼저 표시한다.

## 4. 로컬 서버 역할

이 프로젝트는 로컬 개발환경과 회사 OCP를 함께 쓴다.

### 백엔드

```bash
AIOPS_GATEWAY_MODE=read-only task be:dev
```

의미:

- 로컬 FastAPI gateway를 `127.0.0.1:18080`에 띄운다.
- 회사 OCP API, OLS/Lightspeed, Prometheus/Thanos 조회를 중계한다.
- 기본 모드는 read-only다.

확인:

```bash
curl http://127.0.0.1:18080/healthz
```

### 프론트엔드

```bash
task fe:dev
```

의미:

- 로컬 OpenShift console bridge를 `localhost:9000`에 띄운다.
- 콘솔 플러그인 dev server를 `localhost:9001`로 연결한다.
- 브라우저에서 `http://localhost:9000/dashboards`를 확인한다.

확인:

```text
http://localhost:9000/dashboards
```

## 5. 빠른 UI 확인과 최종 빌드 구분

UI 문구, 배치, 아이콘, CSS를 바꿀 때마다 production build를 먼저 돌리지 않는다.

기본 흐름:

1. `task fe:dev`를 켜둔다.
2. 코드를 수정한다.
3. 브라우저를 새로고침해 빠르게 확인한다.
4. 기능이나 UI가 잠기면 `corepack yarn build`를 돌린다.
5. 릴리즈/카탈로그/검증 전에는 `task kugnus:ui:verify`까지 확인한다.

production build가 오래 걸리는 이유:

- `package.json`의 build는 `yarn clean && NODE_ENV=production yarn webpack`이다.
- 매번 `dist`를 지우고 전체 번들을 다시 만든다.
- TypeScript strict check, webpack chunk 생성, plugin manifest 생성, asset hashing, minify가 함께 실행된다.
- 현재 repo가 `/mnt/c/...`에 있어 WSL에서 작은 파일을 많이 읽는 Node/webpack 작업이 느려질 수 있다.

따라서:

- 빠른 화면 확인은 dev server로 한다.
- 최종 검증만 production build로 한다.

## 6. 검증 우선순위

가장 가까운 검증부터 실행한다.

문구와 UI만 바꿨을 때:

```bash
cd komsco-ai-console-plugin
corepack yarn build
```

콘솔 상호작용까지 바꿨을 때:

```bash
task kugnus:ui:verify
```

gateway API를 바꿨을 때:

```bash
python3 -m pytest komsco-ai-gateway
```

```bash
curl http://127.0.0.1:18080/v1/cluster/summary
```

```bash
curl http://127.0.0.1:18080/v1/aiops/overview
```

검증 실패 시 원칙:

- 실패를 정상처럼 숨기지 않는다.
- `서버 문제`, `도구 문제`처럼 뭉뚱그리지 않는다.
- `oc login 만료`, `Docker daemon 미연결`, `route missing`, `stale dev server`, `gateway data unavailable`, `webpack full rebuild`처럼 실제 원인 단위로 기록한다.

## 7. 하지 않을 것

승인 전 금지:

- `task catalog:deploy`
- `task catalog:release`
- `task catalog:runtime:apply`
- `task olm:deploy`
- `task olm:release`
- `task olm:install`
- `task kugnus:install`
- `oc apply`
- `oc delete`
- `oc patch`
- `oc scale`
- `oc exec`

보안상 금지:

- `.env`, `.env.local`, token, kubeconfig, password 커밋
- 회사 공용 `komsco-ai-console-plugin` 덮어쓰기
- 기존 `lightspeed-console-plugin` 교체
- CRC context 결과를 회사 OCP 검증처럼 보고

## 8. 보고 규칙

작업 보고에는 최소한 아래를 남긴다.

- branch
- head sha
- 바뀐 파일
- 실행한 검증
- pass/fail 결과
- 실패가 남아 있으면 원인과 다음 행동

예시:

```text
branch: feat/v.0.1.2
head: 2558dbf
changed: AssistantLauncher.tsx, coolicons.tsx
verification: corepack yarn build pass
remaining: task kugnus:ui:verify는 gateway data unavailable로 fail
```

## 9. 시연 설명용 한 문장

현재 구조는 회사 OCP에 직접 설치한 상태가 아니라, WSL 로컬 개발환경에서 OpenShift 콘솔 브리지를 띄우고 회사 OCP를 read-only로 관측하는 방식이다. 백엔드 gateway는 OCP/OLS/metrics 데이터를 로컬에서 중계하고, 프론트 콘솔 플러그인은 로컬 dev server로 콘솔에 주입된다. 검증이 끝난 뒤에만 OLM CatalogSource/PackageManifest 등록으로 넘어가며, 실제 설치는 별도 승인 단계로 분리한다.
