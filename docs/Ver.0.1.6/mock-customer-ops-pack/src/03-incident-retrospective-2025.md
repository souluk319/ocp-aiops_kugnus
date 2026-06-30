# MockPay 과거 장애 리포트 2025

문서 ID: MOCKPAY-RETRO-2025-11  
버전: v2025.11  
상태: stale  
고객: MockPay 운영센터  
namespace: mockpay-prod

MOCKPAY_STALE_2025_STORAGE_INCIDENT marker.

## 1. 사건 개요

2025-11-18 02:14 KST, `settlement-close` 배치가 NFS timeout으로 지연되었다. 당시에는 정산 배치 namespace가 `mockpay-prod`에 있었지만, 2026년부터 `mockpay-batch`로 분리되었다.

| 항목 | 내용 |
| --- | --- |
| incident | MP-INC-2025-1187 |
| 영향 | 정산 배치 42분 지연 |
| 주요 증상 | NFS timeout, batch retry 증가 |
| 현재 상태 | 참고용. 최신 runbook 아님 |

## 2. 원인

NFS backend maintenance와 batch retry 정책이 겹쳐 timeout이 증가했다. 애플리케이션 오류는 아니었고, node pressure도 주요 원인이 아니었다.

## 3. 당시 대응

운영팀은 batch retry 간격을 조정하고 NFS backend maintenance window를 분리했다. 이 절차는 현재 변경 승인 절차와 namespace 구조가 달라져 그대로 적용하면 안 된다.

## 4. 현재 사용 방법

이 문서는 stale evidence로만 사용한다. 답변은 반드시 최신 `MockPay 배포/변경 승인 절차` 또는 `MockPay 장애 대응 Runbook`을 우선해야 한다.

실습 포인트:

- stale 필터 없이 검색하면 이 문서가 기본 답변 근거로 쓰이면 안 된다.
- stale 필터를 명시하면 과거 장애 학습 자료로는 검색되어야 한다.
- 답변은 "과거 사례이며 현재 절차와 다를 수 있음"을 명시해야 한다.
