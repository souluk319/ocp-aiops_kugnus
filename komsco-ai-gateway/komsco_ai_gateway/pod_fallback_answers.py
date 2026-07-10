import re
from collections.abc import Callable, Mapping
from typing import Any

from .answer_planning import (
    GatewayFallbackPlanInput,
    build_gateway_fallback_answer_plan,
    render_answer_plan,
)
from .answer_streaming import truncate_detail
from .page_context import normalize_console_page_context, page_context_is_pod_workload
from .pod_action_candidates import pod_inventory_check_commands, pod_row_target
from .pod_evidence_parsing import (
    CRASHLOOPBACKOFF_PLAIN_DEFINITION,
    app_label_from_labels,
    choose_gateway_pod_row,
    command_suggests_immediate_exit,
    deployment_from_owner_chain,
    is_pod_namespace_pattern_lookup_request,
    looks_non_production_context,
    message_mentions_crashloop,
    parse_gateway_current_pod_list_rows,
    parse_gateway_pod_evidence_rows,
    pod_inventory_message_requests_problem_scope,
    pod_inventory_message_requests_restart_history,
    pod_inventory_restart_observation_rows,
    pod_inventory_selected_rows,
    pod_namespace_lookup_pattern,
    pod_row_has_completed_restart_loop,
    pod_row_has_current_failure,
    pod_row_has_error_exit,
    pod_row_priority,
)
from .security import redact_sensitive

ChatRequest = Any
_dependency_provider: Callable[[], Any] | None = None


def _configure_dependency_provider(provider: Callable[[], Any]) -> None:
    global _dependency_provider
    _dependency_provider = provider


def _require_dependencies() -> Any:
    if _dependency_provider is None:
        raise RuntimeError("pod fallback dependencies are not configured")
    return _dependency_provider()


def build_pod_namespace_pattern_lookup_answer(
    req: ChatRequest,
    gateway_evidence: str | None,
) -> str | None:
    if not is_pod_namespace_pattern_lookup_request(req.message):
        return None

    rows, namespace_filter, rows_shown = parse_gateway_current_pod_list_rows(gateway_evidence)
    evidence_scope = "Current Pod list evidence"
    if not rows:
        rows = parse_gateway_pod_evidence_rows(gateway_evidence)
        evidence_scope = "Pod status evidence 상위 항목"
    if not rows:
        return None

    pattern = pod_namespace_lookup_pattern(req.message)
    grouped: dict[str, set[str]] = {}
    matched_rows_by_key: dict[tuple[str, str], Mapping[str, str]] = {}
    for row in rows:
        namespace = str(row.get("namespace") or "").strip()
        pod = str(row.get("pod") or "").strip()
        if not namespace or not pod or namespace == "-" or pod == "-":
            continue
        if pattern and pattern not in pod.lower():
            continue
        grouped.setdefault(namespace, set()).add(pod)
        matched_rows_by_key.setdefault((namespace, pod), row)

    title_pattern = pattern or "Pod"
    sorted_groups = sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0]))
    displayed_groups = sorted_groups[:10]
    hidden_count = max(len(sorted_groups) - len(displayed_groups), 0)
    total_pods = sum(len(pods) for _, pods in sorted_groups)
    displayed_pod_rows: list[Mapping[str, str]] = []
    display_pod_limit = 30
    for namespace, pods in displayed_groups:
        for pod in sorted(pods):
            if len(displayed_pod_rows) >= display_pod_limit:
                break
            row = matched_rows_by_key.get((namespace, pod))
            if row:
                displayed_pod_rows.append(row)
        if len(displayed_pod_rows) >= display_pod_limit:
            break
    hidden_pod_count = max(total_pods - len(displayed_pod_rows), 0)

    lines = [
        "## 테스트 Pod 네임스페이스",
        "",
        "### 요약",
        (
            f"Pod 이름에 `{title_pattern}`가 포함된 Pod는 {len(sorted_groups)}개 namespace에서 {total_pods}개 확인했습니다."
            if pattern
            else f"현재 조회 범위에서 Pod가 있는 namespace {len(sorted_groups)}개를 확인했습니다."
        ),
        f"- 매칭 Pod 총합: {total_pods}개",
        f"- 수집 row: {len(rows)}" + (f" (수집 표시: `{rows_shown}`)" if rows_shown else ""),
        f"- Evidence 범위: `{evidence_scope}`",
        f"- Namespace filter: `{namespace_filter or 'all-accessible-namespaces'}`",
        *(
            [f"- 표시는 상위 {len(displayed_groups)}개 namespace로 제한했습니다. 추가 {hidden_count}개 namespace는 상세 확인 대상입니다."]
            if hidden_count
            else []
        ),
        "",
        "### 확인 결과",
    ]

    if displayed_groups:
        lines.extend(
            [
                "| Namespace | Pod 이름 | 현재 상태 | Ready |",
                "| :--- | :--- | :--- | :---: |",
            ]
        )
        for row in displayed_pod_rows:
            namespace = str(row.get("namespace") or "-")
            pod = str(row.get("pod") or "-")
            current_state = str(row.get("currentState") or "-")
            ready = str(row.get("ready") or "-")
            lines.append(f"| {namespace} | `{pod}` | {current_state} | {ready} |")
        if hidden_pod_count:
            lines.append("")
            lines.append(f"- 표시는 매칭 Pod {len(displayed_pod_rows)}개로 제한했습니다. 추가 {hidden_pod_count}개는 대상 namespace에서 확인할 수 있습니다.")
    else:
        lines.append(
            f"- Pod 이름에 `{title_pattern}`가 포함된 Pod가 있는 namespace는 현재 조회 범위에서 확인되지 않았습니다."
            if pattern
            else "- 현재 조회 범위에서 Pod가 있는 namespace를 확인하지 못했습니다."
        )

    lines.extend(
        [
            "",
            "### 판단",
            "- 이 답변은 모델 추론이 아니라 Gateway가 Kubernetes API로 수집한 Pod 목록을 기준으로 정리한 결과입니다.",
            "- namespace 이름이 아니라 Pod 이름 기준으로 매칭했습니다.",
            "- 정리나 삭제는 실행하지 않았습니다.",
            "",
            "### 다음 확인 명령",
            "필요하면 대상 namespace만 좁혀서 확인합니다.",
            "",
            "```bash",
        ]
    )
    if displayed_groups:
        for namespace, _pods in displayed_groups[:3]:
            lines.append(
                f"oc get pods -n {namespace}"
                + (f" | grep {pattern}" if pattern else "")
            )
    else:
        lines.append("oc get pods -A")
    lines.extend(["```", "", "### 사용한 확인 결과", "- Pod 이름", "- Namespace", "- 현재 Pod 목록"])
    return "\n".join(lines)



def build_pod_list_fallback(req: ChatRequest, gateway_evidence: str | None) -> str | None:
    dependencies = _require_dependencies()
    if not dependencies.is_pod_list_request(req.message):
        return None

    namespace_lookup_answer = dependencies.build_pod_namespace_pattern_lookup_answer(
        req, gateway_evidence
    )
    if namespace_lookup_answer:
        return namespace_lookup_answer

    rows, namespace_filter, rows_shown = parse_gateway_current_pod_list_rows(gateway_evidence)
    evidence_scope = "Current Pod list evidence"
    if not rows:
        rows = parse_gateway_pod_evidence_rows(gateway_evidence)
        evidence_scope = "Pod status evidence 상위 항목"

    namespace = dependencies.pod_list_namespace(req) or namespace_filter or "all-accessible-namespaces"
    if namespace and namespace != "all-accessible-namespaces":
        rows = [row for row in rows if row.get("namespace") == namespace]

    if not rows:
        return "\n".join(
            [
                "## Pod 상태 목록",
                "",
                "### 요약",
                "현재 조회 범위에서 Pod 목록을 확인했지만 표시할 Pod가 없습니다.",
                "",
                "### 확인 결과",
                f"- Namespace: `{namespace}`",
                "- 조회된 Pod가 없습니다.",
                "- Evidence 범위: `Current Pod list evidence`",
                "- 현재 수집 범위에서는 Pod 장애를 확인하지 못했습니다.",
                "",
                "### 다음 확인 명령",
                "조회 범위를 다시 확인합니다.",
                "",
                f"```bash\n{f'oc get pods -n {namespace}' if namespace != 'all-accessible-namespaces' else 'oc get pods -A'}\n```",
                "",
                "### 사용한 확인 결과",
                "- Pod 상세, Event, 로그는 대상 Pod가 식별되지 않아 확인하지 못했습니다.",
            ]
        )

    total_rows = len(rows)
    current_failure_rows = [row for row in rows if pod_row_has_current_failure(row)]
    error_exit_rows = [row for row in rows if pod_row_has_error_exit(row)]
    completed_restart_rows = [row for row in rows if pod_row_has_completed_restart_loop(row)]
    restart_observation_rows = pod_inventory_restart_observation_rows(rows)
    selected_rows = pod_inventory_selected_rows(req.message, rows)
    problem_scope = pod_inventory_message_requests_problem_scope(req.message)
    display_limit = 10 if problem_scope else 20
    display_rows = selected_rows[:display_limit]
    hidden_count = max(len(selected_rows) - len(display_rows), 0)
    top_targets = ", ".join(pod_row_target(row) for row in display_rows[:2]) or "없음"
    commands = pod_inventory_check_commands(display_rows, namespace)
    if problem_scope:
        summary = (
            f"현재 조회 범위에서 에러/비정상 Pod/Container {len(selected_rows)}건을 확인했습니다."
            if selected_rows
            else "현재 조회 범위에서 에러/비정상 Pod/Container는 확인되지 않았습니다."
        )
    else:
        summary = f"현재 조회 범위에서 Pod/Container {total_rows}건을 확인했습니다."

    lines = [
        "## Pod 상태 목록",
        "",
        "### 요약",
        summary,
        f"- 수집 row: {total_rows}" + (f" (수집 표시: `{rows_shown}`)" if rows_shown else ""),
        f"- 문제 의심 Pod/Container: {len(selected_rows)}건",
        f"- 즉시 장애 상태(CrashLoopBackOff/ImagePullBackOff/Pending/NotReady): {len(current_failure_rows)}건",
        f"- 최근 Error 종료 이력: {len(error_exit_rows)}건",
        f"- 재시작 관찰 항목(Completed/0 포함): {len(restart_observation_rows)}건",
        f"- 우선 확인 대상: {top_targets}",
        *([f"- 표시는 우선순위 상위 {len(display_rows)}건으로 제한했습니다. 추가 {hidden_count}건은 상세 확인 대상입니다."] if hidden_count else []),
        *(
            [
                "- 이번 질문은 에러 상태 기준이므로 단순 재시작 이력만 있는 항목은 기본 표에서 제외했습니다."
            ]
            if problem_scope and restart_observation_rows and not pod_inventory_message_requests_restart_history(req.message)
            else []
        ),
        "",
        "### 우선순위 표",
    ]
    if display_rows:
        lines.extend(
            [
                "| 우선순위 | Namespace | Pod | Container | 현재 상태 | Ready | Restart | Last State | 판단 |",
                "| :--- | :--- | :--- | :--- | :--- | :---: | ---: | :--- | :--- |",
            ]
        )
        for row in display_rows:
            _, priority, reason = pod_row_priority(row)
            lines.append(
                "| {priority} | {namespace} | `{pod}` | `{container}` | {currentState} | {ready} | {restarts} | {lastState} | {reason} |".format(
                    priority=priority,
                    namespace=row.get("namespace") or "-",
                    pod=row.get("pod") or "-",
                    container=row.get("container") or "-",
                    currentState=row.get("currentState") or "-",
                    ready=row.get("ready") or "-",
                    restarts=row.get("restarts") or "0",
                    lastState=row.get("lastState") or "-",
                    reason=reason,
                )
            )
    else:
        lines.append("- 표시할 에러/비정상 Pod가 없습니다.")

    lines.extend(
        [
            "",
            "### 판단",
        ]
    )
    if current_failure_rows:
        lines.append("- 현재 비정상 상태 또는 Ready 아님인 항목을 먼저 확인해야 합니다.")
    if error_exit_rows:
        lines.append("- `Error` 종료 이력이 있는 항목은 이전 로그와 Event를 우선 확인합니다.")
    if completed_restart_rows:
        lines.append(
            "- `Running` + `Completed/0` 항목은 장애 확정이 아닙니다. 정상 종료 후 재시작되는 작업성 컨테이너인지 확인해야 합니다."
        )
    if not selected_rows:
        lines.append("- 현재 목록 기준 즉시 장애나 재시작 이력 신호는 낮습니다.")
    lines.extend(
        [
            "",
            "### 다음 확인 명령",
            "우선순위가 높은 대상부터 확인합니다.",
            "",
            "```bash",
            *commands,
            "```",
            "",
            "### 사용한 확인 결과",
            f"- Namespace: `{namespace}`",
            f"- Evidence 범위: `{evidence_scope}`",
            "- Pod 상태",
            "- Container Ready",
            "- Restart count",
            "- Last termination state",
            "- Owner reference",
        ]
    )

    return "\n".join(lines)


def build_pod_evidence_fallback(req: ChatRequest, gateway_evidence: str | None) -> str | None:
    rows = parse_gateway_pod_evidence_rows(gateway_evidence)
    row = choose_gateway_pod_row(rows, req.message)
    if not row:
        return None

    namespace = row.get("namespace") or "unknown"
    pod = row.get("pod") or "unknown"
    container = row.get("container") or "unknown"
    state = row.get("currentState") or "-"
    ready = row.get("ready") or "-"
    restarts = row.get("restarts") or "-"
    last_state = row.get("lastState") or "-"
    last_finished = row.get("lastFinished") or "-"
    image = row.get("image") or "-"
    command = row.get("command") or "-"
    args = row.get("args") or "-"
    labels = row.get("labels") or "-"
    owner_chain = row.get("ownerChain") or row.get("owner") or "-"
    deployment = deployment_from_owner_chain(owner_chain)
    app_label = app_label_from_labels(labels)

    cause = "컨테이너가 `CrashLoopBackOff`/waiting 상태이며 마지막 종료 상태와 restart count가 확인됩니다."
    if command != "-" and command_suggests_immediate_exit(command, args):
        cause = "컨테이너 실행 명령/args가 프로세스의 즉시 종료를 유발하는 형태로 확인됩니다."

    lines = [
        CRASHLOOPBACKOFF_PLAIN_DEFINITION,
        "",
        f"이 Pod의 경우 {cause}",
        "",
        "## RCA 보고서",
        "",
        "### 현재 판단",
        "Gateway가 수집한 Kubernetes 확인 결과 기준으로 대상 Pod를 우선 분석했습니다.",
        "",
        "### 원인 후보",
        f"- 1순위 후보: {cause}",
        "- 로그, Event, resource limit, image pull 세부 원인은 추가 확인 결과가 있어야 확정할 수 있습니다.",
        "",
        "### 확인 결과",
        f"- 대상: `{namespace}` / Pod `{pod}` / Container `{container}`",
        f"- 현재 상태: {state}, Ready `{ready}`, restart count `{restarts}`",
        f"- 마지막 종료: `{last_state}`" + (f", `{last_finished}`" if last_finished != "-" else ""),
        f"- 원인 기준: {cause}",
        f"- 이미지: `{image}`",
        f"- Command: `{command}`",
        f"- Args: `{args}`",
        f"- 관리 객체: `{owner_chain}`",
        "",
        "### 조치 방법",
    ]

    if deployment:
        lines.append(
            f"- 단순 Pod 삭제나 rollout restart만으로는 같은 template이 다시 실행되어 재발할 수 있습니다. "
            f"`deployment/{deployment}`의 command/args/image/env/config 또는 정상 revision을 수정 후보로 잡으세요. 이 단계에서는 실행하지 않습니다."
        )
    else:
        lines.append(
            "- 상위 Deployment가 Gateway evidence에서 확정되지 않았습니다. Pod owner chain을 먼저 확인한 뒤 관리 객체를 대상으로 수정하세요."
        )
    lines.append(
        "- 이번 응답에서는 조치 후보, 조치 계획, 승인, 실행 기록을 만들지 않았습니다. "
        "현재 요청은 조회 중심 RCA로 처리됐으며, 실행 기록이 필요하면 실행 가능 모드에서 `조치 계획 생성`을 명시해야 합니다."
    )
    if looks_non_production_context(row) and deployment:
        lines.append(
            "- 테스트/시나리오 리소스라면 정리 여부를 별도 조치 후보로 검토하세요. "
            "Stage 3 RCA 답변에서는 삭제 명령을 실행하거나 제시하지 않습니다."
        )

    lines.extend(
        [
            "",
            "### 추가 확인",
            "- 이 fallback은 Gateway 사전 수집 표 기반입니다. Pod 상세/Event/previous log 조회가 실패했거나 아직 수행되지 않은 항목은 확정하지 않습니다.",
        ]
    )
    if deployment:
        lines.append("```bash")
        lines.append(f"oc rollout status deployment/{deployment} -n {namespace}")
        if app_label:
            lines.append(f"oc get pod -n {namespace} -l app={app_label}")
        else:
            lines.append(f"oc get pod -n {namespace} --show-labels")
        lines.append(f"oc logs {pod} -n {namespace} -c {container} --previous --tail=120")
        lines.append("```")
    else:
        lines.append("```bash")
        lines.append(f"oc get pod {pod} -n {namespace} -o yaml")
        lines.append(f"oc get rs -n {namespace} --show-labels")
        lines.append("```")

    lines.extend(
        [
            "",
            "### 재발 방지",
            "- 현재 상태와 Event를 확인해 현재 장애인지 과거 이력인지 분리합니다.",
            "- command/args/image/env/config처럼 template에 남는 원인을 먼저 수정 후보로 봅니다.",
            "- 실행 조치는 별도 승인 전까지 제안만 유지합니다.",
        ]
    )

    return "\n".join(lines)


def build_grounded_aiops_answer(
    req: ChatRequest,
    runtime_tool_plan: Mapping[str, Any],
    gateway_evidence: str | None,
) -> str | None:
    dependencies = _require_dependencies()
    namespace_lookup_answer = dependencies.build_pod_namespace_pattern_lookup_answer(
        req, gateway_evidence
    )
    if namespace_lookup_answer:
        return namespace_lookup_answer

    task_type = str(runtime_tool_plan.get("task_type") or "")
    if task_type == "pod_inventory":
        return dependencies.build_pod_list_fallback(req, gateway_evidence)
    if task_type == "pod_screen_rca" and page_context_is_pod_workload(req):
        return dependencies.build_pod_evidence_fallback(req, gateway_evidence)
    return None


INTERNAL_FALLBACK_DIAGNOSTIC_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bGateway fallback\b", re.IGNORECASE),
    re.compile(r"\blightspeed_stream\b", re.IGNORECASE),
    re.compile(r"OpenShift Lightspeed request failed", re.IGNORECASE),
    re.compile(r"ended without answer text", re.IGNORECASE),
    re.compile(r"RAG evidence unavailable", re.IGNORECASE),
    re.compile(r"pgvector .*failed", re.IGNORECASE),
    re.compile(r"expected \d+ dimensions", re.IGNORECASE),
    re.compile(r"streamProbe|gatewayContextDigest", re.IGNORECASE),
)


def is_internal_fallback_diagnostic(value: object) -> bool:
    text = str(value or "")
    return bool(text) and any(pattern.search(text) for pattern in INTERNAL_FALLBACK_DIAGNOSTIC_PATTERNS)


def public_gateway_evidence_excerpt(gateway_evidence: str | None, *, max_lines: int = 8) -> str:
    if not gateway_evidence:
        return ""
    public_lines: list[str] = []
    for raw_line in str(redact_sensitive(gateway_evidence)).splitlines():
        line = raw_line.strip()
        if not line or is_internal_fallback_diagnostic(line):
            continue
        public_lines.append(line)
        if len(public_lines) >= max_lines:
            break
    return "\n".join(public_lines)


def build_image_answer_fallback(
    req: ChatRequest,
    tool_results: list[Mapping[str, Any]],
    gateway_evidence: str | None,
    *,
    image_analysis: str | None = None,
    image_forwarded_to_ols: bool = False,
) -> str:
    _ = image_forwarded_to_ols
    image_count = len(req.attachments)
    evidence_excerpt = public_gateway_evidence_excerpt(gateway_evidence, max_lines=6)
    failed_tools = [
        str(item.get("name") or item.get("evidenceType") or "확인 단계")
        for item in tool_results
        if str(item.get("status") or "").lower() in {"error", "failed", "timeout"}
        and not is_internal_fallback_diagnostic(item.get("name"))
        and not is_internal_fallback_diagnostic(item.get("summary"))
        and not is_internal_fallback_diagnostic(item.get("detail"))
    ]

    lines: list[str] = [
        "## 현재 판단",
    ]
    if image_analysis:
        lines.extend(
            [
                "첨부 화면에서 확인한 내용을 기준으로 정리합니다. 서버 변경은 실행하지 않았습니다.",
                "",
                "## 화면에서 확인한 내용",
                redact_sensitive(image_analysis).strip(),
            ]
        )
    else:
        lines.extend(
            [
                "첨부 화면 분석 답변을 완성하지 못했습니다. 서버 변경은 실행하지 않았습니다.",
                "",
                "## 확인 상태",
                f"- 이미지 수신: {image_count}건",
                "- 화면 판독 결과: 아직 확보하지 못함",
            ]
        )

    if evidence_excerpt:
        lines.extend(
            [
                "",
                "## 함께 확인된 정보",
                evidence_excerpt,
            ]
        )

    lines.extend(
        [
            "",
            "## 다음 확인",
            "- 알림 또는 리소스 상세 화면에서 대상 namespace, kind, name을 확인합니다.",
            "- 같은 화면으로 다시 질문해 이미지 전달과 모델 응답 단계를 진행 상세에서 확인합니다.",
        ]
    )
    if failed_tools:
        lines.append(f"- 실패한 확인 단계: {', '.join(dict.fromkeys(failed_tools))}")

    return "\n".join(lines)


def build_ols_required_failure_answer(
    req: ChatRequest,
    tool_results: list[Mapping[str, Any]],
    *,
    image_analysis: str | None = None,
    image_forwarded_to_ols: bool = False,
) -> str:
    dependencies = _require_dependencies()
    _ = image_forwarded_to_ols
    failed_steps = [
        str(item.get("name") or item.get("evidenceType") or "확인 단계")
        for item in tool_results
        if str(item.get("status") or "").lower() in {"error", "failed", "timeout"}
        and not is_internal_fallback_diagnostic(item.get("name"))
        and not is_internal_fallback_diagnostic(item.get("summary"))
        and not is_internal_fallback_diagnostic(item.get("detail"))
    ]
    lines = [
        "## 현재 상태",
        f"{dependencies.active_llm_label()} 최종 답변을 받지 못해 RCA 답변을 생성하지 않았습니다.",
        "Gateway는 조회 계획, 확인 결과, RCA Context를 준비했지만 최종 분석은 Lightspeed 응답 기준으로 제공해야 합니다.",
        "",
        "## 확인한 것",
        "- 서버 변경: 실행하지 않음",
        "- Gateway 역할: Tool Plan/Evidence/RCA Context를 준비하고 모델에 전달",
    ]
    if req.attachments:
        lines.append(f"- 이미지 첨부: {len(req.attachments)}건 수신")
        if image_analysis:
            lines.append("- 화면 분석 보조 결과: 확보됨")
    if failed_steps:
        lines.append(f"- 실패 단계: {', '.join(dict.fromkeys(failed_steps))}")

    lines.extend(
        [
            "",
            "## 다음 조치",
            "- VPN/FortiClient, OLS 연결, 사용자 토큰 상태를 확인한 뒤 같은 요청을 다시 실행합니다.",
            "- 반복되면 진행 상세의 Lightspeed 오류와 Gateway context digest를 함께 확인합니다.",
        ]
    )
    return "\n".join(lines)


def build_empty_answer_fallback(
    req: ChatRequest,
    policy: Mapping[str, Any],
    tool_results: list[Mapping[str, Any]],
    gateway_evidence: str | None = None,
    *,
    image_analysis: str | None = None,
    image_forwarded_to_ols: bool = False,
) -> str:
    dependencies = _require_dependencies()
    if (
        policy.get("decision") == "action_proposal_only"
        and not dependencies.crashloop_demo_target_from_request(req)
    ):
        return dependencies.build_action_proposal_fallback(req, policy)

    if req.attachments:
        return dependencies.build_image_answer_fallback(
            req,
            tool_results,
            gateway_evidence,
            image_analysis=image_analysis,
            image_forwarded_to_ols=image_forwarded_to_ols,
        )

    answer_plan = build_gateway_fallback_answer_plan(
        GatewayFallbackPlanInput(
            message=req.message,
            policy=policy,
            tool_results=tool_results,
            gateway_evidence=gateway_evidence,
        )
    )
    if answer_plan:
        return render_answer_plan(answer_plan)

    pod_list_fallback = dependencies.build_pod_list_fallback(req, gateway_evidence)
    if pod_list_fallback:
        return pod_list_fallback

    pod_fallback = dependencies.build_pod_evidence_fallback(req, gateway_evidence)
    if pod_fallback:
        return pod_fallback

    # ── classify tool_results ──────────────────────────────────
    _OK = {"success", "ok"}
    _MISS = {"skipped", "missing", "error"}
    ok_events: list[dict] = []
    miss_events: list[dict] = []
    inline_blocks: list[str] = []   # pre-formatted markdown tables (node, alert)

    for ev in tool_results:
        if not isinstance(ev, dict):
            continue
        status = str(ev.get("status") or "")
        detail = str(ev.get("detail") or "")
        summary = str(ev.get("summary") or "")
        name = str(ev.get("name") or ev.get("evidenceType") or "")
        if (
            is_internal_fallback_diagnostic(name)
            or is_internal_fallback_diagnostic(summary)
            or is_internal_fallback_diagnostic(detail)
        ):
            continue
        if status in _OK:
            # detect already-formatted markdown tables in detail
            if "\n|" in detail and ("EvidenceType:" in detail or "Summary:" in detail):
                # strip noisy header lines, keep the formatted block
                block_lines = [
                    ln for ln in detail.splitlines()
                    if not ln.startswith("Gateway-collected")
                    and not ln.startswith("EvidenceType:")
                    and ln.strip()
                ]
                if block_lines:
                    inline_blocks.append("\n".join(block_lines))
            else:
                ok_events.append(ev)
        elif status in _MISS:
            miss_events.append(ev)

    # ── query namespace for oc commands ──────────────────────
    ctx = normalize_console_page_context(req.pageContext)
    ns = str(ctx.get("namespace") or "default")

    # ── build answer ─────────────────────────────────────────
    crashloop_intro = (
        [
            CRASHLOOPBACKOFF_PLAIN_DEFINITION,
            "",
        ]
        if message_mentions_crashloop(req.message)
        or re.search(r"CrashLoopBackOff", str(gateway_evidence or ""), re.IGNORECASE)
        else []
    )
    lines: list[str] = [
        *crashloop_intro,
        "## RCA 보고서",
        "",
        "### 현재 판단",
        "- 현재 확인된 조회 결과 기준으로 정리합니다. 원인은 후보로만 봅니다.",
        "",
        "### 원인 후보",
        "- Event, Pod 상태, metric, log-pattern 확인 결과가 함께 맞을 때만 원인으로 확정합니다.",
        "",
        "### 확인 결과",
        f"- 질문: {redact_sensitive(req.message)}",
        "- 확인된 운영 정보만 답변에 사용했습니다.",
        "",
    ]

    # collected summary table
    if ok_events:
        lines.append("| 증거 유형 | 내용 |")
        lines.append("| :--- | :--- |")
        for ev in ok_events:
            ev_type = str(ev.get("evidenceType") or ev.get("name") or "-")
            detail = str(ev.get("detail") or "")
            summary = str(ev.get("summary") or "")
            # prefer detail that isn't raw JSON or generic header
            if detail and not detail.startswith("{") and not detail.startswith("Gateway-collected"):
                desc = truncate_detail(detail, 160)
            else:
                desc = truncate_detail(summary, 160)
            lines.append(f"| `{ev_type}` | {desc} |")
        lines.append("")
    else:
        evidence_excerpt = public_gateway_evidence_excerpt(gateway_evidence, max_lines=8)
        if evidence_excerpt:
            lines.append(truncate_detail(evidence_excerpt, 800))
        else:
            lines.append("- 수집 완료로 표시된 증거가 없습니다.")
        lines.append("")

    # inline formatted blocks (node table, alert table etc.)
    for block in inline_blocks:
        lines.append(block)
        lines.append("")

    lines.extend([
        "### 조치 방법",
        "- 확인된 비정상 리소스가 있으면 상세/Event/metric을 먼저 연결하고, 변경 작업은 승인 흐름으로 분리합니다.",
        "",
        "### 추가 확인",
    ])

    # missing summary
    if miss_events:
        for ev in miss_events:
            ev_type = str(ev.get("evidenceType") or ev.get("name") or "-")
            reason = str(ev.get("missingReason") or ev.get("summary") or "-")
            if is_internal_fallback_diagnostic(ev_type) or is_internal_fallback_diagnostic(reason):
                continue
            lines.append(f"- `{ev_type}` — {truncate_detail(reason, 120)}")
        lines.append("")
    else:
        lines.append("- 추가 확인이 필요한 항목은 상세 상태에서 확인합니다.")
        lines.append("")

    lines.extend([
        "```bash",
        f"oc get events -n {ns} --sort-by=.lastTimestamp | tail -20",
        f"oc get pods -n {ns}",
        "oc get co",
        "```",
        "",
        "### 재발 방지",
        "- 같은 유형의 미완성 답변이 반복되면 모델 응답 상태와 수집 증거 digest를 운영 기록에 남겨 재검증합니다.",
    ])

    return "\n".join(lines)
