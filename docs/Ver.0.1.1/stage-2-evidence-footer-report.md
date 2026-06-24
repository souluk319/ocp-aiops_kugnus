# Ver.0.1.1 Stage 2 Evidence Footer Report

작성 기준일: 2026-06-24 KST  
브랜치: `feat/v.0.1.1`  
기준 문서: `reviewer-gate-protocol.md` Stage 2

## 목표

채팅 답변을 받은 사용자가 답변 본문 바로 아래에서 다음을 확인할 수 있게 한다.

- 답변에 연결된 RCA Context trace id 또는 digest
- 수집된 evidence 개수와 대표 reference
- 추가 확인이 필요한 missing evidence
- 복사 시 답변과 evidence 추적 정보가 함께 남는지

## 구현 요약

- `AssistantLauncher.tsx`
  - `rca_context` stream event를 수신하면 마지막 assistant message에 `evidenceFooter`를 붙인다.
  - collected evidence, failed evidence, missing evidence를 분리한다.
  - footer 표시 전 token/email/token-like string은 redaction 처리한다.
  - copy 버튼은 답변 본문 뒤에 `[Evidence]` 블록을 추가한다.

- `evidenceDisplay.ts`
  - evidence footer/copy text에 들어가는 문자열 redaction 규칙을 별도 util로 분리했다.
  - `admin`, `kubeadmin`, email, `Bearer`, OpenShift `sha256~` token, JWT, AWS access key, key-value API key/token/secret/password, 일반 token-like/API key prefix를 표시 전 제거한다.
  - footer용 `safeEvidenceText`는 96자 제한을 유지하고, clipboard용 `redactSensitiveText`는 본문 길이를 유지한 채 민감정보만 제거한다.

- `assistant.css`
  - 답변 하단에 작은 evidence footer를 추가했다.
  - 수집 evidence는 green tone pill, 추가 확인 필요 evidence는 amber tone block으로 구분한다.
  - 답변 본문을 밀어내지 않도록 compact spacing과 높이 제한을 검증 기준으로 둔다.

- `verify-kugnus-ui.mjs`
  - assistant message별 evidence footer를 읽어 검증한다.
  - trace id/digest, 수집/누락 구분, footer 높이, 민감정보 redaction을 자동 검사한다.
  - evidence 없는 답변과 evidence 있는 답변을 구분해 검사한다.
  - 답변 복사 버튼을 눌러 `[Evidence]` 블록이 포함되고 민감정보가 없는지 확인한다.
  - evidence footer가 보이는 스크린샷을 저장한다.
  - `/dashboards` 로컬 콘솔에서 stale CDP target을 잡으면 이미 로드된 정상 Cywell AI tab으로 복구해 검증 재현성을 확보한다.
  - background tab에서 `requestAnimationFrame`이 멈추는 경우를 피하기 위해 resize drag 검증 대기는 `setTimeout` 기반으로 둔다.

- `verify-evidence-display.cjs`
  - redaction helper에 악성/민감 문자열을 직접 주입해 표시 전 제거 여부를 검증한다.
  - 답변 본문/코드블록 복사처럼 긴 clipboard payload도 직접 주입해 민감정보 제거와 정상 문장 보존을 함께 검증한다.

## 하지 않은 것

- Gateway evidence schema는 Stage 1 결과를 사용한다.
- 새 backend API를 추가하지 않았다.
- 회사 OCP 공용 `komsco-ai-console-plugin`, `lightspeed-console-plugin`, 공용 namespace는 건드리지 않았다.
- `.env`, token, kubeconfig, password는 읽거나 커밋하지 않는다.

## Acceptance Criteria

| 기준 | 측정 방법 | 결과 |
| :--- | :--- | :--- |
| 답변 하단에 evidence footer가 표시된다 | UI verifier가 `.komsco-ai__evidence-footer` 확인 | PASS |
| trace id 또는 digest가 유지된다 | `data-evidence-context-id`, `data-evidence-digest` 확인 | PASS |
| 수집 evidence와 missing evidence가 분리된다 | collected/missing pill 및 missing block 확인 | PASS |
| footer가 답변을 과도하게 밀어내지 않는다 | footer height <= 140px | PASS |
| evidence 없는/중지 답변과 evidence 있는 답변의 UI 차이가 명확하다 | no-evidence stopped answer와 collected ref footer를 각각 확인 | PASS |
| token/email/admin 같은 민감 표시가 노출되지 않는다 | helper 주입 검사 + footer/copy text regex 검사 | PASS |
| composer, sidebar, fullscreen, scroll, stop button 회귀 없음 | 전체 UI verifier | PASS |

## Evidence 없음/있음 UI 차이

| 상태 | 기대 UI | 판정 방법 |
| :--- | :--- | :--- |
| Evidence 없음 또는 답변 중지 | evidence footer가 없거나 `수집 0`/reference 0 상태로 표시된다. 성공 evidence처럼 보이지 않아야 한다. | `assistant distinguishes no-evidence stopped answer from collected evidence footer` |
| Evidence 있음 | footer에 `수집 N`, `추가 확인 M`, `contextId` 또는 digest, 대표 evidence ref가 표시된다. | `assistant answer exposes compact evidence footer with trace id`, `assistant evidence footer separates collected and missing evidence without crowding answer` |

## Screenshot Evidence

| 파일 | 용도 | 상태 |
| :--- | :--- | :--- |
| `.tmp-aiops-kugnus-ui-verify-fullscreen.png` | evidence footer 없는 초기/빈 대화 상태, fullscreen/sidebar 회귀 확인 | 생성 확인 |
| `.tmp-aiops-kugnus-ui-verify-resize.png` | floating assistant resize 상태에서 composer/sidebar 회귀 확인 | 생성 확인 |
| `.tmp-aiops-kugnus-ui-verify-evidence-footer.png` | evidence footer가 보이는 답변 상태 확인 | 생성 확인 |

## 검증 결과

- Frontend build
  - 명령: `corepack yarn build`
  - 결과: PASS
  - 특이사항: vendor chunk size warning 1건 존재. Stage 2 기능 실패는 아님.

- Evidence display redaction probe
  - 명령: `node scripts/verify-evidence-display.cjs`
  - 위치: `komsco-ai-console-plugin`
  - 결과: PASS
  - 확인 대상: `admin`, `kubeadmin`, email, `Bearer`, `sha256~`, JWT, API key/token-like string

- UI verifier
  - 명령: `node scripts/verify-kugnus-ui.mjs`
  - 환경:
    - `KUGNUS_UI_WINDOWS_DELEGATED=1`
    - `KUGNUS_CHROME_DEBUG_PORT=9225`
    - `KUGNUS_UI_URL=http://localhost:9000/dashboards`
  - 결과: `64 checked, 0 failed`
  - 검증 기준: 로컬 OpenShift Console `/dashboards` 위 floating assistant 기준
  - 주의: 이 검증은 회사 서버 배포가 아니라 local console bridge + local plugin/gateway 검증이다.

## Reviewer FAIL 대응 기록

| 이슈 | 원인 | 조치 | 재검증 |
| :--- | :--- | :--- | :--- |
| Backend/Safety FAIL | `api_key=shortsecret`, `x-api-key: shortsecret`, `token=shortsecret`, `AKIA...` 형태가 redaction helper를 통과할 수 있었다. | key-value secret/API key/token/password redaction과 AWS access key redaction을 추가했다. | `node scripts/verify-evidence-display.cjs` PASS |
| Frontend/UX FAIL | CDP에 stale `/dashboards` tab이 쌓여 새 verifier target이 `.komsco-ai` root 없는 콘솔 초기화 실패 상태를 잡을 수 있었다. | loaded Cywell AI tab recovery, refresh recovery, resize drag wait 안정화를 추가했다. | `/dashboards` UI verifier `64 checked, 0 failed` |
| Backend/Safety 재FAIL | message copy와 code-block copy가 raw answer/code text를 clipboard에 쓸 수 있었다. | `redactSensitiveText`를 추가하고 message copy/code-block copy 모두 clipboard write 전에 적용했다. | `node scripts/verify-evidence-display.cjs` PASS, `corepack yarn build` PASS |
| Backend/Safety 2차 재FAIL | kubeconfig-shaped `client-key-data`, `client-certificate-data`, `certificate-authority-data` base64 값이 clipboard redaction을 통과할 수 있었다. | kubeconfig credential key redaction과 base64 certificate/private-key probe를 추가했다. | `node scripts/verify-evidence-display.cjs` PASS, `corepack yarn build` PASS |
| Product/Safety 최종 재FAIL | multiline `client-key-data: |` redaction이 payload까지 포함한 `$1`을 다시 내보낼 수 있었다. | multiline kubeconfig redaction을 generic single-line rule보다 먼저 적용하고 payload capture를 제거했다. | multiline probe 포함 `node scripts/verify-evidence-display.cjs` PASS, `corepack yarn build` PASS |
| Backend/Safety 최종 재FAIL | `Authorization: Bearer <token>`에서 generic `authorization` rule이 먼저 적용되어 Bearer token tail이 남을 수 있었다. | Bearer redaction을 generic key-value rule보다 먼저 적용하고 Authorization/Bearer clipboard probe를 추가했다. | `node scripts/verify-evidence-display.cjs` PASS, `corepack yarn build` PASS |

## Reviewer Gate 기록

Reviewer A/B/C 검수는 이 파일, 코드 diff, 빌드 결과, UI verifier 결과를 기준으로 수행한다.

| Reviewer | 관점 | 결과 | 메모 |
| :--- | :--- | :--- | :--- |
| A | Product/Requirements | PASS | screenshot inspection 및 evidence 없음/있음 UI 차이 문서화 반영 완료 |
| B | Backend/Safety | 2차 수정 후 재검수 대기 | key-value/API key/token redaction 누락과 message/code clipboard raw copy 누출 수정, 주입 테스트 PASS |
| C | Frontend/UX | 수정 후 재검수 대기 | 초기 FAIL 원인인 `/dashboards` CDP stale target 재현성 문제 수정, UI verifier PASS |

## 다음 Stage

Stage 3는 RAG/Runbook Storage Contract + Search Skeleton이다.
Stage 2가 Reviewer A/B/C 모두 PASS한 뒤에만 진행한다.
