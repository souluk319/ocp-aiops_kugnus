from types import SimpleNamespace

from komsco_ai_gateway.answer_contracts import assistant_operating_answer_style_contract
from komsco_ai_gateway.followup_selection import (
    extract_numbered_followups,
    rewrite_followup_option_as_query,
    resolve_numeric_followup_message,
    selected_followup_index,
)


FOLLOWUP_ANSWER = """
### 다음으로 무엇을 확인할까요?

1. **Pod 이벤트 확인**: `gpu-test-kugnus`의 최근 Event를 확인할까요?
2. 이전 컨테이너 로그를 확인할까요?
3. 승인 가능한 Action Plan 초안을 만들까요?
4. 화면에 표시하지 않을 네 번째 질문입니다.
"""


def test_exact_followup_heading_extracts_at_most_three_questions() -> None:
    assert extract_numbered_followups(FOLLOWUP_ANSWER) == [
        "Pod 이벤트 확인: gpu-test-kugnus의 최근 Event를 확인할까요?",
        "이전 컨테이너 로그를 확인할까요?",
        "승인 가능한 Action Plan 초안을 만들까요?",
    ]


def test_numeric_and_korean_ordinal_selection_keep_existing_behavior() -> None:
    messages = [{"role": "assistant", "content": FOLLOWUP_ANSWER}]

    assert selected_followup_index("1") == 1
    assert selected_followup_index("2번") == 2
    assert selected_followup_index("세 번째") == 3
    selection = resolve_numeric_followup_message("2번", messages)
    assert selection is not None
    assert selection.index == 2
    assert selection.option == "이전 컨테이너 로그를 확인할까요?"
    assert selection.effective_message == "이전 컨테이너 로그를 확인해줘"


def test_followup_question_is_rewritten_as_a_user_command() -> None:
    assert (
        rewrite_followup_option_as_query(
            "gpu-test-kugnus의 CrashLoopBackOff Pod 로그를 상세히 확인하시겠습니까?"
        )
        == "gpu-test-kugnus의 CrashLoopBackOff Pod 로그를 상세히 확인해줘"
    )
    assert (
        rewrite_followup_option_as_query(
            "Critical 알림 리스트를 표 형태로 정리해 드릴까요?"
        )
        == "Critical 알림 리스트를 표 형태로 정리해줘"
    )


def test_code_and_operating_checklists_are_not_followup_choices() -> None:
    assert extract_numbered_followups("1. 요청 확인\n2. 권한 확인\n3. 조회 실행") == []
    assert extract_numbered_followups("### 추가 확인\n1. Event 확인\n2. 로그 확인") == []
    assert (
        extract_numbered_followups(
            "```text\n### 다음으로 무엇을 확인할까요?\n1. 예시 질문\n```"
        )
        == []
    )
    assert (
        extract_numbered_followups(
            "~~~text\n### 다음으로 무엇을 확인할까요?\n1. 예시 질문\n~~~"
        )
        == []
    )
    assert (
        extract_numbered_followups(
            "원하시면 아래 절차를 따르세요.\n1. Deployment 확인\n2. Event 확인"
        )
        == []
    )


def test_displayed_choice_number_is_used_instead_of_array_position() -> None:
    messages = [
        {
            "role": "assistant",
            "content": (
                "### 다음으로 무엇을 확인할까요?\n\n"
                "2. 두 번째 대상을 확인할까요?\n"
                "3. 세 번째 대상을 확인할까요?"
            ),
        }
    ]

    selection = resolve_numeric_followup_message("2", messages)
    assert selection is not None
    assert selection.option == "두 번째 대상을 확인할까요?"
    assert selection.effective_message == "두 번째 대상을 확인해줘"


def test_numeric_choice_does_not_reuse_an_older_assistant_answer() -> None:
    messages = [
        {"role": "assistant", "content": FOLLOWUP_ANSWER},
        {"role": "user", "content": "다른 질문입니다"},
    ]

    assert resolve_numeric_followup_message("2", messages) is None


def test_answer_contract_uses_exact_choice_heading_and_one_line_limit() -> None:
    korean = assistant_operating_answer_style_contract(
        SimpleNamespace(language="ko", message="상태를 알려줘", pageContext={})
    )
    english = assistant_operating_answer_style_contract(
        SimpleNamespace(language="en", message="Show status", pageContext={})
    )

    assert "### 다음으로 무엇을 확인할까요?" in korean
    assert "최대 3개" in korean
    assert "독립 질문 한 줄" in korean
    assert "### What would you like to check next?" in english
    assert "no more than 3" in english
    assert "one line" in english
