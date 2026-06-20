# OLS and Gateway Tool Boundary

This document defines the operational boundary between OpenShift Lightspeed
(OLS) and the KOMSCO AI Gateway.

## Current OLS MCP Scope

The `openshift-lightspeed` deployment runs an `openshift-mcp-server` sidecar.
The current MCP configuration enables these toolsets:

- `core`
- `config`
- `helm`
- `metrics`

The MCP configuration denies these resources:

- `core/v1 Secret`
- all `rbac.authorization.k8s.io/v1` resources

All tools returned by the MCP `tools/list` endpoint are annotated as
`readOnlyHint=true` and `destructiveHint=false`.

## OLS-Owned Capabilities

OLS owns live, user-token-scoped, read-only cluster observation.

| Area | OLS tools |
| --- | --- |
| Alerts and silences | `get_alerts`, `get_silences` |
| Events | `events_list` |
| Metrics | `list_metrics`, `execute_instant_query`, `execute_range_query`, `show_timeseries`, `get_label_names`, `get_label_values`, `get_series` |
| Pods | `pods_list`, `pods_list_in_namespace`, `pods_get`, `pods_log`, `pods_top` |
| Nodes | `nodes_top`, `nodes_stats_summary`, `nodes_log` |
| Resources | `resources_list`, `resources_get`, `namespaces_list`, `projects_list` |
| Helm | `helm_list` |
| Configuration | `configuration_view` |

OLS must use these tools when the user asks about live cluster state such as
alerts, events, failing pods, node pressure, logs, resource inventory, or
Prometheus metrics. It must not invent alert names, pod names, node names, or
resource states that are absent from tool results.

`configuration_view` can expose kubeconfig-shaped material. Even when minified,
its output must be treated as sensitive operational context and should not be
shown verbatim to users.

## Gateway-Owned Capabilities

The KOMSCO AI Gateway is not the primary cluster read model. It owns the control
plane around OLS:

- forwarding the console `UserToken` to OLS through the ConsolePlugin proxy
- request shape validation, size limits, and attachment validation
- sensitive-value redaction before prompts leave the gateway
- SSE normalization, heartbeat events, and long-running loop progress
- converting raw OLS tool telemetry into UI-safe progress events
- policy prompts and deterministic guardrails around dangerous operations
- audit-friendly request metadata and future observability hooks
- image attachment validation and optional gateway-side vision preprocessing
  before forwarding text context to OLS
- future internal document/RAG connectors when explicitly enabled

The gateway should not duplicate OLS read-only cluster tools by default. A
gateway-side cluster query is allowed only when one of these is true:

- OLS does not expose the required data source.
- The gateway must enforce a deterministic safety or compliance preflight.
- The data belongs to an internal KOMSCO system outside OLS MCP scope.
- A future approved write workflow needs an auditable precheck before execution.

## Permission Policy

| Capability | OLS | Gateway |
| --- | --- | --- |
| Live alerts/events/pods/nodes/metrics/logs | Allowed, read-only, UserToken scoped | Do not duplicate by default |
| Secret/RBAC reads | Denied by MCP config | Do not expose or proxy to the model |
| Cluster mutations | Not allowed | Not allowed without a separate approval/RBAC/audit workflow |
| Image attachment validation | Not applicable | Allowed |
| Image attachment forwarding | Only when the OLS deployment accepts image MIME types | Disabled by default; allowed after validation when explicitly enabled |
| Image OCR/vision enrichment | Not required for cluster tool use | Optional gateway-side preprocessing when a vision endpoint is configured |
| Internal documents/RAG | Not currently enabled | Future gateway-owned capability |
| Streaming/progress UX | Emits telemetry | Normalizes and renders telemetry |

## Routing Rules

- Alert or incident questions (`경고`, `Alert`, `장애`, `오류`, `firing`) should
  start with OLS `get_alerts`.
- Event questions should use `events_list`.
- Pod and workload questions should use `pods_list`, `pods_get`, `pods_log`, and
  `pods_top` as needed.
- Node pressure or capacity questions should use `nodes_top` and
  `nodes_stats_summary`; logs require `nodes_log`.
- Metric and graph questions should call `list_metrics` before any PromQL query.
- Requests to modify, delete, restart, scale, patch, or approve resources should
  be answered with analysis and recommended commands only until an explicit
  approved execution workflow exists.

## Prompting Guardrail

The gateway prompt must stay thin. Put the user's question first, keep page
context minimal, and instruct OLS to use OpenShift MCP tools for live state
questions. If tool results are missing, OLS should say that it could not confirm
the live state instead of filling gaps with plausible examples.
