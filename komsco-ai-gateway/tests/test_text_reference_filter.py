from komsco_ai_gateway.text_reference_filter import (
    TextReferenceFilter,
    should_filter_gateway_api_references,
    should_filter_low_signal_references,
)


def test_text_reference_filter_strips_private_reasoning_before_display() -> None:
    text_filter = TextReferenceFilter(
        filter_gateway_api_references=False,
        filter_low_signal_references=False,
        normalize_restart_language=False,
    )

    visible = text_filter.filter(
        "현재 확인한 내용입니다.\n"
        "<|channel|>thought <channel>\n"
        "thought The user wants to clean up meaningless test pods.\n"
        "Let's search for these patterns.\n"
        "<|channel|>final <channel>\n"
        "## 현재 판단\n"
        "gpu-test-kugnus 테스트 파드 정리 여부를 확인합니다.\n",
        final=True,
    )

    assert "현재 확인한 내용입니다." in visible
    assert "## 현재 판단" in visible
    assert "gpu-test-kugnus" in visible
    assert "<|channel|>" not in visible
    assert "thought The user" not in visible
    assert "Let's search" not in visible


def test_text_reference_filter_strips_angle_bracket_thought_before_display() -> None:
    text_filter = TextReferenceFilter(
        filter_gateway_api_references=False,
        filter_low_signal_references=False,
        normalize_restart_language=False,
    )

    visible = text_filter.filter(
        "현재 확인한 내용입니다.\n"
        "<thought>\n"
        "I have already executed `pods_list` and need to scan the output.\n"
        "Looking at the pods_list output:\n"
        "</thought>\n"
        "## 확인 결과\n"
        "`gpu-test-kugnus` 네임스페이스에 테스트 Pod가 있습니다.\n",
        final=True,
    )

    assert "현재 확인한 내용입니다." in visible
    assert "## 확인 결과" in visible
    assert "gpu-test-kugnus" in visible
    assert "<thought>" not in visible
    assert "I have already executed" not in visible
    assert "Looking at the pods_list output" not in visible


def test_text_reference_filter_drops_unclosed_private_reasoning() -> None:
    text_filter = TextReferenceFilter(
        filter_gateway_api_references=False,
        filter_low_signal_references=False,
        normalize_restart_language=False,
    )

    visible = text_filter.filter(
        "<|channel|>thought <channel>\n"
        "thought The user wants to inspect cluster state.\n"
        "Patterns to search: test, demo, scenario.\n",
        final=True,
    )

    assert visible == ""
    assert text_filter.flush() == ""


def test_gateway_api_reference_filter_removes_misleading_gateway_docs() -> None:
    text_filter = TextReferenceFilter(filter_gateway_api_references=True)

    output = [
        text_filter.filter("대상 미지정입니다.\n---\n\nGateway [gateway.networking.k8s.io/v1]: "),
        text_filter.filter("https://docs.openshift.com/container-platform/4.20/rest_api/network_apis/gateway-gateway-networking-k8s-io-v1.html\n"),
        text_filter.filter("GatewayClass [gateway.networking.k8s.io/v1]: https://docs.openshift.com/container-platform/4.20/rest_api/network_apis/gatewayclass-gateway-networking-k8s-io-v1.html\n"),
        text_filter.flush(),
    ]
    filtered = "".join(output)

    assert "대상 미지정입니다." in filtered
    assert "gateway.networking.k8s.io" not in filtered
    assert "GatewayClass" not in filtered
    assert "---" not in filtered


def test_gateway_api_reference_filter_allows_explicit_gateway_api_questions() -> None:
    assert should_filter_gateway_api_references("pod 재시작해줘")
    assert not should_filter_gateway_api_references("Kubernetes Gateway API 문서 알려줘")


def test_low_signal_reference_filter_removes_unrequested_api_index_links() -> None:
    text_filter = TextReferenceFilter(
        filter_gateway_api_references=False,
        filter_low_signal_references=True,
    )

    output = [
        text_filter.filter("분석 요약입니다.\n---\n\nExtension APIs: https://docs.openshift.com/x\n"),
        text_filter.filter("Admission plugins: https://docs.openshift.com/y\n"),
        text_filter.filter("TokenReview [authentication.k8s.io/v1]: https://docs.openshift.com/z\n"),
        text_filter.filter("ClusterRole [authorization.openshift.io/v1]: https://docs.openshift.com/a\n"),
        text_filter.flush(),
    ]
    filtered = "".join(output)

    assert "분석 요약입니다." in filtered
    assert "Extension APIs" not in filtered
    assert "Admission plugins" not in filtered
    assert "TokenReview" not in filtered
    assert "ClusterRole" not in filtered
    assert "---" not in filtered


def test_low_signal_reference_filter_allows_explicit_doc_questions() -> None:
    assert should_filter_low_signal_references("현재 pod 상태 분석해줘")
    assert not should_filter_low_signal_references("TokenReview API 문서 링크 알려줘")


def test_text_filter_normalizes_restart_frequency_language() -> None:
    text_filter = TextReferenceFilter(
        filter_gateway_api_references=False,
        normalize_restart_language=True,
    )

    filtered = text_filter.filter("높은 빈도의 빈번한 재시작이 확인됩니다.\n")

    assert "높은 빈도" not in filtered
    assert "빈번한 재시작" not in filtered
    assert "높은 누적 재시작 횟수" in filtered
    assert "누적 재시작 이력" in filtered
