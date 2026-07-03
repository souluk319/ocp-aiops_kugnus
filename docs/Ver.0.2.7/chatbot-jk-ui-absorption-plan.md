# v0.2.7 Chatbot JK UI Absorption Plan

## Current Judgment

The v0.2.6 Assistant has the right functional contract, but the visual result is still too close to a patched console widget. The JK reference has a cleaner product shape: a dark operational header, a light dense workspace, runbook-first answers, and rails that feel integrated instead of bolted on.

## Reference Files

- `/home/kugnus/cywell/AIOps-Ref/aiops-ocp/demo/DESIGN.md`
- `/home/kugnus/cywell/AIOps-Ref/aiops-ocp/demo/ocp_chatbot_redesign.html`
- `/home/kugnus/cywell/AIOps-Ref/aiops-ocp/demo/ocp_chatbot_redesign_docked.png`
- `/home/kugnus/cywell/AIOps-Ref/aiops-ocp/demo/ocp_chatbot_redesign_expanded.png`

## Absorption Targets

| Area | v0.2.6 gap | v0.2.7 target |
| --- | --- | --- |
| Header | White utility bar feels generic and visually weak. | Dark command-center header with visible icon buttons and a thin blue accent. |
| History rail | Hard divider makes the left panel feel attached after the fact. | Soft rail surface, no strong vertical line, active history item with subtle inset. |
| Answer body | Assistant bubble still competes with runbook cards. | Assistant message shell becomes transparent; runbook cards carry the structure. |
| Runbook cards | Useful structure exists, but card hierarchy is not strong enough. | Dense operational cards with clear titles, left accent for action/verification/details. |
| Composer | Functional, but rectangular and slightly utilitarian. | Compact rounded composer with stable toolbar and clear send affordance. |
| Expanded mode | Context rail exists, but should read as part of the command workspace. | `chat column + context rail` with light rail and restrained divider. |

## Acceptance Criteria

| ID | Pass/Fail 기준 | 측정 방법 | Evidence |
| --- | --- | --- | --- |
| V027-01 | 헤더가 JK 기준 dark command bar로 보이고 KR/EN, 전체화면, 잠금, 닫기 아이콘이 보인다. | browser visual check | screenshot or manual note |
| V027-02 | 좌측 지난 대화 패널이 열렸을 때 강한 세로 경계선 없이 패널과 본문이 하나의 제품 표면처럼 보인다. | browser visual check | screenshot or manual note |
| V027-03 | assistant 답변은 큰 말풍선보다 런북 카드가 중심으로 보인다. | DOM/CSS check | CSS selectors + browser |
| V027-04 | 좁은 docked panel에서 긴 제목/ID가 가로 스크롤을 만들지 않는다. | browser visual check | manual note |
| V027-05 | 회사 서버 배포 산출물, OLM, Helm, protected artifacts는 수정하지 않는다. | `git diff --name-only` | diff evidence |

## Non-goals

- 회사 서버 배포
- OLM/catalog/package 변경
- Gateway action lifecycle 변경
- JK 코드를 그대로 복사하는 것

## Implementation Notes

The safest path is CSS-first:

1. Keep `AssistantLauncher.tsx` behavior intact.
2. Add one final `v0.2.7 JK chatbot UI absorption` override block to `assistant.css`.
3. Only edit JSX if a UI target cannot be achieved with existing class structure.
4. Run console plugin typecheck/build before claiming completion.
