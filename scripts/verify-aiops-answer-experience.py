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
ASSISTANT_CSS = ROOT / "komsco-ai-console-plugin" / "src" / "components" / "assistant.css"
PAGES = ROOT / "komsco-ai-console-plugin" / "src" / "pages" / "AiopsPages.tsx"
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
    require(GATEWAY_MAIN, '"answerMode": answer_mode', "transcript stores answerMode")
    require(GATEWAY_MAIN, '"assistantAnswer"', "transcript stores assistantAnswer")
    require(GATEWAY_MAIN, '"toolPlanDigest": tool_plan_digest', "transcript stores toolPlanDigest")
    require(GATEWAY_MAIN, '"rcaContextDigest": rca_context_digest', "transcript stores rcaContextDigest")
    require(GATEWAY_MAIN, '"evidenceRefs"', "transcript stores evidenceRefs")
    require(GATEWAY_MAIN, '"human_rca"', "transcript names human RCA answer mode")
    require(GATEWAY_MAIN, "조회 계획:", "action text uses human query plan wording")
    reject(GATEWAY_MAIN, 'f"- Tool Plan:', "default action text does not print Tool Plan line")

    require(ASSISTANT, "type EvidenceFooterQueryStep", "console has query step type")
    require(ASSISTANT, "queryPlan", "console builds queryPlan for Evidence footer")
    require(ASSISTANT, "상세 보기", "console has Evidence detail toggle")
    require(ASSISTANT, "조회 계획", "console labels human query plan")
    require(ASSISTANT, "현재 화면의 대상 리소스에 대해 가능한 안전 조회를 실행", "quick prompt asks AIOps to run safe checks")
    require(ASSISTANT_CSS, "komsco-ai__evidence-query-plan", "console styles query plan detail")
    require(PAGES, "원본 Tool Plan JSON", "audit page keeps raw Tool Plan JSON")
    require(PAGES, "RCA Context JSON", "audit page keeps raw RCA Context JSON")

    require(ASSISTANT, "type AiopsExecutionMode = 'read-only' | 'execute' | 'unrestricted';", "console keeps three modes")
    require(ASSISTANT, "읽기 전용", "console keeps read-only label")
    require(ASSISTANT, "실행 가능", "console keeps execute label")
    require(ASSISTANT, "실행 무제한", "console keeps unrestricted label")
    require(ASSISTANT, 'title="실험 무제한 모드"', "console keeps unrestricted button selectable")
    reject(ASSISTANT, "setExecutionMode('execute');", "console does not auto-demote unrestricted mode")
    require(AIOPS_CONTRACTS, '"evidence_check"', "gateway keeps evidence-check mode")
    require(AIOPS_CONTRACTS, '"controlled_execution"', "gateway keeps controlled execution mode")
    require(AIOPS_CONTRACTS, '"unrestricted"', "gateway keeps unrestricted mode")

    require(GATEWAY_TESTS, "read_only_action_request_skips_plan", "tests cover read-only action skip")
    require(GATEWAY_TESTS, "execute_action_request_emits_plan", "tests cover execute action planning")
    require(GATEWAY_TESTS, "test_runtime_tool_plan_promotes_current_pod_screen_to_rca", "tests cover current Pod screen promotion")
    require_ignored("komsco-ai-gateway/var/aiops/chat-transcripts.jsonl", "runtime transcript JSONL ignored")


if __name__ == "__main__":
    main()
