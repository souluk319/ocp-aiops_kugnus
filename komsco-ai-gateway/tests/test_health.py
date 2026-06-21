import asyncio

import httpx
import pytest
from fastapi import HTTPException

from komsco_ai_gateway.main import (
    ChatRequest,
    DIAGNOSTIC_REQUESTS,
    EVIDENCE_RECORDS,
    ImageAttachment,
    METRICS,
    TextReferenceFilter,
    WORKFLOW_RECORDS,
    app,
    build_attachment_context,
    build_action_proposal_fallback,
    build_cluster_summary,
    build_cluster_operator_status_evidence,
    build_cronjob_activity_evidence,
    build_diagnostic_request_candidate,
    build_diagnostic_request_record,
    build_empty_answer_fallback,
    build_evidence_reference_events,
    build_ols_payload,
    build_ols_query,
    build_product_access_review_request,
    diagnostic_request_digest,
    can_subject_read_record,
    build_pod_status_evidence,
    DiagnosticEvidencePolicy,
    DiagnosticLimits,
    DiagnosticRequestCreate,
    DiagnosticTargetNode,
    DiagnosticTimeRange,
    parse_bool,
    parse_ols_verify,
    normalize_console_page_context,
    product_access_review_status,
    summarize_product_access_review,
    should_collect_cronjob_activity_evidence,
    should_collect_pod_status_evidence,
    should_filter_gateway_api_references,
    should_filter_low_signal_references,
    split_plain_text_events,
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


def test_normalize_console_page_context_extracts_namespaced_resource() -> None:
    context = normalize_console_page_context(
        {
            "href": "http://localhost:9000/k8s/ns/team-a/deployments/web",
            "pathname": "/k8s/ns/team-a/deployments/web",
            "title": "ignored browser title",
        }
    )

    assert context["route"] == "k8s"
    assert context["namespace"] == "team-a"
    assert context["resourceList"] == "deployments"
    assert context["resourceKind"] == "Deployment"
    assert context["resourceName"] == "web"
    assert "title" not in context


def test_normalize_console_page_context_extracts_catalog_namespace() -> None:
    context = normalize_console_page_context(
        {
            "href": "http://localhost:9000/catalog/ns/team-a",
            "pathname": "/catalog/ns/team-a",
        }
    )

    assert context["route"] == "catalog"
    assert context["namespace"] == "team-a"
    assert context["resourceKind"] == "Catalog"
    assert context["perspective"] == "developer"


def test_product_access_review_request_is_config_driven_ssar() -> None:
    request = build_product_access_review_request()

    assert request["apiVersion"] == "authorization.k8s.io/v1"
    assert request["kind"] == "SelfSubjectAccessReview"
    attributes = request["spec"]["resourceAttributes"]
    assert attributes["verb"]
    assert attributes["resource"]
    assert "token" not in str(request).lower()


def test_product_access_review_statuses_are_nonblocking_by_default() -> None:
    review = {
        "allowed": False,
        "enabled": True,
        "reason": "not allowed in this namespace",
        "required": False,
        "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
    }

    assert product_access_review_status(review) == "warning"
    assert "required: False" in summarize_product_access_review(review)


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


def test_classify_request_policy_blocks_mutation_action_plan_intent() -> None:
    policy = classify_request_policy("deployment 재시작 계획을 세워줘")

    assert policy["decision"] == "action_proposal_only"
    assert policy["mutationAllowed"] is False
    assert policy["risk"] == "approval_required"


def test_classify_request_policy_allows_restart_count_analysis() -> None:
    policy = classify_request_policy("현재 클러스터에서 재시작이 많은 Pod를 분석해줘")

    assert policy["decision"] == "allow_read_only_evidence"
    assert policy["mutationAllowed"] is False
    assert policy["risk"] == "low"


def test_pod_status_evidence_trigger_only_for_read_only_status_analysis() -> None:
    assert should_collect_pod_status_evidence("현재 클러스터의 Pod 상태와 재시작이 많은 Pod를 분석해줘")
    assert not should_collect_pod_status_evidence("openshift-monitoring pod 재시작해줘")


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


def test_build_attachment_context_without_vision_uses_metadata_only_language() -> None:
    attachment = ImageAttachment(
        data="iVBORw0KGgo=",
        id="image-1",
        mimeType="image/png",
        name="catalog-screen.png",
        size=8,
    )

    context = build_attachment_context([attachment])

    assert "비활성화" in context
    assert "첨부 파일 메타데이터" in context
    assert "사용자 설명" in context
    assert "도구 조회 결과" in context
    assert "이미지 원본 판독은 수행하지 않았습니다" not in context


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
    assert "스크린샷이나 이미지가 전달된 것이 아닙니다" in query
    assert '답변에 "이미지를 직접 판독할 수 없다"' in query
    assert "경로 기준으로는 Catalog 페이지로 보입니다" in query
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
    assert "Pod 상태/재시작 분석 프로토콜" in query
    assert "CronJob/Activity 분석 프로토콜" in query
    assert "설정상 의도된 <N>분 주기" in query
    assert "lifecycle/retention 관련 env" in query
    assert "로그나 소스 근거 없이 생성 후" in query
    assert "`restartCount`만 보고 현재 `CrashLoopBackOff`" in query
    assert "`restartCount`는 Pod 단위가 아니라 container 단위" in query
    assert "`restartCount`는 누적 카운터" in query
    assert "containerStatuses[*]" in query
    assert "`Running` 및 `Ready=True`" in query
    assert "과거 실패 Pod 이력, 현재 Operator 상태는 정상" in query
    assert "CatalogSource" in query
    assert "--previous" in query
    assert "Extension APIs" in query
    assert "Admission plugins" in query
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


def test_build_ols_query_treats_console_path_as_context_not_image() -> None:
    query = build_ols_query(
        ChatRequest(
            message="현재 보고 있는 콘솔 화면이 무엇인지 설명해줘.",
            pageContext={
                "href": "http://localhost:9000/catalog/ns/team-a",
                "pathname": "/catalog/ns/team-a",
                "namespace": "team-a",
            },
        )
    )

    assert "첨부 이미지 없음" in query
    assert "/catalog/ns/team-a" in query
    assert '"namespace": "team-a"' in query
    assert '"route": "catalog"' in query
    assert '"resourceKind": "Catalog"' in query
    assert "현재 콘솔 페이지의 스크린샷이나 이미지가 전달된 것이 아닙니다" in query
    assert "화면의 시각적 내용 자체라고 단정하지 말고" in query


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


def test_build_ols_query_includes_gateway_evidence() -> None:
    query = build_ols_query(
        ChatRequest(message="현재 클러스터의 Pod 상태를 분석해줘"),
        gateway_evidence="Top container restart counts:\nopenshift-lightspeed exporter restartCount=44",
    )

    assert "[Gateway 선조회 증거]" in query
    assert "openshift-lightspeed exporter restartCount=44" in query


def test_action_proposal_fallback_is_non_empty_and_requests_target() -> None:
    policy = classify_request_policy("Pod 하나 재시작해줘")
    fallback = build_action_proposal_fallback(ChatRequest(message="Pod 하나 재시작해줘"), policy)

    assert "직접 실행할 수 없습니다" in fallback
    assert "namespace" in fallback
    assert "Pod 또는 관리 객체" in fallback


def test_empty_answer_fallback_includes_question_and_tool_summary() -> None:
    policy = classify_request_policy("ClusterOperator authentication 상태를 확인해줘")
    fallback = build_empty_answer_fallback(
        ChatRequest(message="ClusterOperator authentication 상태를 확인해줘"),
        policy,
        [
            {
                "name": "resources_list",
                "status": "success",
                "summary": "ClusterOperator authentication 조회 완료",
            }
        ],
    )

    assert "authentication" in fallback
    assert "resources_list" in fallback
    assert "조회 완료" in fallback


def test_cronjob_activity_evidence_trigger_for_15_minute_activity() -> None:
    assert should_collect_cronjob_activity_evidence("여기 15분 단위로 이러는데 맞아?")
    assert should_collect_cronjob_activity_evidence("notebook-cleaner CronJob 이 정상인지 확인해줘")
    assert not should_collect_cronjob_activity_evidence("현재 노드 상태 요약해줘")


def test_build_cronjob_activity_evidence_includes_schedule_env_and_recent_jobs() -> None:
    evidence = build_cronjob_activity_evidence(
        {
            "items": [
                {
                    "metadata": {"namespace": "tools-dev", "name": "notebook-cleaner"},
                    "spec": {
                        "schedule": "*/15 * * * *",
                        "concurrencyPolicy": "Forbid",
                        "successfulJobsHistoryLimit": 2,
                        "failedJobsHistoryLimit": 3,
                        "jobTemplate": {
                            "spec": {
                                "template": {
                                    "spec": {
                                        "containers": [
                                            {
                                                "image": (
                                                    "ghcr.io/jungyuoo/"
                                                    "ocpops-playbookstudio-sandbox:dev"
                                                ),
                                                "env": [
                                                    {
                                                        "name": (
                                                            "NOTEBOOK_HIBERNATE_AFTER_SECONDS"
                                                        ),
                                                        "value": "1800",
                                                    },
                                                    {
                                                        "name": "NOTEBOOK_RETENTION_DELETE_AFTER_SECONDS",
                                                        "value": "1209600",
                                                    },
                                                ],
                                            }
                                        ]
                                    }
                                }
                            }
                        },
                    },
                }
            ]
        },
        {
            "items": [
                {
                    "metadata": {
                        "namespace": "tools-dev",
                        "name": "notebook-cleaner-29147292",
                        "creationTimestamp": "2026-06-21T03:00:00Z",
                        "ownerReferences": [{"kind": "CronJob", "name": "notebook-cleaner"}],
                    },
                    "status": {
                        "startTime": "2026-06-21T03:00:01Z",
                        "completionTime": "2026-06-21T03:00:05Z",
                        "succeeded": 1,
                    },
                }
            ]
        },
        context_text="notebook-cleaner가 15분마다 보여",
    )

    assert "`notebook-cleaner`" in evidence
    assert "`*/15 * * * *`" in evidence
    assert "15분마다" in evidence
    assert "Forbid" in evidence
    assert "2 | 3 |" in evidence
    assert "`NOTEBOOK_HIBERNATE_AFTER_SECONDS`" in evidence
    assert "1800초 (30분)" in evidence
    assert "1209600초 (14일)" in evidence
    assert "threshold values only" in evidence
    assert "`notebook-cleaner-29147292`" in evidence


def test_build_cronjob_activity_evidence_matches_arbitrary_requested_interval() -> None:
    evidence = build_cronjob_activity_evidence(
        {
            "items": [
                {
                    "metadata": {"namespace": "ops", "name": "fifteen-minute-cleaner"},
                    "spec": {"schedule": "*/15 * * * *"},
                },
                {
                    "metadata": {"namespace": "ops", "name": "backup-cleaner"},
                    "spec": {"schedule": "*/30 * * * *"},
                },
            ]
        },
        context_text="backup-cleaner가 30분마다 보여",
    )

    assert "`backup-cleaner`" in evidence
    assert "30분마다" in evidence
    assert "`fifteen-minute-cleaner`" not in evidence


def test_build_pod_status_evidence_sorts_container_restart_counts() -> None:
    evidence = build_pod_status_evidence(
        {
            "items": [
                {
                    "metadata": {
                        "name": "lightspeed-app-server-abc",
                        "namespace": "openshift-lightspeed",
                        "ownerReferences": [{"kind": "ReplicaSet", "name": "lightspeed-app-server"}],
                    },
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [
                            {
                                "name": "lightspeed-service-api",
                                "ready": True,
                                "restartCount": 0,
                                "state": {"running": {"startedAt": "2026-06-16T01:40:29Z"}},
                            },
                            {
                                "name": "lightspeed-to-dataverse-exporter",
                                "ready": True,
                                "restartCount": 44,
                                "state": {"running": {"startedAt": "2026-06-16T05:04:55Z"}},
                                "lastState": {
                                    "terminated": {
                                        "reason": "Error",
                                        "exitCode": 137,
                                        "finishedAt": "2026-06-16T04:59:40Z",
                                    }
                                },
                            },
                        ],
                    },
                },
                {
                    "metadata": {
                        "name": "nginx-gateway-fabric-controller-manager-abc",
                        "namespace": "openshift-operators",
                    },
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [
                            {
                                "name": "manager",
                                "ready": True,
                                "restartCount": 36,
                                "state": {"running": {"startedAt": "2026-06-20T04:54:32Z"}},
                                "lastState": {
                                    "terminated": {
                                        "reason": "Error",
                                        "exitCode": 1,
                                        "finishedAt": "2026-06-20T04:54:32Z",
                                    }
                                },
                            }
                        ],
                    },
                },
            ]
        }
    )

    assert "Restart counts below are cumulative container-level counts" in evidence
    assert "`lightspeed-to-dataverse-exporter`" in evidence
    assert "`manager`" in evidence
    assert evidence.index("`lightspeed-to-dataverse-exporter`") < evidence.index("`manager`")
    assert "Error/137" in evidence


def test_build_pod_status_evidence_marks_failed_pod_start_time() -> None:
    evidence = build_pod_status_evidence(
        {
            "items": [
                {
                    "metadata": {"name": "installer-1-node-a", "namespace": "openshift-example"},
                    "status": {
                        "phase": "Failed",
                        "startTime": "2026-06-09T08:55:51Z",
                        "containerStatuses": [
                            {
                                "name": "installer",
                                "ready": False,
                                "restartCount": 0,
                                "state": {
                                    "terminated": {
                                        "reason": "Error",
                                        "exitCode": 1,
                                    }
                                },
                            }
                        ],
                    },
                }
            ]
        }
    )

    assert "old Failed pods can be historical artifacts" in evidence
    assert "2026-06-09T08:55:51Z" in evidence
    assert "Failed / terminated:Error/1" in evidence


def test_build_cluster_operator_status_evidence_summarizes_operator_health() -> None:
    evidence = build_cluster_operator_status_evidence(
        {
            "items": [
                {
                    "metadata": {"name": "example-operator"},
                    "status": {
                        "versions": [{"version": "4.20.23"}],
                        "conditions": [
                            {"type": "Available", "status": "True"},
                            {"type": "Degraded", "status": "False"},
                            {"type": "Progressing", "status": "False"},
                        ],
                    },
                }
            ]
        }
    )

    assert "ClusterOperator status evidence" in evidence
    assert "example-operator" in evidence
    assert "Available | Degraded | Progressing" in evidence
    assert "True | False | False" in evidence


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
            '"kind": "Pod", "namespace": "example-namespace", '
            '"name": "example-catalog-pod"}, "id": "tool-1"}\n'
        )
        yield (
            'Tool result: {"name": "resources_get", "status": "success", '
            '"content": "apiVersion: v1\\nkind: Pod\\nmetadata:\\n  name: '
            'example-catalog-pod\\n  namespace: example-namespace\\n", '
            '"id": "tool-1"}\n'
        )
        yield (
            'Tool result: {"name": "resources_get", "status": "error", '
            '"content": "Tool failed: resource not allowed", "id": "tool-2"}\n'
        )

    async def run() -> list[dict]:
        return [event async for event in split_plain_text_events(chunks())]

    events = asyncio.run(run())

    assert events[0]["summary"] == "Pod example-namespace/example-catalog-pod 상세 조회"
    assert events[1]["summary"] == "Pod example-namespace/example-catalog-pod 조회 완료"
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
    assert evidence["sourceType"] == "ols-tool-result"
    assert evidence["summary"] == "Pod 조회 완료"


def test_build_evidence_reference_events_supports_gateway_preflight_source() -> None:
    subject = safe_subject({"username": "user@example.com", "uid": "uid-1", "groups": ["ops"]})
    event = {
        "type": "tool_result",
        "name": "pod_status_evidence",
        "status": "success",
        "summary": "Pod 상태/재시작 증거 수집 완료",
        "detail": "Gateway-collected Pod status evidence",
    }

    events = build_evidence_reference_events(
        event=event,
        incident_id="inc-1",
        run_id="run-1",
        source_type="gateway-preflight-evidence",
        subject=subject,
    )

    assert events[0]["type"] == "tool_call"
    assert events[0]["name"] == "evidence_ref"
    assert events[1]["type"] == "tool_result"
    assert events[1]["result"]["sourceType"] == "gateway-preflight-evidence"
    assert events[1]["result"]["summary"] == "Pod 상태/재시작 증거 수집 완료"


def test_can_subject_read_record_requires_same_observed_identity() -> None:
    subject = safe_subject({"username": "user@example.com", "uid": "uid-1", "groups": ["ops"]})
    other_subject = safe_subject({"username": "other@example.com", "uid": "uid-2", "groups": ["ops"]})
    record = {"originatingSubject": subject}

    assert can_subject_read_record(record, subject)
    assert not can_subject_read_record(record, other_subject)


def test_evidence_api_reads_stored_evidence_with_read_time_authorization() -> None:
    EVIDENCE_RECORDS.clear()
    subject = safe_subject(None)
    event = {
        "type": "tool_result",
        "name": "resources_get",
        "status": "success",
        "summary": "테스트 증거",
        "detail": "password=secret-value\nkind: Pod",
    }
    events = build_evidence_reference_events(
        event=event,
        incident_id="inc-test",
        run_id="run-test",
        source_type="gateway-preflight-evidence",
        subject=subject,
    )
    evidence_id = events[1]["result"]["evidenceId"]

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/v1/evidence/{evidence_id}",
                headers={"Authorization": "Bearer test-token"},
            )
            list_response = await client.get(
                "/v1/evidence?incidentId=inc-test",
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["kind"] == "Evidence"
        assert payload["spec"]["detail"] == "password=[REDACTED]\nkind: Pod"
        assert list_response.status_code == 200
        assert list_response.json()["items"][0]["evidenceId"] == evidence_id
        assert "detail" not in list_response.json()["items"][0]

    asyncio.run(run())


def test_workflow_and_metrics_endpoints_expose_non_secret_runtime_state() -> None:
    WORKFLOW_RECORDS.clear()
    METRICS["aiops_chat_requests_total"] = 3
    subject = safe_subject(None)
    WORKFLOW_RECORDS["run-test"] = {
        "runId": "run-test",
        "status": "completed",
        "subject": subject,
        "target": {"messageLength": 10},
    }

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            workflow_response = await client.get(
                "/v1/workflows/run-test",
                headers={"Authorization": "Bearer test-token"},
            )
            metrics_response = await client.get("/metrics")

        assert workflow_response.status_code == 200
        assert workflow_response.json()["spec"]["status"] == "completed"
        assert metrics_response.status_code == 200
        assert "aiops_chat_requests_total 3" in metrics_response.text
        assert "Bearer" not in metrics_response.text

    asyncio.run(run())


def test_diagnostic_request_digest_uses_request_projection_without_target_hardcoding() -> None:
    subject = safe_subject({"username": "user@example.com", "uid": "uid-1", "groups": ["ops"]})
    request = DiagnosticRequestCreate(
        targetNode=DiagnosticTargetNode(name="node-a.example.com", uid="node-uid-a"),
        collector="kubelet_logs",
        timeRange=DiagnosticTimeRange(
            since="2026-06-21T00:00:00Z",
            until="2026-06-21T00:05:00Z",
        ),
        limits=DiagnosticLimits(deadline="30s", maxBytes=4096, maxLines=1000),
        evidencePolicy=DiagnosticEvidencePolicy(
            classification="restricted",
            rawStorageAllowed=False,
            redactionPolicyDigest="sha256:redaction-policy",
        ),
        policy={
            "policyDecisionId": "pd-1",
            "policyBundleHash": "sha256:bundle",
            "policyInputDigest": "sha256:input",
            "policyDecisionDigest": "sha256:decision",
        },
    )
    candidate = build_diagnostic_request_candidate(request, subject)
    digest = diagnostic_request_digest(candidate)

    changed_target = request.model_copy(
        update={"targetNode": DiagnosticTargetNode(name="node-b.example.com", uid="node-uid-b")}
    )
    changed_candidate = build_diagnostic_request_candidate(changed_target, subject)

    assert digest.startswith("sha256:")
    assert candidate["requester"]["username"] == "user@example.com"
    assert candidate["targetNode"]["name"] == "node-a.example.com"
    assert diagnostic_request_digest(changed_candidate) != digest


def test_diagnostic_request_record_stores_only_grant_reference() -> None:
    subject = safe_subject({"username": "user@example.com", "uid": "uid-1", "groups": ["ops"]})
    request = DiagnosticRequestCreate(
        targetNode=DiagnosticTargetNode(name="node-a.example.com", uid="node-uid-a"),
        collector="kubelet_logs",
        timeRange=DiagnosticTimeRange(
            since="2026-06-21T00:00:00Z",
            until="2026-06-21T00:05:00Z",
        ),
    )

    record = build_diagnostic_request_record(request, subject)

    assert record["metadata"]["name"].startswith("diag-")
    assert record["spec"]["grantRef"]["bearerGrantStored"] is False
    assert record["spec"]["status"]["submittedToController"] is False
    assert record["spec"]["status"]["phase"] in {"disabled", "pending_controller_submission"}
    assert "Bearer" not in str(record)


def test_diagnostic_request_api_creates_disabled_foundation_with_read_authorization() -> None:
    DIAGNOSTIC_REQUESTS.clear()

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            create_response = await client.post(
                "/v1/diagnostics/requests",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "incidentId": "inc-diag",
                    "runId": "run-diag",
                    "targetNode": {"name": "node-a.example.com", "uid": "node-uid-a"},
                    "collector": "kubelet_logs",
                    "timeRange": {
                        "since": "2026-06-21T00:00:00Z",
                        "until": "2026-06-21T00:05:00Z",
                    },
                    "requester": {"username": "attacker@example.com"},
                },
            )

        assert create_response.status_code == 422

        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            create_response = await client.post(
                "/v1/diagnostics/requests",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "incidentId": "inc-diag",
                    "runId": "run-diag",
                    "targetNode": {"name": "node-a.example.com", "uid": "node-uid-a"},
                    "collector": "kubelet_logs",
                    "timeRange": {
                        "since": "2026-06-21T00:00:00Z",
                        "until": "2026-06-21T00:05:00Z",
                    },
                },
            )
            payload = create_response.json()
            request_id = payload["metadata"]["name"]
            read_response = await client.get(
                f"/v1/diagnostics/requests/{request_id}",
                headers={"Authorization": "Bearer test-token"},
            )

        assert create_response.status_code == 200
        assert payload["kind"] == "DiagnosticRequest"
        assert payload["spec"]["candidate"]["requester"]["username"] == "unknown"
        assert payload["spec"]["candidate"]["targetNode"]["name"] == "node-a.example.com"
        assert payload["spec"]["grantRef"]["bearerGrantStored"] is False
        assert payload["spec"]["status"]["submittedToController"] is False
        assert read_response.status_code == 200
        assert read_response.json()["metadata"]["name"] == request_id

    asyncio.run(run())
