# Mock Customer Scenario Readiness Audit

작성일: 2026-06-30 KST

## 한 줄 결론

사용자의 이해는 맞다.

AIOps는 단순히 AI 채팅창을 붙이는 것이 아니라, 특정 고객사가 가진 운영 문서, 장애 이력, 변경 정책, 현재 OpenShift 증거, 과거 이벤트, 로그, 메트릭을 한 흐름으로 묶어 운영자가 판단하고 조치 후보를 검토하게 만드는 환경이다.

현재 repo에는 MockPay 고객 문서와 시나리오 계약은 있다. 하지만 "콘솔 안에서 위험상황을 쉽게 연출하는 시나리오 주입 세트"는 아직 부족하다.

## 제품 방향 판정

시연용 제품을 따로 만들면 안 된다.

제품은 하나여야 한다. 대신 제품 안에 안전한 시나리오 주입 기능이 있어야 한다.

목표 흐름은 아래와 같다.

```text
고객 문서 PDF
  -> 파싱
  -> 전처리
  -> RAG 적재
  -> OpenShift 콘솔의 시나리오 선택
  -> demo namespace 또는 replay evidence 주입
  -> Gateway가 현재 증거와 고객 문서를 함께 수집
  -> Lightspeed/LLM이 RCA와 조치 후보를 작성
  -> 콘솔에서 위험상황, 근거, missing evidence, 승인 필요 조치를 확인
```

## 현재 있는 목업 자료

### 고객사

가상 고객사는 `MockPay 운영센터`다.

주요 namespace:

- `mockpay-prod`
- `mockpay-observability`
- `mockpay-batch`

주요 workload:

- `deployment/payment-api`
- `deployment/merchant-callback`
- `cronjob/settlement-close`

### 고객 문서 세트

위치:

```text
docs/Ver.0.1.6/mock-customer-ops-pack/
```

문서:

| 파일 | 역할 | 상태 |
| --- | --- | --- |
| `00-service-map` | 서비스, namespace, SLO, 운영팀 정의 | 있음 |
| `01-incident-runbook` | CrashLoopBackOff, ImagePullBackOff, 지연 알림 대응 | 있음 |
| `02-change-approval-policy` | 변경창, 승인 조건, read-only/approve-required 구분 | 있음 |
| `03-incident-retrospective-2025` | 과거 장애 리포트, stale evidence 테스트 | 있음 |

PDF 파일도 생성되어 있다.

```text
docs/Ver.0.1.6/mock-customer-ops-pack/pdf/
```

## 현재 검증된 것

### 시나리오 계약

실행:

```bash
task kugnus:scenario:verify
```

결과:

```json
{
  "scenarioCount": 13,
  "expectedScenarioCount": 13,
  "passed": 13,
  "failed": 0,
  "negativeControlsPassed": true
}
```

13번 MockPay 시나리오는 통과했다.

```text
mockpay-payment-oom-rca
```

질문:

```text
mockpay-prod namespace payment-api Pod가 어제 새벽에 재시작됐는데 OOM 관련 런북 찾아줘
```

검증된 evidence:

- `event`
- `snapshot`
- `pod_status`
- `runbook`

missing evidence:

- `clusteroperator`
- `metric`
- `pod_log`

이 부분은 좋다. 근거가 없는 항목을 억지로 확인했다고 말하지 않고 `missing evidence`로 남긴다.

### RAG 고객 문서 검색

기존 리포트:

```text
docs/Ver.0.1.6/rag-mock-customer-smoke-report.json
```

결과:

- 4개 PDF 업로드 성공
- PDF 한글 추출 성공
- raw content 미반환 확인
- CrashLoopBackOff 런북 검색 성공
- ImagePullBackOff pull secret 런북 검색 성공
- 변경 승인 정책 검색 성공
- stale 과거 리포트는 명시 필터가 없으면 숨김

이 부분도 좋다. "고객 문서를 RAG에 넣고 찾아오는" 기본 기능은 검증되어 있다.

## 현재 부족한 것

### 가장 큰 빈틈

문서와 시나리오 JSON은 있는데, 콘솔에서 실제 위험상황처럼 보이게 만드는 주입 세트가 부족하다.

현재 있는 것:

```text
MockPay 문서
MockPay 시나리오 JSON
RAG 검색 smoke report
offline scenario evaluator
```

아직 약한 것:

```text
mockpay-prod namespace 생성 manifest
payment-api Deployment manifest
OOMKilled 또는 CrashLoopBackOff를 안전하게 연출하는 fixture
Event replay 데이터
Metric replay 데이터
콘솔에서 시나리오를 선택하는 Scenario Lab UI
시나리오 실행 전/후 상태 확인 report
```

### 왜 이게 문제인가

지금 상태는 "AI가 이런 답을 해야 한다"는 계약 검증은 된다.

하지만 운영자가 콘솔에서 아래 흐름을 자연스럽게 실습하기에는 부족하다.

```text
MockPay 선택
  -> 결제 API 장애 상황 주입
  -> 콘솔 이상 징후 카드가 위험으로 변함
  -> Kugnus AI 질문 버튼 클릭
  -> Event / Pod 상태 / RAG 런북 / missing metric 확인
  -> 조치 후보는 승인 필요로 표시
  -> 시나리오 정리
```

이 흐름이 되어야 고객 맞춤 AIOps 시연이라고 말할 수 있다.

## 목업자료 품질 기준

앞으로 목업자료는 대충 만든 샘플 문서가 아니라 "고객 운영 복제 세트"여야 한다.

필수 구성:

| 구분 | 필요 자료 | 예시 |
| --- | --- | --- |
| 고객 구조 | 서비스 맵, namespace, workload, SLO | MockPay payment-api 99.95% |
| 운영 정책 | 변경창, 승인자, 금지 조치 | MP-CHG, MP-INC, read-only |
| 장애 런북 | 증상별 확인 순서 | OOMKilled, ImagePullBackOff |
| 과거 이력 | stale/fresh 구분되는 장애 리포트 | 2025 NFS timeout |
| 콘솔 상태 | 실제 또는 replay 가능한 Pod/Event/Alert | payment-api OOMKilled |
| RAG 연결 | 어떤 질문이 어떤 문서를 찾아야 하는지 | OOM 질문 -> incident runbook |
| 안전 경계 | 실행 가능/불가 조치 구분 | 승인 전 scale/patch 금지 |
| 정리 절차 | 시나리오 후 cleanup | namespace 삭제 또는 fixture reset |

## 다음 구현 순서

가장 먼저 해야 할 일은 "MockPay Scenario Lab"이다.

### 1단계: MockPay fixture manifest

새 디렉터리 후보:

```text
openshift/scenarios/mockpay-payment-oom/
```

포함할 파일:

```text
namespace.yaml
payment-api-deployment.yaml
merchant-callback-deployment.yaml
mock-events.yaml 또는 event-replay.json
scenario.yaml
cleanup.yaml
```

목표:

- 실제 회사 클러스터를 망가뜨리지 않는 demo namespace 사용
- read-only 분석이 가능한 Pod/Event/label/annotation 구성
- 위험상황이 콘솔 anomaly board에 보이게 하는 label 포함

### 2단계: Scenario registry

새 파일 후보:

```text
evals/aiops-scenarios/scenario-registry.json
```

역할:

- 시나리오 id
- 고객사
- namespace
- 관련 문서
- 필요한 fixture
- 주입 방식
- 정리 방식
- 기대 evidence chain

### 3단계: Gateway replay endpoint

제품 경로에 붙일 기능:

```text
POST /v1/scenarios/replay
GET /v1/scenarios
POST /v1/scenarios/{id}/cleanup
```

초기에는 실제 리소스 변경보다 replay evidence부터 시작한다.

### 4단계: Console Scenario Lab

콘솔에 필요한 화면:

```text
고객 선택: MockPay
상황 선택: 결제 API OOM 재시작
사전 확인: 만들 namespace와 리소스 표시
주입 실행: replay 또는 demo namespace fixture
질문 보내기: Kugnus AI로 RCA 분석
정리 실행: cleanup
```

## 최종 판정

현재 MockPay 자료는 "RAG 검색과 시나리오 계약 검증용"으로는 합격이다.

하지만 "고객 맞춤 AIOps 제품 시연용"으로는 아직 부족하다.

부족한 이유는 문서 내용이 아니라, 문서와 콘솔 위험상황을 이어 주는 주입/재생 계층이 약하기 때문이다.

다음 작업은 문서를 더 예쁘게 쓰는 것이 아니라, MockPay 시나리오를 콘솔에서 선택하고 주입하고 정리할 수 있는 제품 기능으로 만드는 것이다.
