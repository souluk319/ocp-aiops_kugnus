# MockPay 장애 대응 Runbook

문서 ID: MOCKPAY-RUNBOOK-2026-06  
버전: v2026.06  
상태: fresh  
고객: MockPay 운영센터  
namespace: mockpay-prod

MOCKPAY_CRASHLOOP_RUNBOOK marker.  
MOCKPAY_IMAGEPULL_RUNBOOK marker.

## 1. 공통 원칙

장애 대응은 관측, 원인 후보, read-only 검증, 승인 필요 조치 후보 순서로 진행한다. 운영자는 먼저 변경하지 않는 명령으로 증거를 모은다.

| 단계 | 확인 항목 | 예시 증거 |
| --- | --- | --- |
| 관측 | Pod 상태, restart count, recent events | waiting.reason, lastState, event reason |
| 원인 후보 | 이미지, 설정, 의존 서비스, probe | ImagePullBackOff, CrashLoopBackOff, Readiness failed |
| read-only 검증 | describe/logs/events | container message, previous log tail |
| 승인 필요 조치 | 설정 변경, rollout, secret 교체 | MP-CHG 티켓 필요 |

## 2. CrashLoopBackOff 대응

대상 예시: `deployment/payment-api`, namespace `mockpay-prod`.

우선순위:

1. `oc describe pod`로 `waiting.reason`, `message`, `lastState.terminated.reason`을 확인한다.
2. `oc logs --previous`로 직전 종료 로그를 확인한다.
3. 최근 배포 또는 config 변경 티켓 `MP-CHG`가 있었는지 확인한다.
4. readiness/liveness probe 실패인지, 프로세스 자체 종료인지 분리한다.

원인 후보:

- 새 config key 누락
- 외부 승인사 sandbox endpoint DNS 실패
- JVM heap 또는 container memory limit 불일치
- DB connection pool 설정 오류

read-only 답변 예시:

`payment-api`는 CrashLoopBackOff 상태이며, 직전 종료 로그와 event message를 확인해야 한다. 지금 단계에서는 설정 변경이나 재배포를 수행하지 않는다.

## 3. ImagePullBackOff 대응

대상 예시: `deployment/merchant-callback`, namespace `mockpay-prod`.

MOCKPAY_PULL_SECRET_CHECK marker.

확인 순서:

1. event에서 image 이름과 tag를 확인한다.
2. registry mirror `registry.mockpay.local/platform` 접근 장애인지 확인한다.
3. pull secret 참조가 workload service account에 연결되어 있는지 확인한다.
4. 직전 변경 티켓 `MP-CHG`에서 image tag 변경이 있었는지 확인한다.

운영 메모:

- `ErrImagePull` 직후 `ImagePullBackOff`로 바뀌면 registry 또는 secret 문제 가능성이 높다.
- 새 tag가 존재하지 않는 경우 배포 승인자에게 rollback 후보를 요청한다.
- Secret 값 원문은 조회하거나 답변에 쓰지 않는다.

## 4. 지연 알림 대응

`payment-api` P95 latency가 1초를 넘으면 다음을 확인한다.

- node pressure
- upstream 승인사 응답 지연
- connection pool saturation
- 최근 autoscaling 정책 변경

지연만 있고 error rate가 낮으면 P2, 결제 승인 실패율이 같이 오르면 P1로 승격한다.
