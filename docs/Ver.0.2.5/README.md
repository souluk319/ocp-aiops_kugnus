# v0.2.5 AIOps for OCP Reference Port

## 기준

- 현재 작업 브랜치: `feature/v0.2.5-aiops-for-ocp-port`
- 기준 상위 브랜치: `feature/v0.2.4-assistant-runbook-cards`
- 현재 repo 기준 HEAD: `8fe2aa3`
- 정답지 레포: `/home/kugnus/cywell/AIOps-Ref/aiops-ocp`
- 정답지 원격: `cywell-rnd-team/aiops-ocp`
- 정답지 브랜치/HEAD: `dev@a7bd16b`
- 제품명 기준: `AIOps for OCP`

## 왜 v0.2.5인가

v0.2.4는 JK 브랜치의 UI/Action Plan/검증 관점을 흡수하는 계획이었다. v0.2.5에서는 상위 엔지니어가 준 `aiops-ocp` 레포를 사실상의 정답지로 보고, 우리 repo에 안전하게 이식한다.

이번 변화는 단순 UI 개선이 아니다.

```text
기존: 콘솔 플러그인 + 챗봇/standalone 화면을 우리 방식으로 개선
v0.2.5: AIOps for OCP 포털 + Gateway 계약 + action/event/status 로직을 기준으로 재정렬
```

## 정답지에서 가져올 핵심

| 영역 | 정답지 위치 | 이식 방향 |
| --- | --- | --- |
| 독립 포털 | `komsco-ai-portal/` | 우리 repo에 별도 package로 이식 |
| Gateway 계약 | `GET /v1/cluster/summary`, `/v1/aiops/status`, `/v1/aiops/events` | 포털이 기대하는 API shape를 우선 계약으로 고정 |
| 운영 화면 | `komsco-ai-portal/src/App.tsx`, `styles.css` | `AIOps for OCP` 포털 경험을 1차 기준으로 채택 |
| Action 로직 | `komsco-ai-gateway/komsco_ai_gateway/main.py`, `aiops_core.py`, `action_executor.py` | natural action, registry, execution verification 비교 후 missing만 이식 |
| 로컬 개발 | `Taskfile.yml`, `scripts/dev-gateway-lightspeed.sh`, `komsco-ai-portal/vite.config.ts` | `task portal:dev`, gateway proxy, token 주입 경로 이식 |
| 문서/운영 계약 | `README.md`, `docs/*.md` | 이름과 실행 경로를 `AIOps for OCP`로 통일 |

## 산출물

- [aiops-for-ocp-porting-plan.md](./aiops-for-ocp-porting-plan.md)

## 절대 하지 않을 것

- `dev` 브랜치 직접 수정
- 회사 OCP/OKD 서버 배포
- OLM/Helm/NetworkPolicy/Route 즉시 변경
- `cp -r AIOps-Ref/aiops-ocp/* .` 식의 전체 덮어쓰기
- 보호 산출물 수정
- `evals/aiops-scenarios/*` 수정

## 권장 흐름

```text
0.2.5 계획 고정
  -> reference inventory
  -> portal package 이식
  -> gateway API 계약 이식
  -> action logic gap 이식
  -> launcher/console 연결
  -> local verification
  -> 이후 dev merge 여부 판단
```

