# Ver.0.1.2 AIOps 관제탑 추진 계획

## 현재 상태

- 기준 브랜치: `feat/v.0.1.1`
- 현재 목표: Ver.0.1.2에서 1~6 기능 고도화를 순차 진행한다.
- 현재 개발 방식: 로컬 개발 콘솔과 회사 OCP read-only 연동 중심으로 진행한다.
- 회사 OCP에 실제 설치, 배포, Subscription 생성, AIOpsInstallation 생성은 별도 승인 전까지 하지 않는다.
- Windows 자동 업데이트/재부팅으로 로컬 서버는 꺼질 수 있으므로, 다음 작업 시작 시 복구 체크부터 진행한다.
- 세션 재개, WSL 기준 명령 안내, 빠른 UI 확인/최종 빌드 구분은 [work-session-operating-rules.md](./work-session-operating-rules.md)를 따른다.

## 재부팅 후 복구 체크리스트

1. VS Code에서 WSL Ubuntu 터미널을 연다.
2. 프로젝트 경로로 이동한다.

```bash
cd /mnt/c/Users/soulu/cywell/ocp-aiops_kugnus
```

3. 브랜치와 작업 상태를 확인한다.

```bash
git status --short --branch
```

4. 회사 OCP 로그인 상태를 확인한다.

```bash
oc whoami
oc whoami --show-server
```

5. Docker 연결을 확인한다.

```bash
docker version
```

6. 백엔드와 프론트 로컬 개발 서버를 다시 띄운다.

```bash
AIOPS_GATEWAY_MODE=read-only task be:dev
```

새 터미널에서:

```bash
task fe:dev
```

7. 로컬 콘솔은 아래 주소로 확인한다.

```text
http://localhost:9000/dashboards
```

## Ver.0.1.2 목표 1~6

### 1. 현재 클러스터 상태 요약

- 회사 OCP의 실제 상태를 로컬 콘솔에서 명확히 보여준다.
- 노드 Ready, CPU, 메모리, Pod 상태, ClusterOperator 상태, 주요 네임스페이스 상태를 요약한다.
- OpenShift 기본 대시보드와 Cywell AI 관제탑 화면을 헷갈리지 않게 분리한다.
- 신규 집계 API는 `/v1/aiops/overview`로 둔다.
- 기존 `/v1/cluster/summary`는 유지한다.

완료 기준:

- 샘플 데이터 없이 실제 OCP 데이터가 표시된다.
- 데이터를 못 읽으면 원인을 숨기지 않고 `권한 없음`, `연결 실패`, `데이터 없음`으로 표시한다.
- 화면에서 사용자가 현재 클러스터 상태를 바로 이해할 수 있다.

### 2. 이상 징후 자동 정리

- Alert, Degraded Operator, CrashLoopBackOff, ImagePullBackOff, Pending Pod, 재시작 급증, 업그레이드 차단 신호를 수집한다.
- 결과는 심각도와 운영 영향 기준으로 정렬한다.
- 사람이 읽는 상태값으로 변환한다: `정상`, `주의`, `확인 필요`, `위험`.

완료 기준:

- 이상 징후가 없으면 정상이라고 분명히 표시한다.
- 이상 징후가 있으면 근거 리소스, namespace, 원인 후보, 우선순위를 함께 보여준다.
- 가짜 데이터나 임의 추정은 금지한다.

### 3. 챗봇 RCA 고도화

- 질문 입력 시 바로 답하지 않고 먼저 증거 수집 계획을 세운다.
- Pod, Event, Alert, Operator, Node, Metrics 근거를 모아 RCA 답변을 만든다.
- 근거가 부족하면 추측하지 않고 `확인 불가`로 표시한다.
- 답변에는 원인 후보, 확인한 근거, 추가 확인 명령, 우선순위가 포함되어야 한다.

완료 기준:

- 답변이 일반 챗봇 문장 나열이 아니라 운영 분석 보고서처럼 보인다.
- RCA 근거가 화면에서 추적 가능하다.
- Lightspeed/OLS 응답 실패 시에도 실패 원인을 표시하고 UI가 깨지지 않는다.

### 4. 조치 후보 생성

- 실제 실행이 아니라 read-only 조치 후보를 만든다.
- 조치 후보는 위험도, 선행 확인, 예상 영향, 승인 필요 여부를 포함한다.
- 실행성 명령은 기본 비활성화한다.

금지:

- `oc apply`
- `oc delete`
- `oc patch`
- `oc scale`
- `oc exec`
- `task catalog:deploy`
- `task olm:install`
- `task kugnus:install`

완료 기준:

- 사용자가 실행 전에 무엇을 확인해야 하는지 알 수 있다.
- UI에 `제안만 함 / 실행 안 함`이 명확히 보인다.
- mutation disabled 상태가 유지된다.

### 5. 운영자용 대시보드 UX

- 첫 화면은 AIOps 관제탑처럼 보이게 구성한다.
- 기본 구성: 클러스터 상태, 이상 징후, RCA 근거, 조치 후보, 감사/대화 기록, 안전 정책.
- 좌측 히스토리 패널은 기본 접힘 상태다.
- 헤더, 입력창, 상태 배지, 사이드바는 Ver.0.1.1 UI polish 기준을 유지한다.

완료 기준:

- 버튼 의미가 모호하지 않다.
- 텍스트가 겹치거나 잘리지 않는다.
- 공간을 불필요하게 쪼개지 않는다.
- 사용자가 “이게 뭐 하는 기능이지?”라고 묻지 않아도 된다.

### 6. 검증 자동화

- API smoke, gateway pytest, frontend build, UI verifier, Prometheus/Thanos proxy check, AIOps scenario evaluator를 자동 검증 루프로 묶는다.
- 각 stage 결과는 `docs/Ver.0.1.2/stage-N-review.md`에 남긴다.
- 최종 보고에는 branch, head sha, 검증 명령, pass/fail 결과를 남긴다.

완료 기준:

- 기능을 만들었다는 말이 아니라 검증 결과가 남는다.
- 실패한 검증은 원인과 재작업 내용을 기록한다.
- 기존 회사 공용 리소스가 바뀌지 않았음을 확인한다.

## 검수 체계

각 단계는 최소 2회 검수를 거친다.

1. 구현 후보 작성
2. 자동 검증 1차
3. 초안 검수
4. 빠꾸 사항 수정
5. 자동 검증 2차
6. 최종 검수
7. stage 문서 저장
8. stage commit

### Reviewer A: 요구사항/제품성

- PDF 요구사항, 기존 0.1.1 산출물, 사용자 의도와 맞는지 검수한다.
- 기능이 실제 운영자에게 의미 있는지 확인한다.

### Reviewer B: 백엔드/안전성

- read-only 원칙, 인증정보 비노출, 기존 회사 리소스 미변경을 검수한다.
- API 실패 처리와 로그 근거를 확인한다.

### Reviewer C: UI/UX

- PatternFly/OpenShift 콘솔 질감과 관제 도구다운 밀도를 검수한다.
- 겹침, 잘림, 공간 낭비, 버튼 의미 불명확, 반응형 깨짐을 확인한다.

### Reviewer K: 김성욱봇 최종심

- 세상 깐깐한 운영자 관점으로 본다.
- 허접한 임시 UI, 가짜 데이터, 안 보이는 변화, 애매한 버튼, 근거 없는 답변, `나중에 고도화` 핑계는 즉시 fail 처리한다.
- A/B/C가 통과해도 김성욱봇이 fail이면 stage 완료가 아니다.

## 기본 테스트 목록

```bash
python3 -m pytest komsco-ai-gateway
```

```bash
cd komsco-ai-console-plugin
corepack yarn build
```

```bash
task kugnus:ui:verify
```

```bash
curl -k http://127.0.0.1:18080/healthz
```

```bash
curl -k http://127.0.0.1:18080/v1/cluster/summary
```

추가로 Prometheus/Thanos proxy가 살아있는지 `up`, `node_cpu_seconds_total`, range query를 확인한다.

## 하지 않을 것

- 회사 OCP에 새 런타임을 설치하지 않는다.
- 기존 회사 공용 챗봇과 ConsolePlugin을 교체하지 않는다.
- 기존 `komsco-ai`, `komsco-ai-dev`, `komsco-ai-console-plugin`, `lightspeed-console-plugin`을 수정하지 않는다.
- `.env`, token, kubeconfig, password를 커밋하지 않는다.
- 에러를 숨겨서 정상처럼 보이게 만들지 않는다.

## 다음 작업 시작점

다음 작업은 `feat/v.0.1.2` 브랜치를 만들고 Stage 1부터 시작한다.

```bash
git switch -c feat/v.0.1.2
```

Stage 1의 첫 구현 목표는 `/v1/aiops/overview`와 관제탑 첫 화면의 실제 클러스터 상태 카드다.
