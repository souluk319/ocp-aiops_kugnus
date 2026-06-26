# Ver.0.1.6 Demo Readiness & RAG Docs Control

## 현재 판단

Ver.0.1.5까지는 WSL 네이티브 작업대, 로컬 console bridge, Gateway, RAG 파일 업로드, Docs 화면, UI verifier, 직접 실행 안내서까지 정리했다.

다음 단계는 기능을 무작정 늘리는 것이 아니라, **재부팅 후에도 10분 안에 환경을 복구하고 공식 시연 시나리오 한 사이클을 안정적으로 보여주는 것**이다.

## 목표

- 로컬 시연 환경을 한 명령 또는 짧은 순서로 복구한다.
- 공식 시연 시나리오를 한 사이클로 고정한다.
- Docs/RAG 화면을 제품 관점에서 설명 가능한 수준으로 다듬는다.
- 시연 전/중/후 체크리스트를 HTML 책자와 연결한다.
- 여전히 회사 OCP/OKD에 제품 설치나 배포는 하지 않는다.

## 기능 범위

1. **시연 Preflight 자동화**
   - `oc login`, Docker, RAG DB, Gateway, Console, Lightspeed, ActionExecutor, UI route 상태를 한 번에 점검한다.
   - 실패 시 단순 실패가 아니라 원인 계층을 보여준다.
   - 결과는 JSON과 HTML report로 남긴다.

2. **공식 시연 시나리오 1개 완성**
   - 운영자가 장애 징후를 확인한다.
   - Cywell AI에 질문한다.
   - Evidence/RAG/ToolPlan/Runbook 근거를 확인한다.
   - 조치 후보 또는 다음 명령을 확인한다.
   - 실제 실행은 승인 모드와 안전 경계를 지켜 수행한다.

3. **Docs/RAG 화면 제품화**
   - 업로드 문서 목록, 적재 상태, chunk preview, 검색 결과를 더 명확히 보여준다.
   - PBS에서 가져온 사용자 업로드 개념은 유지하되, 우리 제품에서는 OpenShift 운영 RAG에 맞게 정리한다.
   - raw 원문 전체 노출보다 redacted evidence/chunk preview를 우선한다.

4. **UI 마지막 정돈**
   - 헤더 상태칩, 실행 모드칩, Docs 탭, 새 대화 버튼, 전송/정지 버튼의 의미와 형태를 통일한다.
   - “예쁘다”가 아니라 “운영자가 무엇을 믿어도 되는지 바로 보인다”를 기준으로 검수한다.

5. **시연용 책자 보강**
   - 실행 전 점검
   - 시연 멘트
   - 실패 시 복구 루트
   - 현재 가능한 것과 말하면 안 되는 것

## 완료 기준

| 항목 | PASS 기준 |
| --- | --- |
| 환경 복구 | 재부팅 후 `task kugnus:demo:resume` 또는 정해진 짧은 순서로 로컬 콘솔이 열린다. |
| Preflight | HTML/JSON report에 모든 핵심 endpoint와 실패 원인이 표시된다. |
| 공식 시나리오 | 사용자가 같은 질문/흐름으로 장애 확인 -> 근거 -> 조치 후보까지 재현할 수 있다. |
| Docs/RAG | 업로드 문서가 적재되고, 검색/채팅 근거로 쓰였는지 화면에서 확인 가능하다. |
| UI | `task kugnus:ui:verify` 통과. 사용자 눈으로도 버튼 의미가 헷갈리지 않는다. |
| 안전 경계 | 회사 OCP/OKD 설치, OLM install, runtime deploy를 실행하지 않는다. |

## 검증 방법

```bash
cd /home/kugnus/cywell/ocp-aiops_kugnus
task kugnus:dev:doctor
task kugnus:runtime:smoke
task kugnus:rag:file-upload:smoke
task kugnus:rag:chat:smoke
task kugnus:ui:verify
```

추가 구현 후에는 0.1.6 전용 preflight task와 HTML report를 추가한다.

## 하지 않을 것

- `task catalog:deploy`
- `task catalog:release`
- `task catalog:runtime:apply`
- `task olm:deploy`
- `task olm:release`
- `task olm:install`
- `task kugnus:install`
- 회사 OCP/OKD 리소스에 대한 임의 `apply/delete/patch/scale/exec`
- `.env`, token, kubeconfig, password, 인증정보 commit

## 버전 상승 운영 규칙

앞으로 버전이 올라갈 때는 사용자가 매번 따로 말하지 않아도 아래 순서를 기본으로 한다.

1. 현재 브랜치 상태와 HEAD를 확인한다.
2. 현재 버전 작업물을 커밋하고 origin에 푸시한다.
3. 새 버전 브랜치 `feat/v.X.Y.Z`를 만든다.
4. 새 버전 폴더 `docs/Ver.X.Y.Z/`를 만든다.
5. 새 버전 목표/완료조건/검증방법/하지 않을 것을 산출물로 먼저 남긴다.
6. 그 브랜치에서 구현을 시작한다.

## 현재 기준점

- 시작 브랜치: `feat/v.0.1.6`
- 기준 커밋: `1351dfc complete ver.0.1.5 docs rag controls`
- 작업대: WSL native repo `/home/kugnus/cywell/ocp-aiops_kugnus`
- 시연 기준: 로컬 console `http://localhost:9000/dashboards`
