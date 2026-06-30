"""Tests for rca_result_parser and 0.1.8 OS-context classification."""

from __future__ import annotations

import pytest


def _import_parser():
    from komsco_ai_gateway.rca_result_parser import RcaResult, parse_rca_result
    return parse_rca_result, RcaResult


def _import_contracts():
    from komsco_ai_gateway.aiops_contracts import build_runtime_tool_plan
    return build_runtime_tool_plan


# ---------------------------------------------------------------------------
# RCA result parser
# ---------------------------------------------------------------------------

class TestParseRcaResult:
    def test_oomkilled_extracted_as_cause(self):
        parse_rca_result, _ = _import_parser()
        result = parse_rca_result("Pod가 OOMKilled 상태입니다. 메모리가 부족합니다.", [])
        assert any("OOMKilled" in c for c in result.cause_candidates)

    def test_crashloopbackoff_extracted(self):
        parse_rca_result, _ = _import_parser()
        result = parse_rca_result("컨테이너가 CrashLoopBackOff 상태로 반복 재시작 중입니다.", [])
        assert any("CrashLoopBackOff" in c for c in result.cause_candidates)

    def test_cause_from_korean_label(self):
        parse_rca_result, _ = _import_parser()
        result = parse_rca_result("원인: 메모리 설정 오류", [])
        assert any("메모리 설정 오류" in c for c in result.cause_candidates)

    def test_action_extracted(self):
        parse_rca_result, _ = _import_parser()
        result = parse_rca_result("조치: 메모리 limit을 512Mi로 증가하세요.", [])
        assert any("메모리 limit을 512Mi" in a for a in result.action_candidates)

    def test_all_success_confidence_one(self):
        parse_rca_result, _ = _import_parser()
        tool_results = [
            {"name": "openshift_event_lookup", "status": "success"},
            {"name": "pod_status_evidence", "status": "ok"},
        ]
        result = parse_rca_result("", tool_results)
        assert result.confidence == 1.0

    def test_empty_tool_results_confidence_zero(self):
        parse_rca_result, _ = _import_parser()
        result = parse_rca_result("", [])
        assert result.confidence == 0.0

    def test_partial_success_confidence(self):
        parse_rca_result, _ = _import_parser()
        tool_results = [
            {"name": "tool_a", "status": "success"},
            {"name": "tool_b", "status": "error"},
        ]
        result = parse_rca_result("", tool_results)
        assert result.confidence == 0.5

    def test_evidence_types_from_successful_tools(self):
        parse_rca_result, _ = _import_parser()
        tool_results = [
            {"name": "event_tool", "status": "success"},
            {"name": "grep_tool", "status": "error"},
        ]
        result = parse_rca_result("", tool_results)
        assert "event_tool" in result.evidence_types
        assert "grep_tool" not in result.evidence_types

    def test_no_cause_returns_fallback(self):
        parse_rca_result, _ = _import_parser()
        result = parse_rca_result("모든 시스템이 정상입니다.", [])
        assert result.cause_candidates == ["수집된 증거 기준 원인 후보 미확정"]

    def test_causes_capped_at_three(self):
        parse_rca_result, _ = _import_parser()
        text = (
            "OOMKilled 발생\n"
            "원인: A 오류\n"
            "근본 원인: B 문제\n"
            "주요 원인: C 이슈\n"
            "CrashLoopBackOff 재시작\n"
        )
        result = parse_rca_result(text, [])
        assert len(result.cause_candidates) <= 3


# ---------------------------------------------------------------------------
# OS context classification (0.1.8 — Linux / Windows skeleton)
# ---------------------------------------------------------------------------

class TestOsContextClassification:
    def test_journalctl_maps_to_linux(self):
        build_runtime_tool_plan = _import_contracts()
        plan = build_runtime_tool_plan("journalctl -xe 로그를 확인해줘")
        assert plan["task_type"] == "linux_service_diagnosis"

    def test_systemctl_maps_to_linux(self):
        build_runtime_tool_plan = _import_contracts()
        plan = build_runtime_tool_plan("systemctl status nginx가 실패했어요")
        assert plan["task_type"] == "linux_service_diagnosis"

    def test_linux_service_keyword(self):
        build_runtime_tool_plan = _import_contracts()
        plan = build_runtime_tool_plan("linux service 장애가 났어요")
        assert plan["task_type"] == "linux_service_diagnosis"

    def test_windows_maps_to_windows(self):
        build_runtime_tool_plan = _import_contracts()
        plan = build_runtime_tool_plan("windows event log 확인해줘")
        assert plan["task_type"] == "windows_event_diagnosis"

    def test_get_winevent_maps_to_windows(self):
        build_runtime_tool_plan = _import_contracts()
        plan = build_runtime_tool_plan("Get-WinEvent 명령 결과를 분석해줘")
        assert plan["task_type"] == "windows_event_diagnosis"

    def test_linux_plan_has_runbook_tool(self):
        build_runtime_tool_plan = _import_contracts()
        plan = build_runtime_tool_plan("journalctl 오류 분석해줘")
        tools = [step.get("tool") for step in plan["tool_plan"]]
        assert "gateway_rag_runbook_search" in tools

    def test_linux_plan_official_tool_is_runbook(self):
        build_runtime_tool_plan = _import_contracts()
        plan = build_runtime_tool_plan("systemctl status 확인해줘")
        first_step = plan["tool_plan"][0]
        assert first_step.get("official_tool") == "runbook_tool"
        assert first_step.get("adapter") == "linux"

    def test_windows_plan_official_tool_is_runbook(self):
        build_runtime_tool_plan = _import_contracts()
        plan = build_runtime_tool_plan("windows event log 보여줘")
        first_step = plan["tool_plan"][0]
        assert first_step.get("official_tool") == "runbook_tool"
        assert first_step.get("adapter") == "windows"

    def test_ocp_question_still_maps_to_openshift(self):
        build_runtime_tool_plan = _import_contracts()
        plan = build_runtime_tool_plan("네임스페이스 상태 확인해줘")
        assert plan["task_type"] == "openshift_operational_question"

    def test_linux_missing_evidence_notes_v019(self):
        build_runtime_tool_plan = _import_contracts()
        plan = build_runtime_tool_plan("journalctl 오류")
        missing_types = [m.get("type") for m in plan["missing_evidence"]]
        assert "linux_command_output" in missing_types
