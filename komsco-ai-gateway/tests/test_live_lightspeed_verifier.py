from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFIER_PATH = REPO_ROOT / "scripts" / "verify-live-lightspeed-final-response.py"
SPEC = importlib.util.spec_from_file_location("live_lightspeed_verifier", VERIFIER_PATH)
assert SPEC and SPEC.loader
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


def _healthy_status() -> dict:
    return {
        "ok": True,
        "payload": {
            "spec": {
                "safetyContract": {
                    "lightspeedStatus": {
                        "streamProbe": "succeeded",
                        "lastStatus": "succeeded",
                        "fallbackActive": False,
                        "lastError": "",
                    }
                },
                "accessReviewStatus": {},
            }
        },
    }


def _healthy_stream() -> dict:
    return {
        "doneReceived": True,
        "runStatusStages": ["lightspeed", "completed"],
        "olsTextEvents": 1,
        "answerLength": 120,
        "toolPlanEvents": [{}],
        "evidenceRefEvents": [{}],
        "rcaContextPhases": ["pre_answer", "post_answer"],
        "fallbackEvents": [],
        "gatewayErrors": [],
        "lightspeedErrors": [],
        "requiredAnyTextPresent": {
            "RCA | 원인 후보 | 분석 결과": True,
            "근거 | 증거 | 확인 결과": True,
        },
        "answerContractEvents": [],
    }


def test_read_only_lightspeed_case_does_not_require_action_contract() -> None:
    result = verifier.evaluate_case(
        "cluster-summary",
        _healthy_stream(),
        _healthy_status(),
        action_contract_expectation="optional",
    )

    assert result["ok"] is True
    assert result["checks"]["aiopsActionContractPresent"] is True


def test_action_case_still_requires_current_action_contract_evidence() -> None:
    stream = _healthy_stream()

    missing = verifier.evaluate_case(
        "action-case",
        stream,
        _healthy_status(),
        action_contract_expectation="required",
    )
    assert missing["ok"] is False
    assert missing["checks"]["aiopsActionContractPresent"] is False

    stream["answerContractEvents"] = [
        {
            "answerContract": "aiops-action-v0.1.9",
            "hasAiopsActionFeature": True,
            "hasActionExecutionPath": True,
            "hasRejectionPath": True,
        }
    ]
    present = verifier.evaluate_case(
        "action-case",
        stream,
        _healthy_status(),
        action_contract_expectation="required",
    )
    assert present["ok"] is True


def test_required_meaning_groups_are_evaluated_from_answer_text() -> None:
    groups = [
        ["RCA", "현재 판단", "원인 후보", "분석 결과"],
        ["근거", "증거", "확인 결과", "확인 불가"],
    ]

    assert verifier.required_any_text_presence("현재 판단과 확인 결과입니다.", groups) == {
        "RCA | 현재 판단 | 원인 후보 | 분석 결과": True,
        "근거 | 증거 | 확인 결과 | 확인 불가": True,
    }
    assert verifier.required_any_text_presence("확인 불가", groups) == {
        "RCA | 현재 판단 | 원인 후보 | 분석 결과": False,
        "근거 | 증거 | 확인 결과 | 확인 불가": True,
    }


def test_optional_action_contract_must_be_valid_when_present() -> None:
    safe_text = """## 승인 대기 조치
Action Plan 조치 후보입니다.
승인 전에는 변경 작업을 실행하지 않습니다.
거절하면 실행은 차단되고 거절 기록만 남습니다.
"""
    unsafe_text = "Action Plan 조치 후보이며 승인 없이 실행합니다. 거절해도 실행은 차단되지 않습니다."

    safe_event = verifier.summarize_answer_contract_event(
        {"answerContract": "aiops-action-v0.1.9"},
        safe_text,
    )
    unsafe_event = verifier.summarize_answer_contract_event(
        {"answerContract": "aiops-action-v0.1.9"},
        unsafe_text,
    )

    assert verifier.action_contract_satisfied([], "optional") is True
    assert verifier.action_contract_satisfied([safe_event], "optional") is True
    assert verifier.action_contract_satisfied([unsafe_event], "optional") is False
    assert verifier.action_contract_satisfied([safe_event], "forbidden") is False
