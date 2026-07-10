import re
from collections.abc import Mapping

POD_NAMESPACE_PATTERN_LOOKUP_RE = re.compile(
    r"(?i)((pod|pods|파드).*(네임스페이스|namespace).*(알려|찾아|있는|있나|있냐|있었|포함)|"
    r"(pod|pods|파드).*(네임스페이스|namespace).*(조회|확인)|"
    r"(네임스페이스|namespace).*(pod|pods|파드).*(알려|찾아|있는|있나|있냐|있었|포함|조회|확인))"
)

def parse_markdown_table_cells(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return []
    cells = [cell.strip().replace("\\|", "|") for cell in stripped.strip("|").split("|")]
    if not cells or all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
        return []
    if cells[0].lower() == "namespace":
        return []
    return [cell.strip("`") for cell in cells]


def parse_gateway_pod_evidence_rows(gateway_evidence: str | None) -> list[dict[str, str]]:
    if not gateway_evidence:
        return []

    section = ""
    rows: dict[tuple[str, str, str], dict[str, str]] = {}
    for line in gateway_evidence.splitlines():
        if line.startswith("Top container restart counts:"):
            section = "status_with_finished"
            continue
        if line.startswith("Currently non-healthy or waiting container evidence:"):
            section = "status"
            continue
        if line.startswith("Current Pod list evidence:"):
            section = "pod_list"
            continue
        if line.startswith("Spec evidence for currently non-healthy or waiting containers:"):
            section = "spec"
            continue

        cells = parse_markdown_table_cells(line)
        if not cells:
            continue

        if section == "status_with_finished" and len(cells) >= 10:
            namespace, pod, container = cells[0], cells[1], cells[2]
            key = (namespace, pod, container)
            rows.setdefault(key, {"namespace": namespace, "pod": pod, "container": container}).update(
                {
                    "currentState": cells[3],
                    "podStart": cells[4],
                    "ready": cells[5],
                    "restarts": cells[6],
                    "lastState": cells[7],
                    "lastFinished": cells[8],
                    "owner": cells[9],
                }
            )
            continue

        if section == "status" and len(cells) >= 9:
            namespace, pod, container = cells[0], cells[1], cells[2]
            key = (namespace, pod, container)
            rows.setdefault(key, {"namespace": namespace, "pod": pod, "container": container}).update(
                {
                    "currentState": cells[3],
                    "podStart": cells[4],
                    "ready": cells[5],
                    "restarts": cells[6],
                    "lastState": cells[7],
                    "owner": cells[8],
                }
            )
            continue

        if section == "pod_list" and len(cells) >= 9:
            namespace, pod, container = cells[0], cells[1], cells[2]
            key = (namespace, pod, container)
            rows.setdefault(key, {"namespace": namespace, "pod": pod, "container": container}).update(
                {
                    "currentState": cells[3],
                    "podStart": cells[4],
                    "ready": cells[5],
                    "restarts": cells[6],
                    "lastState": cells[7],
                    "owner": cells[8],
                }
            )
            continue

        if section == "spec" and len(cells) >= 8:
            namespace, pod, container = cells[0], cells[1], cells[2]
            key = (namespace, pod, container)
            rows.setdefault(key, {"namespace": namespace, "pod": pod, "container": container}).update(
                {
                    "image": cells[3],
                    "command": cells[4],
                    "args": cells[5],
                    "labels": cells[6],
                    "ownerChain": cells[7],
                }
            )

    return list(rows.values())


def parse_gateway_current_pod_list_rows(gateway_evidence: str | None) -> tuple[list[dict[str, str]], str, str]:
    if not gateway_evidence:
        return [], "", ""

    section = ""
    namespace_filter = ""
    rows_shown = ""
    rows: list[dict[str, str]] = []
    for line in gateway_evidence.splitlines():
        if line.startswith("Current Pod list evidence:"):
            section = "pod_list"
            continue
        if section == "pod_list" and line.startswith("Namespace filter:"):
            namespace_filter = line.split(":", 1)[1].strip().strip("`")
            continue
        if section == "pod_list" and line.startswith("Rows shown:"):
            rows_shown = line.split(":", 1)[1].strip()
            continue
        if section == "pod_list" and line.startswith("Spec evidence for currently non-healthy or waiting containers:"):
            section = ""
            continue

        cells = parse_markdown_table_cells(line)
        if section != "pod_list" or len(cells) < 9:
            continue

        rows.append(
            {
                "namespace": cells[0],
                "pod": cells[1],
                "container": cells[2],
                "currentState": cells[3],
                "podStart": cells[4],
                "ready": cells[5],
                "restarts": cells[6],
                "lastState": cells[7],
                "owner": cells[8],
            }
        )

    return rows, namespace_filter, rows_shown


def kubernetes_name_terms(message: str) -> list[str]:
    ignored = {
        "namespace",
        "deployment",
        "statefulset",
        "daemonset",
        "crashloopbackoff",
        "openshift",
    }
    terms: list[str] = []
    for match in re.finditer(r"\b[a-z0-9](?:[-a-z0-9]{2,61}[a-z0-9])?\b", message.lower()):
        term = match.group(0)
        if len(term) < 4 or term in ignored:
            continue
        if term not in terms:
            terms.append(term)
    return terms


def score_gateway_pod_row(row: Mapping[str, str], message: str) -> int:
    message_lower = message.lower()
    haystack = " ".join(str(row.get(key, "")).lower() for key in row)
    score = 0
    if row.get("namespace", "").lower() in message_lower:
        score += 3
    if row.get("pod", "").lower() in message_lower:
        score += 30
    if row.get("container", "").lower() in message_lower:
        score += 5
    for term in kubernetes_name_terms(message):
        if term and term in haystack:
            score += 10
    if "crash" in message_lower and "crashloopbackoff" in haystack:
        score += 5
    if "waiting:" in row.get("currentState", "").lower() or "crashloopbackoff" in haystack:
        score += 2
    return score


def choose_gateway_pod_row(rows: list[dict[str, str]], message: str) -> dict[str, str] | None:
    if not rows:
        return None
    scored = sorted(
        ((score_gateway_pod_row(row, message), index, row) for index, row in enumerate(rows)),
        key=lambda item: (item[0], -item[1]),
        reverse=True,
    )
    if scored[0][0] > 0:
        return scored[0][2]
    for row in rows:
        if "crashloopbackoff" in " ".join(row.values()).lower() or "waiting:" in row.get("currentState", "").lower():
            return row
    return rows[0]


def deployment_from_owner_chain(owner_chain: str) -> str | None:
    match = re.search(r"Deployment/([A-Za-z0-9._-]+)", owner_chain)
    return match.group(1) if match else None


def app_label_from_labels(labels: str) -> str | None:
    match = re.search(r"(?:^|,\s*)app=([^,\s]+)", labels)
    return match.group(1) if match else None


def looks_non_production_context(row: Mapping[str, str]) -> bool:
    text = " ".join(
        [
            row.get("pod", ""),
            row.get("labels", ""),
            row.get("ownerChain", ""),
        ]
    ).lower()
    return bool(re.search(r"\b(test|e2e|scenario|sandbox|demo|sample)\b", text))


def command_suggests_immediate_exit(command: str, args: str) -> bool:
    text = f"{command} {args}".lower()
    return any(marker in text for marker in ["systemexit", "raise ", "exit ", "exit(", "false", "sys.exit"])


CRASHLOOPBACKOFF_PLAIN_DEFINITION = (
    "CrashLoopBackOff는 컨테이너가 시작된 뒤 곧바로 종료되고, Kubernetes가 재시작을 반복하다가 "
    "잠시 대기 시간을 늘리는 상태입니다."
)
CRASHLOOPBACKOFF_FIRST_SENTENCE_RULE = (
    '첫 문장에 "컨테이너가 시작 후 곧바로 종료되고 Kubernetes가 재시작을 반복하다가 대기 시간을 늘리는 상태"를 '
    "설명한다."
)


def message_mentions_crashloop(message: str) -> bool:
    return bool(re.search(r"crash\s*loop\s*back\s*off|crashloopbackoff|크래시\s*루프\s*백\s*오프", message, re.IGNORECASE))


def ready_summary_is_full(ready: str) -> bool:
    match = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", ready)
    return bool(match and match.group(1) == match.group(2))


def parse_restart_count(value: str) -> int:
    match = re.search(r"\d+", str(value or ""))
    return int(match.group(0)) if match else 0


def pod_row_has_current_failure(row: Mapping[str, str]) -> bool:
    current = str(row.get("currentState") or "")
    ready = str(row.get("ready") or "")
    return bool(
        re.search(
            r"(?i)(crashloopbackoff|imagepullbackoff|errimagepull|pending|failed|error|waiting:)",
            current,
        )
        or (ready and not ready_summary_is_full(ready) and current.lower().startswith("running"))
    )


def pod_row_has_error_exit(row: Mapping[str, str]) -> bool:
    last_state = str(row.get("lastState") or "")
    return bool(re.search(r"(?i)(error|oomkilled|exit\s*code\s*(?!0\b)[1-9]|/[1-9][0-9]*)", last_state))


def pod_row_has_completed_restart_loop(row: Mapping[str, str]) -> bool:
    current = str(row.get("currentState") or "")
    last_state = str(row.get("lastState") or "")
    return (
        parse_restart_count(str(row.get("restarts") or "")) > 0
        and re.search(r"(?i)\brunning\b", current) is not None
        and re.search(r"(?i)completed\s*/\s*0", last_state) is not None
    )


def pod_row_priority(row: Mapping[str, str]) -> tuple[int, str, str]:
    if pod_row_has_current_failure(row):
        return 1, "높음", "현재 비정상 상태 또는 Ready 아님"
    if pod_row_has_error_exit(row):
        return 2, "높음", "최근 Error 종료 이력"
    if pod_row_has_completed_restart_loop(row):
        return 3, "중간", "Completed/0 반복 재시작 이력"
    if parse_restart_count(str(row.get("restarts") or "")) > 0:
        return 4, "중간", "재시작 이력 확인 필요"
    return 5, "낮음", "현재 목록 기준 즉시 장애 신호 낮음"


def pod_inventory_message_requests_restart_history(message: str) -> bool:
    return bool(
        re.search(
            r"(?i)(재시작|리스타트|restart|restarts|restart\s*count|"
            r"누적|횟수|많은|높은|빈번|반복|completed\s*/\s*0|이력)",
            message,
        )
    )


def pod_inventory_message_requests_problem_scope(message: str) -> bool:
    return bool(
        re.search(
            r"(?i)(에러|error|failed|crashloop|imagepull|backoff|pending|"
            r"비정상|문제|이상|원인)",
            message,
        )
    )


def pod_inventory_restart_observation_rows(rows: list[Mapping[str, str]]) -> list[Mapping[str, str]]:
    return [
        row
        for row in rows
        if not (pod_row_has_current_failure(row) or pod_row_has_error_exit(row))
        and (
            pod_row_has_completed_restart_loop(row)
            or parse_restart_count(str(row.get("restarts") or "")) > 0
        )
    ]


def pod_inventory_selected_rows(message: str, rows: list[Mapping[str, str]]) -> list[Mapping[str, str]]:
    strict_rows = [
        row
        for row in rows
        if pod_row_has_current_failure(row) or pod_row_has_error_exit(row)
    ]
    restart_rows = pod_inventory_restart_observation_rows(rows)
    include_restart_history = pod_inventory_message_requests_restart_history(message)
    problem_scope = pod_inventory_message_requests_problem_scope(message)

    if problem_scope:
        selected = strict_rows + (restart_rows if include_restart_history else [])
    elif include_restart_history:
        selected = strict_rows + restart_rows
    else:
        selected = list(rows)

    return sorted(
        selected,
        key=lambda row: (pod_row_priority(row)[0], -parse_restart_count(str(row.get("restarts") or ""))),
    )


def is_pod_namespace_pattern_lookup_request(message: str) -> bool:
    return bool(POD_NAMESPACE_PATTERN_LOOKUP_RE.search(message))


def pod_namespace_lookup_pattern(message: str) -> str:
    quoted_match = re.search(r"[`'\"](?P<pattern>[A-Za-z0-9._-]{2,})[`'\"]", message)
    if quoted_match:
        return quoted_match.group("pattern").lower()
    if re.search(r"(?i)(테스트|test)", message):
        return "test"
    before_contains = re.search(
        r"(?i)(?P<pattern>[A-Za-z0-9._-]{2,})\s*(?:가|이)?\s*(?:포함|들어)",
        message,
    )
    if before_contains:
        return before_contains.group("pattern").lower()
    after_contains = re.search(
        r"(?i)(?:포함|들어).{0,12}(?P<pattern>[A-Za-z0-9._-]{2,})",
        message,
    )
    if after_contains:
        return after_contains.group("pattern").lower()
    return ""
