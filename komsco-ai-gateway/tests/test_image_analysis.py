from __future__ import annotations

from komsco_ai_gateway.image_analysis import (
    IMAGE_ANALYSIS_PROMPT,
    build_grounded_image_question,
    extract_analysis_text,
)
from komsco_ai_gateway.ols_payloads import build_attachment_context


class _Attachment:
    name = "image.png"
    mimeType = "image/png"
    size = 128
    data = "aW1hZ2U="


def test_image_analysis_prompt_is_concise_and_distinguishes_quoted_chatbot_text() -> None:
    assert len(IMAGE_ANALYSIS_PROMPT) < 300
    assert "화면 속 다른 챗봇 문구" in IMAGE_ANALYSIS_PROMPT
    assert "자신의 기능 상태로 해석하지 마세요" in IMAGE_ANALYSIS_PROMPT


def test_extract_analysis_text_reads_string_content() -> None:
    result = {"choices": [{"message": {"content": "gpu-test 화면의 오류입니다."}}]}

    assert extract_analysis_text(result) == "gpu-test 화면의 오류입니다."


def test_extract_analysis_text_reads_text_blocks() -> None:
    result = {
        "choices": [
            {"message": {"content": [{"type": "text", "text": "Pod 오류"}, {"text": "재시작 25회"}]}}
        ]
    }

    assert extract_analysis_text(result) == "Pod 오류\n재시작 25회"


def test_extract_analysis_text_rejects_reasoning_only_response() -> None:
    result = {"choices": [{"message": {"content": None, "reasoning": "private reasoning"}}]}

    assert extract_analysis_text(result) is None


def test_extract_analysis_text_rejects_ungrounded_image_refusal() -> None:
    result = {"choices": [{"message": {"content": "현재 이미지를 직접 분석할 수 없습니다."}}]}

    assert extract_analysis_text(result) is None


def test_extract_analysis_text_rejects_refusal_with_generic_error_word() -> None:
    result = {
        "choices": [
            {"message": {"content": "이미지 분석 중 오류가 발생하여 화면을 읽을 수 없습니다."}}
        ]
    }

    assert extract_analysis_text(result) is None


def test_extract_analysis_text_removes_private_reasoning_from_content() -> None:
    result = {
        "choices": [
            {"message": {"content": "<think>private chain</think>\nNamespace: gpu-test\nPod 오류가 보입니다."}}
        ]
    }

    assert extract_analysis_text(result) == "Namespace: gpu-test\nPod 오류가 보입니다."


def test_extract_analysis_text_keeps_grounded_screenshot_of_previous_refusal() -> None:
    text = "화면 종류: 챗봇 UI\nNamespace: gpu-test\n화면 속 챗봇이 이미지를 분석할 수 없다고 답했습니다."
    result = {"choices": [{"message": {"content": text}}]}

    assert extract_analysis_text(result) == text


def test_attachment_context_marks_pixel_analysis_as_successful_visual_evidence() -> None:
    context = build_attachment_context(
        [_Attachment()],
        "gpu-test 화면에서 이전 챗봇이 이미지를 읽지 못했다고 답했습니다.",
    )

    assert "[첨부 화면 판독 상태: 성공]" in context
    assert "이미지 픽셀을 실제로 판독한 시각 증거" in context
    assert "현재 시스템의 기능 상태가 아니라" in context


def test_grounded_image_question_converts_image_request_to_text_evidence_task() -> None:
    question = build_grounded_image_question("이 화면에서 문제되는 부분이 무엇이야?")

    assert "픽셀 판독을 완료했습니다" in question
    assert "이미지 지원 여부를 판단하거나 설명하지 말고" in question
    assert "텍스트로 다시 입력하거나 이미지를 다시 첨부하라고 요구하지 마세요" in question
    assert "원래 사용자 요청: 이 화면에서 문제되는 부분이 무엇이야?" in question


def test_grounded_image_question_identifies_previous_assistant_failure() -> None:
    question = build_grounded_image_question(
        "이 화면에서 문제되는 부분이 무엇이야?",
        "화면 속 챗봇이 첨부 이미지의 내용을 읽지 못하고 일반 명령만 안내했습니다.",
    )

    assert "이전 챗봇이 이미지를 읽지 못하고 일반 안내를 반환한 UI 문제" in question
    assert "현재 시스템이 이미지를 못 본다고 설명하지 마세요" in question
    assert "텍스트 재입력이나 재첨부를 요구하지 말고" in question
