# Coolicons 기능 아이콘 적용 지침

작성일: 2026-06-25 KST

## 결론

브랜드 자산은 기존 파일을 유지한다.

- Catalog/FAB/product mark: `docs/Ver.0.1.0/design-assets/K_icon.png`
- Header brand logo: `komsco-ai-console-plugin/src/assets/komsco_logo.svg`

`coolicons`는 브랜드가 아니라 **기능 아이콘 전용 세트**로 사용한다. 새 기능 아이콘이 필요하면 먼저 coolicons에서 같은 톤의 아이콘을 고른다.

## 출처

- Figma community: `coolicons | Free Iconset Community`
- Figma URL: `https://www.figma.com/design/p0olQ2NbclE1GjTGfhMxdv/coolicons-%7C-Free-Iconset--Community-?node-id=17102-2265`
- GitHub source: `https://github.com/krystonschwarze/coolicons`
- Sprite source used: `Sprite/coolicons-sprite.svg`

## 적용 방식

전체 icon pack, webfont, sprite 파일을 bundle에 넣지 않는다.

현재 방식:

1. 공식 `coolicons-sprite.svg`에서 필요한 symbol만 선별한다.
2. `komsco-ai-console-plugin/src/components/coolicons.tsx`에 React SVG 컴포넌트로 옮긴다.
3. 기능 UI에서는 해당 컴포넌트만 import한다.

이 방식은 필요한 path만 bundle에 들어가므로 용량 증가가 작고, 외부 npm dependency도 늘리지 않는다.

## 현재 등록된 기능 아이콘

| Component | Coolicons source id | 사용 의도 |
| --- | --- | --- |
| `CoolMenuIcon` | `Hamburger_MD` | 좌측 대화/히스토리 패널 토글 |
| `CoolGlobeIcon` | `Globe` | 한/영 전환 |
| `CoolExpandIcon` | `Expand` | 전체화면 |
| `CoolShrinkIcon` | `Shrink` | 전체화면 해제 |
| `CoolLockIcon` | `Lock` | 창 크기 잠금 |
| `CoolLockOpenIcon` | `Lock_Open` | 창 크기 잠금 해제 |
| `CoolCloseIcon` | `Close_MD` | 닫기/제거 |
| `CoolPlusIcon` | `Add_Plus` | 새 채팅/자주 쓰는 질문 |
| `CoolPaperclipIcon` | `Paperclip_Attechment_Tilt` | 이미지 첨부 |
| `CoolPaperPlaneIcon` | `Paper_Plane` | 질문 전송 |
| `CoolStopIcon` | `Stop` | 응답 중지 |
| `CoolCaretDownIcon` | `Caret_Down_SM` | select/dropdown 표시 |
| `CoolChatDotsIcon` | `Chat_Dots` | Ask 모드 |
| `CoolSettingsIcon` | `Settings` | Troubleshooting 모드 |
| `CoolTerminalIcon` | `Terminal` | 조치 절차/실행 가능성 표시 |
| `CoolShieldCheckIcon` | `Shield_Check` | read-only/safety/action candidate |
| `CoolArrowDownIcon` | `Arrow_Down_SM` | 최신 답변으로 이동 |
| `CoolCopyIcon` | `Copy` | 코드/답변 복사 |
| `CoolUserCircleIcon` | `User_Circle` | 사용자 표시 |
| `CoolClockIcon` | `Clock` | 지난 대화/이력 |
| `CoolDesktopTowerIcon` | `Desktop_Tower` | Node/host 상태 |
| `CoolWarningIcon` | `Triangle_Warning` | 경고/이상 징후 |
| `CoolInfoIcon` | `Info` | system/info 상태 |
| `CoolListChecklistIcon` | `List_Checklist` | 점검 목록/절차 |
| `CoolMonitorIcon` | `Monitor` | 관제/콘솔 상태 |
| `CoolCheckIcon` | `Check` | 정상/완료 |

## 추가 절차

1. 최신 sprite를 임시 위치에 내려받는다.

```powershell
Invoke-WebRequest `
  -Uri "https://raw.githubusercontent.com/krystonschwarze/coolicons/master/Sprite/coolicons-sprite.svg" `
  -OutFile ".tmp-figma/coolicons-sprite.svg"
```

2. 필요한 source id를 검색한다.

```powershell
Select-String -Path .tmp-figma/coolicons-sprite.svg -Pattern 'id="Search|id="Filter|id="Database'
```

3. 필요한 symbol 내부의 `<path>`만 `coolicons.tsx`에 새 컴포넌트로 추가한다.
4. 이 문서의 "현재 등록된 기능 아이콘" 표에 source id와 사용 의도를 추가한다.
5. `corepack yarn build`와 UI verifier를 실행한다.

## 금지

- 브랜드 로고를 coolicons로 대체하지 않는다.
- 전체 webfont, 전체 sprite, 전체 PNG 폴더를 production bundle에 넣지 않는다.
- 같은 기능군 안에서 PatternFly icon과 coolicons를 이유 없이 섞지 않는다.
- 아이콘만 바꾸면서 aria-label, title, 버튼 동작을 바꾸지 않는다.
- 출처 없는 SVG를 임의로 복붙하지 않는다.

## 현재 적용 위치

- `komsco-ai-console-plugin/src/components/coolicons.tsx`
- `komsco-ai-console-plugin/src/components/AssistantLauncher.tsx`

대시보드 페이지(`AiopsPages.tsx`)는 아직 PatternFly 아이콘을 사용한다. 다음 UI 정리 단계에서 dashboard 카드 아이콘까지 coolicons로 맞출 수 있다.
