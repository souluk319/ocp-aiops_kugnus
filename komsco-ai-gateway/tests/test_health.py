import asyncio

import httpx
import pytest
from fastapi import HTTPException

from komsco_ai_gateway.main import (
    ChatRequest,
    ImageAttachment,
    app,
    build_attachment_context,
    build_cluster_summary,
    build_ols_payload,
    build_ols_query,
    parse_bool,
    parse_ols_verify,
    should_filter_gateway_api_references,
    split_plain_text_events,
    TextReferenceFilter,
    validate_image_attachments,
)
from komsco_ai_gateway.security import (
    build_evidence_reference,
    classify_request_policy,
    redact_sensitive,
    safe_subject,
)


def test_healthz() -> None:
    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/healthz")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    asyncio.run(run())


def test_parse_bool() -> None:
    assert parse_bool("true")
    assert parse_bool("1")
    assert parse_bool("on")
    assert not parse_bool("false")
    assert not parse_bool(None)
    assert parse_bool(None, default=True)


def test_parse_ols_verify() -> None:
    assert parse_ols_verify(None) is True
    assert parse_ols_verify("true") is True
    assert parse_ols_verify("false") is False
    assert parse_ols_verify("/var/run/configmaps/service-ca/service-ca.crt") == (
        "/var/run/configmaps/service-ca/service-ca.crt"
    )


def test_redact_sensitive_removes_tokens_and_secret_values() -> None:
    raw = {
        "authorization": "Bearer abcdefghijklmnopqrstuvwxyz",
        "message": "password=supersecret token: sha256~abcdef Bearer abcdefghijklmnopqrstuvwxyz",
        "nested": {"clientSecret": "should-not-leak"},
    }

    redacted = redact_sensitive(raw)

    assert redacted["authorization"] == "[REDACTED]"
    assert "supersecret" not in redacted["message"]
    assert "abcdefghijklmnopqrstuvwxyz" not in redacted["message"]
    assert redacted["nested"]["clientSecret"] == "[REDACTED]"


def test_classify_request_policy_blocks_direct_mutation_intent() -> None:
    policy = classify_request_policy("openshift-monitoring pod 재시작해줘")

    assert policy["decision"] == "action_proposal_only"
    assert policy["mutationAllowed"] is False
    assert policy["risk"] == "approval_required"


def test_classify_request_policy_allows_read_only_investigation() -> None:
    policy = classify_request_policy("최근 경고와 원인을 근거 기준으로 정리해줘")

    assert policy["decision"] == "allow_read_only_evidence"
    assert policy["mutationAllowed"] is False


def test_validate_image_attachments_accepts_supported_base64_image() -> None:
    attachment = ImageAttachment(
        data="iVBORw0KGgo=",
        id="image-1",
        mimeType="image/png",
        name="cluster.png",
        size=8,
    )

    validate_image_attachments([attachment])
    context = build_attachment_context([attachment])

    assert "cluster.png" in context
    assert "image/png" in context


def test_build_ols_payload_does_not_forward_image_attachments_by_default() -> None:
    attachment = ImageAttachment(
        data="iVBORw0KGgo=",
        id="image-1",
        mimeType="image/png",
        name="cluster.png",
        size=8,
    )

    payload = build_ols_payload("이미지 분석해줘", "conversation-1", [attachment])

    assert payload == {
        "query": "이미지 분석해줘",
        "conversation_id": "conversation-1",
    }


def test_build_ols_payload_forwards_image_attachments_when_enabled() -> None:
    attachment = ImageAttachment(
        data="iVBORw0KGgo=",
        id="image-1",
        mimeType="image/png",
        name="cluster.png",
        size=8,
    )

    payload = build_ols_payload(
        "이미지 분석해줘",
        "conversation-1",
        [attachment],
        forward_image_attachments=True,
    )

    assert payload == {
        "query": "이미지 분석해줘",
        "conversation_id": "conversation-1",
        "attachments": [
            {
                "attachment_type": "image",
                "content_type": "image/png",
                "content": "iVBORw0KGgo=",
            }
        ],
    }


def test_validate_image_attachments_rejects_unsupported_type() -> None:
    attachment = ImageAttachment(
        data="aGVsbG8=",
        id="image-1",
        mimeType="text/plain",
        name="note.txt",
        size=5,
    )

    with pytest.raises(HTTPException):
        validate_image_attachments([attachment])


def test_build_ols_query_keeps_page_context_thin_and_requires_live_tools() -> None:
    query = build_ols_query(
        ChatRequest(
            message="최근 OpenShift 경고와 우선 확인할 항목을 정리해줘.",
            pageContext={
                "href": "http://localhost:9000/k8s/cluster/projects",
                "pathname": "/k8s/cluster/projects",
                "title": "개요 · 클러스터 · OKD",
            },
        )
    )

    assert "최근 OpenShift 경고" in query
    assert "OpenShift MCP 도구를 먼저 사용하세요" in query
    assert "도구 결과에 없는 alert" in query
    assert "OpenShift 경고 분석 프로토콜" in query
    assert "resources_get" in query
    assert '"상세 확인됨"' in query
    assert '"Alert 근거 확인"' in query
    assert '"추가 확인 필요"' in query
    assert "상세 조회를 실제로 호출하지 않은 리소스" in query
    assert "alert 이름이나 summary만으로 원인을 단정하지 마세요" in query
    assert "status.containerStatuses와 events" in query
    assert "oc logs를 우선 명령으로 제시하지 말고" in query
    assert "ClusterVersion conditions" in query
    assert "apiVersion: config.openshift.io/v1" in query
    assert "kind: ClusterVersion" in query
    assert "alert 결과만으로 ConfigMap 또는 Secret 이름을 만들어 조회하지 마세요" in query
    assert "권한상 직접 확인이 제한될 수 있음" in query
    assert "조회 실패/권한 제한" in query
    assert "즉시 수행" in query
    assert "삼중 백틱" in query
    assert "catalog Pod" in query
    assert "gateway.networking.k8s.io" in query
    assert "GatewayClass 문서" in query
    assert "대상 미지정" in query
    assert "oc get pods -A" in query
    assert "기본 제안하지 마세요" in query
    assert "oc delete pod" in query
    assert "기본 재시작 방법으로 제시하지 마세요" in query
    assert "title" not in query
    assert "OKD" not in query


def test_build_ols_query_includes_security_guardrail_and_redacts_user_secrets() -> None:
    policy = classify_request_policy("deployment restart 해줘 token=my-secret-token-value")
    query = build_ols_query(
        ChatRequest(message="deployment restart 해줘 token=my-secret-token-value"),
        policy=policy,
        subject=safe_subject({"username": "user@example.com", "uid": "uid-1", "groups": ["a"]}),
    )

    assert "Gateway Phase 0-1 Security Envelope" in query
    assert "action_proposal_only" in query
    assert "mutation을 실행하지 않습니다" in query
    assert "user@example.com" in query
    assert "my-secret-token-value" not in query
    assert "[REDACTED]" in query


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


def test_build_cluster_summary_returns_real_operational_counts() -> None:
    nodes_payload = {
        "items": [
            {
                "metadata": {
                    "name": "node-1",
                    "labels": {
                        "node-role.kubernetes.io/control-plane": "",
                        "node-role.kubernetes.io/worker": "",
                    },
                },
                "status": {
                    "conditions": [
                        {"type": "Ready", "status": "True"},
                        {"type": "DiskPressure", "status": "False"},
                        {"type": "MemoryPressure", "status": "False"},
                        {"type": "PIDPressure", "status": "False"},
                    ],
                    "nodeInfo": {"kubeletVersion": "v1.33.1", "osImage": "RHEL CoreOS 9.6"},
                },
            }
        ]
    }
    node_metrics_payload = {
        "items": [
            {
                "metadata": {"name": "node-1"},
                "usage": {"cpu": "123m", "memory": "456Mi"},
            }
        ]
    }
    cluster_version_payload = {
        "status": {
            "desired": {"version": "4.20.23"},
            "channel": "stable-4.20",
            "availableUpdates": [{"version": "4.20.24"}],
            "conditions": [{"type": "Upgradeable", "status": "False", "reason": "AdminAck"}],
        }
    }
    cluster_operators_payload = {
        "items": [
            {
                "metadata": {"name": "console"},
                "status": {
                    "conditions": [
                        {"type": "Available", "status": "True"},
                        {"type": "Degraded", "status": "False"},
                        {"type": "Progressing", "status": "False"},
                    ]
                },
            },
            {
                "metadata": {"name": "marketplace"},
                "status": {
                    "conditions": [
                        {"type": "Available", "status": "True"},
                        {
                            "type": "Degraded",
                            "status": "True",
                            "reason": "CatalogPodNotReady",
                            "message": "catalog pod is not ready",
                        },
                        {"type": "Progressing", "status": "False"},
                    ]
                },
            },
        ]
    }

    summary = build_cluster_summary(
        nodes_payload,
        node_metrics_payload,
        cluster_version_payload,
        cluster_operators_payload,
    )

    assert summary["nodes"]["total"] == 1
    assert summary["nodes"]["ready"] == 1
    assert summary["nodes"]["items"][0]["usage"]["cpu"] == "123m"
    assert summary["operators"]["degraded"] == 1
    assert summary["operators"]["issues"][0]["name"] == "marketplace"
    assert summary["version"]["updateAvailable"] is True
    assert summary["version"]["upgradeable"] is False
    assert summary["healthScore"] < 100


def test_split_plain_text_events_extracts_tool_lines() -> None:
    async def chunks():
        yield 'Tool call: {"name": "get_alerts", "args": {"active": true}, "id": "tool-1"}\n'
        yield 'Tool result: {"name": "get_alerts", "status": "success", "content": "{\\"alerts\\":[{},{}]}", "id": "tool-1"}\n'
        yield "현재 확인된 경고를 정리합니다."

    async def run() -> list[dict]:
        return [event async for event in split_plain_text_events(chunks())]

    events = asyncio.run(run())

    assert events[0]["type"] == "tool_call"
    assert events[0]["name"] == "get_alerts"
    assert events[1]["type"] == "tool_result"
    assert events[1]["summary"] == "경고 2건 조회"
    assert events[2] == {"type": "text", "content": "현재 확인된 경고를 정리합니다."}


def test_split_plain_text_events_summarizes_resource_get_progress() -> None:
    async def chunks():
        yield (
            'Tool call: {"name": "resources_get", "args": {"apiVersion": "v1", '
            '"kind": "Pod", "namespace": "openshift-marketplace", '
            '"name": "appscan360-catalog-457gn"}, "id": "tool-1"}\n'
        )
        yield (
            'Tool result: {"name": "resources_get", "status": "success", '
            '"content": "apiVersion: v1\\nkind: Pod\\nmetadata:\\n  name: '
            'appscan360-catalog-457gn\\n  namespace: openshift-marketplace\\n", '
            '"id": "tool-1"}\n'
        )
        yield (
            'Tool result: {"name": "resources_get", "status": "error", '
            '"content": "Tool failed: resource not allowed", "id": "tool-2"}\n'
        )

    async def run() -> list[dict]:
        return [event async for event in split_plain_text_events(chunks())]

    events = asyncio.run(run())

    assert events[0]["summary"] == "Pod openshift-marketplace/appscan360-catalog-457gn 상세 조회"
    assert events[1]["summary"] == "Pod openshift-marketplace/appscan360-catalog-457gn 조회 완료"
    assert events[2]["summary"] == "조회 실패: Tool failed: resource not allowed"


def test_build_evidence_reference_uses_redacted_digest_projection() -> None:
    subject = safe_subject({"username": "user@example.com", "uid": "uid-1", "groups": ["ops"]})
    event = {
        "type": "tool_result",
        "name": "resources_get",
        "status": "success",
        "summary": "Pod 조회 완료",
        "detail": "token=my-secret-token-value\nkind: Pod",
    }

    evidence = build_evidence_reference(
        event=event,
        incident_id="inc-1",
        run_id="run-1",
        subject=subject,
    )

    assert evidence["evidenceId"].startswith("ev-")
    assert evidence["contentDigest"].startswith("sha256:")
    assert evidence["originatingSubject"]["username"] == "user@example.com"
    assert evidence["summary"] == "Pod 조회 완료"
