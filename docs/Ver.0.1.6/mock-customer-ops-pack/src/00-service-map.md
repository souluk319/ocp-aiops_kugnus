# MockPay 운영센터 서비스 맵

문서 ID: MOCKPAY-SVCMAP-2026-06  
버전: v2026.06  
상태: fresh  
고객: MockPay 운영센터  
namespace: mockpay-prod, mockpay-observability, mockpay-batch

MOCKPAY_SERVICE_MAP marker.

## 1. 운영 목적

MockPay는 결제 승인, 정산 배치, 가맹점 callback을 운영하는 가상 고객사다. 이 문서는 OpenShift 운영자가 장애 탐지와 RAG 답변 근거를 연습할 수 있도록 만든 목업이다.

## 2. 서비스 구성

| 영역 | namespace | 주요 workload | SLO | 운영팀 |
| --- | --- | --- | --- | --- |
| 결제 승인 API | mockpay-prod | deploy/payment-api | 99.95% | Payment SRE |
| 가맹점 callback | mockpay-prod | deploy/merchant-callback | 99.90% | Payment SRE |
| 정산 배치 | mockpay-batch | cronjob/settlement-close | D+1 03:30 완료 | Batch Ops |
| 관측/알림 | mockpay-observability | deploy/mockpay-exporter | best effort | Platform Ops |

## 3. 운영 경계

- 운영자는 read-only 모드에서 먼저 `oc get`, `oc describe`, `oc logs --previous` 수준의 증거만 확인한다.
- 변경 조치는 승인 티켓, 변경창, Action Executor 경유가 모두 확인된 뒤에만 수행한다.
- Secret 원문, token, kubeconfig, private key는 답변과 evidence에 포함하지 않는다.
- 결제 승인 API 장애는 영업시간과 무관하게 P1로 분류한다.

## 4. 중요 식별자

| 항목 | 값 |
| --- | --- |
| 대표 route | https://pay.mockpay.example |
| 결제 API deployment | deployment/payment-api |
| callback deployment | deployment/merchant-callback |
| registry mirror | registry.mockpay.local/platform |
| 변경 티켓 prefix | MP-CHG |
| 장애 티켓 prefix | MP-INC |

## 5. 운영자 실습 질문

1. `payment-api`에서 CrashLoopBackOff가 발생하면 어떤 문서를 먼저 봐야 하는가?
2. `merchant-callback`의 ImagePullBackOff가 발생하면 registry mirror와 pull secret 중 무엇을 먼저 확인해야 하는가?
3. read-only 모드에서 답변 가능한 범위와 승인 후 조치 범위는 어떻게 나뉘는가?
