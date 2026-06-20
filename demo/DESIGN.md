# OCP Chatbot Wrapper — UI Design Specification

## Direction
- Clean enterprise operations copilot, not a generic chat window.
- Strong visual presence without playful gradients or washed-out white surfaces.
- Progressive disclosure: summary first, commands and details inside expandable runbook cards.
- The assistant must feel context-aware and safe for production operations.

## Layout
- Default: 466px right-side floating panel, 16px viewport margin.
- Expanded: centered workspace, max 1240px, chat column plus 316px context rail.
- Header: 76px dark command-center bar.
- Composer: sticky bottom, compact quick prompts, read-only safety indicator.

## Tokens
```css
--ink-950: #0B1220;
--ink-900: #111827;
--surface: #FFFFFF;
--surface-2: #F7F9FC;
--line: #DBE3EE;
--blue-600: #2563EB;
--green: #16A34A;
--amber: #D97706;
--red: #DC2626;
--radius-md: 12px;
--radius-xl: 20px;
```

## Component rules
1. **Header**: dark neutral background, one thin blue accent line, status visible near the product name.
2. **User message**: small blue-tinted bubble, right aligned, never full-width.
3. **Assistant response**: no giant chat bubble. Use heading, summary, and runbook cards.
4. **Runbook card**: severity, scope, impact, commands, and actions. Only one card should be open by default.
5. **Commands**: dark monospace block with explicit copy control.
6. **Composer**: 44–52px visual height, primary blue send button, attachment button, quick prompts above.
7. **Expanded mode**: use the extra width for operational context rather than leaving blank space.
8. **Safety**: always show read-only/approval state and separate “check” actions from “change” actions.

## Typography
- `Inter, Pretendard, Noto Sans KR, system-ui`.
- Body 11–12px in compact mode; headings 18px; header title 14px.
- Monospace commands 9–10px in compact mode.

## Behavior
- Expand/collapse, close/launcher, accordion runbook, copy command, quick prompts.
- Responsive below 760px: full-screen sheet, hide the context rail.
