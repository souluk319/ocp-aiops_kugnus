# CAS 참고 자산 선별 이식 기록

## 현재 판단

`C:\Users\soulu\cywell\KOMSCO-AIOps_Agent`는 개인 CRC에 배포된 별도 제품이므로 그대로 복사하거나 배포 경로를 가져오지 않는다. 이번 repo에는 제품 개념과 검증 가능한 계약만 선별 이식한다.

## 가져온 것

- read-only first 운영 계약
  - `get`, `list`, `watch` 중심의 안전한 조회 계약
  - `create`, `update`, `patch`, `delete`, `exec`, `portforward`, `restart`, `scale`, `rollout` 금지 목록
- Evidence/RCA 상태 표현
  - OpenShift, metric, runbook, audit 근거 상태를 collected/missing으로 표시
  - 빠진 근거를 숨기지 않고 대시보드에 표시하는 제품 원칙
- OLM/OperatorHub 준비 관점
  - pass/fail 검증 가능한 패키지/카탈로그 산출물 사고방식
  - 단, CRC image, CRC namespace, CRC deploy 스크립트는 제외

## 가져오지 않은 것

- CRC 배포 스크립트
- CRC internal registry 이미지명
- `cywell-ai-sentinel` 패키지명과 CRD
- 기존 Lightspeed/ConsolePlugin 제거 또는 교체 로직
- `.env`, token, kubeconfig, 인증정보
- CAS static chatbot UI 모양

## 새 UI 방향

온라인 레퍼런스는 PatternFly와 OpenShift Console dynamic plugin 문법을 기준으로 삼는다.

- PatternFly dashboard/card/icon 계열의 조용한 운영형 카드 레이아웃
- 외부 이미지를 복사하지 않고 `@patternfly/react-icons` 기반 시각 자산 사용
- CAS와 같은 정적 챗봇 화면 느낌이 아니라 OpenShift Console 안에 붙는 관제 대시보드 느낌
- 첫 화면은 상태 요약, 근거 상태, 안전계약, 최근 실행/감사 흐름을 보여준다.

## 변경 파일

- `komsco-ai-gateway/komsco_ai_gateway/aiops_contracts.py`
- `komsco-ai-gateway/komsco_ai_gateway/main.py`
- `komsco-ai-gateway/tests/test_health.py`
- `komsco-ai-console-plugin/src/services/aiGateway.ts`
- `komsco-ai-console-plugin/src/pages/AiopsPages.tsx`
- `komsco-ai-console-plugin/src/pages/aiops-pages.css`

## 금지 기준

- 이 작업은 회사 OCP에 런타임 설치를 하지 않는다.
- `task olm:install`, `task olm:deploy`, `task olm:release`는 실행하지 않는다.
- 기존 회사 OCP의 `komsco-ai`, `komsco-ai-dev`, `openshift-lightspeed` 리소스를 교체하지 않는다.
- CAS 프로젝트의 CRC 배포 산출물을 현재 repo에 그대로 붙이지 않는다.
