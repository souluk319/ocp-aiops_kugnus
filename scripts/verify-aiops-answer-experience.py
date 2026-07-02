#!/usr/bin/env python3
"""Verify the Ver.0.2.2 AIOps answer experience contract."""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "Ver.0.2.2" / "aiops-answer-experience-contract.md"
GATEWAY_MAIN = ROOT / "komsco-ai-gateway" / "komsco_ai_gateway" / "main.py"
AIOPS_CONTRACTS = ROOT / "komsco-ai-gateway" / "komsco_ai_gateway" / "aiops_contracts.py"
GATEWAY_TESTS = ROOT / "komsco-ai-gateway" / "tests" / "test_health.py"
ASSISTANT = ROOT / "komsco-ai-console-plugin" / "src" / "components" / "AssistantLauncher.tsx"
ASSISTANT_PROGRESS = (
    ROOT / "komsco-ai-console-plugin" / "src" / "components" / "AssistantProgressTimeline.tsx"
)
ASSISTANT_CONSTANTS = ROOT / "komsco-ai-console-plugin" / "src" / "components" / "assistant.constants.tsx"
ASSISTANT_TYPES = ROOT / "komsco-ai-console-plugin" / "src" / "components" / "assistant.types.ts"
ASSISTANT_CSS = ROOT / "komsco-ai-console-plugin" / "src" / "components" / "assistant.css"
PAGES = ROOT / "komsco-ai-console-plugin" / "src" / "pages" / "AiopsPages.tsx"
DASHBOARD_SECTIONS = (
    ROOT / "komsco-ai-console-plugin" / "src" / "pages" / "AiopsDashboardSections.tsx"
)
DOCS_SECTIONS = ROOT / "komsco-ai-console-plugin" / "src" / "pages" / "AiopsDocsSections.tsx"
PAGES_CSS = ROOT / "komsco-ai-console-plugin" / "src" / "pages" / "aiops-pages.css"
GATEWAY_SERVICE = ROOT / "komsco-ai-console-plugin" / "src" / "services" / "aiGateway.ts"
EVIDENCE_DISPLAY = ROOT / "komsco-ai-console-plugin" / "src" / "utils" / "evidenceDisplay.ts"
GITIGNORE = ROOT / ".gitignore"


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def require(path: Path, needle: str, label: str) -> None:
    text = read(path)
    if needle not in text:
        raise SystemExit(f"FAIL {label}: missing {needle!r} in {rel(path)}")
    print(f"PASS {label}")


def reject(path: Path, needle: str, label: str) -> None:
    text = read(path)
    if needle in text:
        raise SystemExit(f"FAIL {label}: forbidden {needle!r} in {rel(path)}")
    print(f"PASS {label}")


def require_in_text(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(f"FAIL {label}: missing {needle!r}")
    print(f"PASS {label}")


def reject_in_text(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise SystemExit(f"FAIL {label}: forbidden {needle!r}")
    print(f"PASS {label}")


def text_between(path: Path, start: str, end: str) -> str:
    text = read(path)
    start_index = text.find(start)
    if start_index < 0:
        raise SystemExit(f"FAIL source slice: missing start marker {start!r} in {rel(path)}")
    end_index = text.find(end, start_index)
    if end_index < 0:
        raise SystemExit(f"FAIL source slice: missing end marker {end!r} in {rel(path)}")
    return text[start_index:end_index]


def require_ignored(path: str, label: str) -> None:
    result = subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(f"FAIL {label}: {path} is not ignored")
    print(f"PASS {label}")


def main() -> None:
    require(CONTRACT, "Tool Plan JSON은 내부 작전서", "contract locks internal tool plan")
    require(CONTRACT, "원인 후보", "contract requires human RCA section")
    require(CONTRACT, "확인한 증적", "contract requires evidence section")
    require(CONTRACT, "권장 조치", "contract requires remediation section")
    require(CONTRACT, "추가 확인", "contract requires follow-up section")
    require(CONTRACT, "재발 방지", "contract requires prevention section")
    require(CONTRACT, "읽기 전용", "contract keeps read-only mode")
    require(CONTRACT, "실행 가능", "contract keeps execute mode")
    require(CONTRACT, "실행 무제한", "contract keeps unrestricted mode")
    require(CONTRACT, "UI 선택은 항상 가능", "contract forbids blocking unrestricted selection")
    require(CONTRACT, "pod_screen_rca", "contract locks current screen Pod RCA promotion")
    require(CONTRACT, "새로고침해도 현재 대화와 최근 대화 목록이 복원", "contract keeps refresh-safe chat history")
    require(CONTRACT, "첨부 이미지 원본 데이터", "contract forbids storing raw attachment data in UI history")
    require(CONTRACT, "evidence-grounded-pod-rca-v0.2.2", "contract locks grounded Pod RCA renderer")
    require(CONTRACT, "본문을 꽉 채우는 embedded/lockOpen 챗봇", "contract forbids embedded dashboard chatbot")
    require(CONTRACT, "관제탑 기본 화면은 내부 디버그 패널을 렌더링하지 않는다", "contract forbids dashboard debug panels")
    require(CONTRACT, "중복 후보를 접은 상위 후보만", "contract requires compact action candidates")
    require(CONTRACT, "가로 스크롤 표 대신 카드 목록", "contract requires mobile-readable records")

    require(AIOPS_CONTRACTS, '"answerExperience"', "RcaContext carries answer experience")
    require(AIOPS_CONTRACTS, '"queryPlan"', "RcaContext carries human query plan")
    require(
        AIOPS_CONTRACTS,
        '"mustNotExposeRawToolPlanInDefaultAnswer": True',
        "RcaContext forbids raw plan in default answer",
    )
    require(AIOPS_CONTRACTS, '"supportedExecutionModes"', "RcaContext lists supported modes")
    require(AIOPS_CONTRACTS, '"toolPlanDigest"', "RcaContext stamps tool plan digest")
    require(AIOPS_CONTRACTS, 'task_type = "pod_screen_rca"', "ToolPlan promotes current Pod screen")

    require(GATEWAY_MAIN, "Tool Plan JSON은 Gateway 내부 작전서", "Gateway prompt treats ToolPlan as internal")
    require(GATEWAY_MAIN, "raw Tool Plan JSON이나 raw RcaContext JSON을 출력하지 마세요", "Gateway prompt hides raw JSON")
    require(GATEWAY_MAIN, "should_collect_pod_status_evidence_for_request(req)", "Gateway collects Pod evidence from page context")
    require(GATEWAY_MAIN, "단순 절차 안내로 끝내지 마세요", "Gateway prompt forbids procedure-only screen answers")
    require(GATEWAY_MAIN, "def build_grounded_aiops_answer", "Gateway has grounded answer renderer")
    require(GATEWAY_MAIN, 'task_type == "pod_screen_rca"', "Gateway grounds current Pod screen answers")
    require(GATEWAY_MAIN, "page_context_is_pod_workload(req)", "Gateway limits grounded renderer to current Pod screen context")
    require(GATEWAY_MAIN, "source\": \"gateway_evidence_renderer\"", "Gateway streams grounded evidence answer")
    require(GATEWAY_MAIN, "evidence-grounded-pod-rca-v0.2.2", "Gateway stamps grounded answer contract")
    require(GATEWAY_MAIN, "조치 레코드가 필요하면 실행 가능 모드에서 `조치 계획 생성`을 명시", "Gateway states when no action record was created")
    require(GATEWAY_MAIN, '"answerMode": answer_mode', "transcript stores answerMode")
    require(GATEWAY_MAIN, '"assistantAnswer"', "transcript stores assistantAnswer")
    require(GATEWAY_MAIN, '"toolPlanDigest": tool_plan_digest', "transcript stores toolPlanDigest")
    require(GATEWAY_MAIN, '"rcaContextDigest": rca_context_digest', "transcript stores rcaContextDigest")
    require(GATEWAY_MAIN, '"evidenceRefs"', "transcript stores evidenceRefs")
    require(GATEWAY_MAIN, '"human_rca"', "transcript names human RCA answer mode")
    require(GATEWAY_MAIN, "조회 계획:", "action text uses human query plan wording")
    reject(GATEWAY_MAIN, 'f"- Tool Plan:', "default action text does not print Tool Plan line")

    require(ASSISTANT_TYPES, "export type EvidenceFooterQueryStep", "console defines query step type")
    require(ASSISTANT, "EvidenceFooterQueryStep", "console uses query step type")
    require(ASSISTANT, "queryPlan", "console builds queryPlan for Evidence footer")
    require(ASSISTANT, "근거 상세보기", "console has Evidence detail toggle")
    require(ASSISTANT, "조회 계획", "console labels human query plan")
    require(ASSISTANT, "stripDefaultEvidenceAppendix", "console hides raw RAG appendix from default chat body")
    require(ASSISTANT, "extractRagAppendixRefs", "console moves raw RAG appendix into evidence detail")
    require(ASSISTANT, "문서 근거", "console labels RAG appendix as document evidence")
    require(ASSISTANT, "compactEvidenceTypeSummary", "console keeps evidence footer compact by default")
    require(ASSISTANT, "evidenceStepStatusLabel", "console translates evidence detail statuses")
    require(ASSISTANT, "rcaContextPhaseLabel", "console translates RCA stream phases")
    require(ASSISTANT_PROGRESS, "답변 근거 연결 완료", "console uses product wording for RCA phase")
    require(ASSISTANT_PROGRESS, "productProgressText", "console sanitizes stored progress wording")
    require(ASSISTANT, "normalized === 'not_attempted'", "console hides raw not_attempted status")
    reject(ASSISTANT, "RCA 문맥 연결:", "console does not expose raw RCA phase wording")
    reject(ASSISTANT, "RCA Context digest", "console does not expose raw RCA context digest wording")
    reject(ASSISTANT, "evidence refs", "console does not expose raw evidence refs wording")
    reject(ASSISTANT, "<code>{ref.evidenceId", "console does not show evidence ids in default footer")
    require(
        ASSISTANT_CONSTANTS,
        "현재 화면의 대상 리소스에 대해 가능한 안전 조회를 실행",
        "quick prompt asks AIOps to run safe checks",
    )
    require(ASSISTANT_CSS, "komsco-ai__evidence-query-plan", "console styles query plan detail")
    require(ASSISTANT_CSS, "komsco-ai__evidence-summary", "console styles compact evidence summary")
    require(ASSISTANT_CSS, "komsco-ai__rag-source-list", "console styles moved RAG appendix detail")
    require(PAGES, "원본 Tool Plan JSON", "audit page keeps raw Tool Plan JSON")
    require(PAGES, "RCA Context JSON", "audit page keeps raw RCA Context JSON")
    require(
        PAGES,
        "<AssistantLauncher draftPrompt={assistantDraftPrompt} onRunComplete={data.refresh} />",
        "dashboard keeps AssistantLauncher mount point; visual FAB is not proven by this static check",
    )
    reject(PAGES, 'className="komsco-ai-page__assistant-stage"', "dashboard does not render full-width assistant stage")
    reject(PAGES, "defaultOpen\n          draftPrompt={assistantDraftPrompt}\n          embedded\n          lockOpen", "dashboard does not force embedded locked chatbot")
    reject(PAGES_CSS, "komsco-ai-page__assistant-stage", "dashboard CSS does not keep embedded assistant stage")
    reject(PAGES_CSS, "komsco-ai-page__assistant-quick-toggle", "dashboard CSS does not keep duplicate quick chatbot button")
    dashboard = text_between(PAGES, "export const AiopsDashboardPage", "export const AiopsDocsPage")
    require_in_text(dashboard, "관제탑", "dashboard remains the control tower route")
    require_in_text(
        dashboard,
        "AssistantLauncher",
        "dashboard keeps AssistantLauncher wiring; visual FAB requires browser proof",
    )
    reject_in_text(dashboard, "<ToolPlanPanel", "dashboard does not render ToolPlanPanel")
    reject_in_text(dashboard, "<RcaContextPanel", "dashboard does not render RcaContextPanel")
    reject_in_text(dashboard, "<AdapterBoard", "dashboard does not render AdapterBoard")
    reject_in_text(dashboard, "<CapabilityBoard", "dashboard does not render CapabilityBoard")
    reject_in_text(dashboard, "<RecordTable", "dashboard does not render raw record table")
    reject_in_text(dashboard, "Lightspeed stream", "dashboard does not show stream jargon")
    reject_in_text(dashboard, "controlled_execution", "dashboard does not show raw safety mode")

    require(DASHBOARD_SECTIONS, "ACTION_CANDIDATE_DISPLAY_LIMIT", "dashboard bounds visible action candidates")
    require(DASHBOARD_SECTIONS, "rankActionCandidatesForDisplay", "dashboard deduplicates action candidates")
    require(DASHBOARD_SECTIONS, "중복 후보", "dashboard tells operator repeated candidates are collapsed")
    require(DASHBOARD_SECTIONS, "isImagePullBackOffCandidate", "dashboard blocks unsafe ImagePullBackOff eviction")
    require(PAGES, "mode === 'execute'", "dashboard maps execute mode before display")
    require(PAGES, "return '실행 가능';", "dashboard displays execute mode in Korean")
    reject(PAGES, "Cywell AI 복구 계획", "dashboard does not label candidates as recovery plan")
    require(DASHBOARD_SECTIONS, "normalizeFindingDisplayText", "dashboard repairs redacted resource placeholders")
    require(DASHBOARD_SECTIONS, "최근 1시간 재시작 증가", "dashboard displays restart metric evidence in Korean")
    require(EVIDENCE_DISPLAY, "(?=.*[.~+/=])", "redaction avoids Kubernetes and metric identifier names")
    reject(EVIDENCE_DISPLAY, "(?=.*[._~+/=-])", "redaction does not treat long hyphenated resource names as tokens")
    require(DOCS_SECTIONS, "고객 문서 저장소", "docs page uses Korean operator title")
    reject(DOCS_SECTIONS, "LLM Wiki", "docs page does not expose wiki jargon as title")
    require(PAGES, "ChatTranscriptList", "audit uses mobile-readable chat cards")
    require(PAGES, "RecordList", "audit/execution uses mobile-readable record cards")
    require(PAGES_CSS, "komsco-ai-page__record-list", "record cards are styled")
    require(PAGES_CSS, "komsco-ai-page__chat-log-list", "chat cards are styled")
    require(GATEWAY_SERVICE, "gatewayResponseDetail", "action errors parse Gateway detail")
    require(GATEWAY_SERVICE, "separation of duties requires requester and approver to differ", "action errors translate approval conflicts")

    require(
        ASSISTANT_TYPES,
        "export type AiopsExecutionMode = 'read-only' | 'execute' | 'unrestricted';",
        "console keeps three modes",
    )
    require(ASSISTANT, "읽기 전용", "console keeps read-only label")
    require(ASSISTANT, "실행 가능", "console keeps execute label")
    require(ASSISTANT, "실행 무제한", "console keeps unrestricted label")
    require(ASSISTANT, 'title="실험 무제한 모드"', "console keeps unrestricted button selectable")
    reject(ASSISTANT, "setExecutionMode('execute');", "console does not auto-demote unrestricted mode")
    require(ASSISTANT, "setHistorySidebarOpen(false);", "console closes history sidebar with assistant")
    require(ASSISTANT, "setHistoryDrawerBounds({});", "console clears detached history drawer bounds")
    require(ASSISTANT, "assistantVisible && historySidebar", "console does not render sidebar portal after close")
    require(ASSISTANT, "AssistantSurfacePortal", "console portals floating assistant out of OKD stacking context")
    require(ASSISTANT, "komsco-ai--portal", "console marks portaled assistant surface")
    reject(ASSISTANT, "OLS 스트림 중계", "console does not show stream relay jargon")
    reject(ASSISTANT, "OLS 질의 전달", "console does not show OLS query jargon")
    reject(ASSISTANT, "본문 스트리밍", "console does not show streaming jargon")
    reject(ASSISTANT, "브라우저로 중계", "console does not show relay wording")
    require(ASSISTANT_CONSTANTS, "STORED_CONVERSATION_HISTORY_KEY", "console has conversation history storage key")
    require(ASSISTANT_CONSTANTS, "STORED_ACTIVE_CONVERSATION_KEY", "console has active conversation storage key")
    require(ASSISTANT_CONSTANTS, "STORED_UI_LANGUAGE_KEY", "console persists language selection")
    require(ASSISTANT, "readStoredUiLanguage", "console restores language selection")
    require(ASSISTANT, "writeStoredUiLanguage(uiLanguage)", "console stores language selection")
    require(ASSISTANT, 'data-ui-language={uiLanguage}', "console exposes current language state")
    require(ASSISTANT, "uiLanguage === 'ko' ? 'KR' : 'EN'", "console language button shows current language")
    require(ASSISTANT, "readStoredConversationHistory", "console restores conversation history")
    require(ASSISTANT, "readStoredActiveConversation", "console restores active conversation")
    require(ASSISTANT, "writeStoredConversationHistory(conversationHistory)", "console persists conversation history")
    require(ASSISTANT, "writeStoredActiveConversation({", "console persists active conversation")
    require(ASSISTANT, "const { attachments: _attachments, ...storedMessage }", "console strips raw attachments from stored messages")
    require(ASSISTANT_CSS, "font-size: 14.5px;", "assistant answer body uses readable font size")
    require(ASSISTANT_CSS, "line-height: 1.7;", "assistant answer body uses readable line height")
    require(ASSISTANT_CSS, "z-index: 2147483646;", "assistant overlay sits above OKD chrome")
    require(ASSISTANT_CSS, ".komsco-ai--portal", "assistant floating surface has portal wrapper")
    require(ASSISTANT_CSS, ".komsco-ai__surface .komsco-ai__icon-button svg *", "assistant header icons do not steal clicks")
    require(ASSISTANT_CSS, "pointer-events: none;", "assistant overlay click contract blocks only decorative layers")
    require(AIOPS_CONTRACTS, '"evidence_check"', "gateway keeps evidence-check mode")
    require(AIOPS_CONTRACTS, '"controlled_execution"', "gateway keeps controlled execution mode")
    require(AIOPS_CONTRACTS, '"unrestricted"', "gateway keeps unrestricted mode")

    require(GATEWAY_TESTS, "read_only_action_request_skips_plan", "tests cover read-only action skip")
    require(GATEWAY_TESTS, "execute_action_request_emits_plan", "tests cover execute action planning")
    require(GATEWAY_TESTS, "test_runtime_tool_plan_promotes_current_pod_screen_to_rca", "tests cover current Pod screen promotion")
    require(GATEWAY_TESTS, "test_grounded_pod_screen_rca_uses_evidence_renderer_instead_of_generic_answer", "tests cover grounded Pod RCA renderer")
    require_ignored("komsco-ai-gateway/var/aiops/chat-transcripts.jsonl", "runtime transcript JSONL ignored")


if __name__ == "__main__":
    main()
