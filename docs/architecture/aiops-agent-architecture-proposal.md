# OCP Operations Copilot Architecture Proposal

## Purpose

This proposal defines the target architecture for an OpenShift-native AIOps
assistant. The system should support live cluster investigation, root-cause
analysis, host-level diagnostics, and approval-gated remediation without
making SSH, arbitrary shell execution, or privileged node access the default
control path.

## Status

```yaml
status: Approved for Phase 0-1 Implementation
decisionDate: 2026-06-20
mvpScope:
  - Phase 0: Security Envelope
  - Phase 1: Read-only Evidence Platform
phase1Gate: Phase 0 exit criteria must pass before Phase 1 production deployment
targetOpenShiftVersions:
  - "4.21"
reviewRequiredBefore:
  - Phase 2: Host Diagnostics
  - Phase 3: Approval-gated Actions
nonGoals:
  - autonomous remediation
  - arbitrary command execution
  - multi-cluster operation
  - unrestricted host access
```

The most important operating principles are:

- The Agent Orchestrator does not have cluster write permission.
- Raw user tokens are confined to the Gateway and Tool Broker credential
  boundary and are never exposed to planning, model, host-agent, or persistent
  storage components.
- All tool calls go through deterministic validation and policy checks.
- Mutations are executed only by a separate Action Executor identity.
- Host-level diagnostics are collector-specific and validated against SCC,
  SELinux, hostPath, hostPID, and runtime socket requirements.
- Approved actions are revalidated immediately before execution.

## Target Architecture

```text
OpenShift Console Dynamic Plugin
  |
  v
Gateway / BFF
  - UserToken termination
  - session, rate limit, SSE stream
  - attachment validation
  - redaction
  |
  +------------------------------------+
  |                                    |
  v                                    v
Agent Orchestrator              Approval API / Internal Execution Coordinator
  - no cluster write              - approver credential context
  - plan and hypothesis           - product authorization
  - evidence synthesis            - action authorization revalidation
  - ActionProposal                - one-time ExecutionGrant
  | \
  |  +--> Model Gateway / OLS Adapter
  |       - redacted prompt only
  |       - provider policy
  |       - schema validation
  |                                    |
  v                                    v
Tool Broker                         Action Executor
  - schema validation                 - separate ServiceAccount
  - authz enforcement                 - accepts ExecutionGrant only
  - quotas and timeouts               - typed actions only
  - output normalization              - precondition and dry-run
  - authorization attestation         - post-verification
  |
  +--> Kubernetes/OpenShift API Adapter
  +--> Thanos / Metrics Adapter
  +--> Alertmanager Adapter
  +--> Loki / Log Adapter
  +--> Event Adapter
  +--> Runbook / RAG Adapter
  +--> Host Diagnostics Controller
  +--> Evidence Service / API
           ^
           |
       outbound mTLS
           |
       Node DaemonSet Agents

Policy Engine
  - enforced independently by Tool Broker and Action Executor
  - contextual risk
  - namespace and target rules
  - policy bundle version

Shared
  - Incident / Evidence Store
  - Structured Audit Sink
  - OpenTelemetry traces and metrics
  - Service-to-service workload identity
```

The product-level shape is:

```text
OCP Operations Copilot
  -> Gateway
    -> Agent Orchestrator
      -> ActionProposal
      -> Tool Broker for evidence only
      -> Model Gateway / OLS Adapter for redacted model calls only
    -> Approval API / Internal Execution Coordinator
      -> SealedActionPlan
      -> ApprovalDecision
      -> ExecutionGrant
      -> Action Executor
```

## Design Principles

- Keep the primary AIOps services inside OpenShift, not on install, bastion, or
  worker nodes.
- Use OpenShift RBAC, ServiceAccount identity, audit logs, and namespace
  boundaries as the default control model.
- Separate planning from execution. The Agent Orchestrator proposes evidence
  requests and actions; it does not directly execute cluster mutations.
- The Agent Orchestrator and Tool Broker cannot invoke the Action Executor.
  Only the Approval API or a dedicated Execution Coordinator can issue an
  execution request, and every request must carry a valid one-time
  ExecutionGrant bound to an immutable plan digest.
- Separate user-scoped access from product-scoped diagnostics. Never silently
  elevate from a user token to a service account when a user lacks permission.
- Treat logs, events, runbooks, and retrieved documents as untrusted input.
- Use evidence and decision traces, not opaque internal reasoning, as the
  operator-facing explanation model.
- Store every tool call as structured audit data: actor, effective identity,
  session, tool, target, normalized input, result, risk, policy decision,
  approval state, evidence references, and timestamp.
- Avoid arbitrary shell execution in normal product flows.
- Prefer typed Kubernetes/OpenShift API adapters. Keep `oc` fallback disabled
  by default and restricted to explicit, typed wrappers if it is ever enabled.
- Make host diagnostics read-only by default and collector-specific by design.
- Require target, impact, dry-run or diff, rollback plan, approval, and
  execution-time revalidation before any mutation.

## Components

### OCP Operations Copilot

The Copilot is the user-facing product surface. In the current workspace this
maps to the OpenShift Console dynamic plugin and assistant overlay.

Responsibilities:

- Chat and incident investigation UI.
- Streaming progress display.
- Evidence, RCA, and action-plan views.
- Approval screens for risky operations.
- Attachment and page-context input from the console.
- Clear display of whether each answer is confirmed from live data or inferred
  from available evidence.
- Separate display of user-permission-scoped evidence and platform-diagnostic
  evidence.

The Copilot does not directly execute cluster operations. It calls the Gateway
and renders normalized stream events.

### Gateway / BFF

The Gateway is the boundary between the console UI and backend agent services.

Responsibilities:

- Terminate the console `UserToken`.
- Keep user tokens in memory only.
- Validate request shape, image attachments, and size limits.
- Redact sensitive values before prompt, audit, trace, or log storage.
- Normalize backend streams into UI-safe SSE progress events.
- Manage session, incident, and request identifiers.
- Apply rate limits and request timeout boundaries.
- Route requests to the Agent Orchestrator, Tool Broker, or Approval API.

The Gateway should remain thin. It owns API safety, identity termination, and
streaming UX, not the core reasoning loop.

### Credential Delegation Contract

The Agent Orchestrator must not receive raw user tokens. The Gateway and Tool
Broker need an explicit credential delegation contract so the Broker can apply
the correct user token to later Agent-requested tool calls.

```text
Console -> Gateway
- Gateway receives raw UserToken from the ConsolePlugin proxy.
- Gateway verifies the user session and cluster context.

Gateway -> Tool Broker
- Gateway registers the token over an internal mTLS channel.
- Broker stores the token in memory only with a short TTL.
- Broker returns an authContextId.

Gateway -> Agent Orchestrator
- Gateway sends authContextId plus verified identity metadata.
- Gateway does not send the raw token.

Agent Orchestrator -> Tool Broker
- Agent sends structured ToolCall requests with authContextId.
- Broker revalidates session, cluster, actor, expiry, policy, and tool scope.

Approver UI -> Gateway
- Gateway receives the approver's UserToken during approval.
- Gateway verifies the approver session and cluster context.

Gateway -> Tool Broker
- Gateway registers the approver token separately.
- Broker returns approverAuthContextId.

Gateway -> Approval API
- Gateway sends sealedPlanId, expectedPlanDigest, approver identity metadata, and
  approverAuthContextId.
- Gateway does not send the raw approver token.
- Approval API accepts approval only when expectedPlanDigest matches the stored
  SealedActionPlan digest.

Execution-time authorization
- Approval API calls Tool Broker `revalidate_action_authorization`.
- Broker performs SSAR with the approver token.
- Broker returns a short-TTL signed AuthorizationAttestation.
- Approval API, through its internal Execution Coordinator module, issues a
  one-time ExecutionGrant.
```

Rules:

- `authContextId` is bound to one session and one cluster.
- `authContextId` cannot be reused across sessions.
- `approverAuthContextId` is distinct from the requester's `authContextId`.
- Broker obtains API-server-observed subject information with
  SelfSubjectReview and binds it to the credential context.
- Authorization decisions use API-server-observed subject UID, username, and
  group digest, not client-supplied strings.
- Token expiry returns `reauth_required`.
- Token expiry must not trigger ServiceAccount fallback.
- User name and groups supplied by the client are never trusted.
- `authContextId` and `approverAuthContextId` are credential handles and must
  not be written to logs, traces, prompts, audit payloads, model input, DB
  rows, or object storage.
- MVP binds each credential context to one Broker instance.
- An internal router must route by Broker instance ID or consistent hash.
- If the owning Broker pod disappears, the context is discarded and
  `reauth_required` is returned.
- If an Agent or Broker restart removes an in-memory credential context, every
  active workflow step that depends on that context transitions to
  `reauth_required` before any further tool call, approval revalidation, or
  evidence read.
- Token replication between Broker pods is out of scope for MVP.

Subject shape:

```yaml
subject:
  username: user@example.com
  uid: stable-user-uid
  groupsDigest: sha256:...
  authenticatedByCluster: cluster-id
```

Credential-dependent workflow state machine:

```text
active
  -> waiting_for_approval
  -> reauth_required
  -> resumed_after_reauth
  -> completed | failed | cancelled
```

Credential loss transitions:

- `active -> reauth_required` when an evidence tool call requires a missing
  requester `authContextId`
- `waiting_for_approval -> reauth_required` when approval or execution-time
  authorization revalidation requires a missing `approverAuthContextId`
- `reauth_required` blocks further Tool Broker calls, evidence reads,
  PlanValidationGrant issuance, and ExecutionGrant issuance
- after successful reauthentication, the workflow revalidates stale evidence,
  policy, target state, and plan digest before resuming

### Agent Orchestrator

The Agent Orchestrator is the core Rust planning service. It creates
investigation plans, asks for evidence, synthesizes hypotheses, and proposes
actions.

Responsibilities:

- Classify user intent.
- Build an investigation plan.
- Request evidence from the Tool Broker.
- Call the Model Gateway / OLS Adapter for OpenShift knowledge and natural
  language synthesis with redacted inputs only.
- Generate cause candidates with evidence references.
- Produce ActionProposal objects for deterministic validation.
- Explain uncertainty, missing data, and confidence.

Non-responsibilities:

- No Kubernetes write permission.
- No user token storage.
- No direct call to host DaemonSet agents.
- No arbitrary shell execution.
- No direct execution of approved actions.

### Tool Broker

The Tool Broker is the deterministic boundary between the Agent Orchestrator
and operational data sources.

Responsibilities:

- Validate tool schemas.
- Enforce authorization and identity mode.
- Apply output size limits, pagination limits, timeouts, and rate limits.
- Normalize tool outputs.
- Prevent secrets, tokens, and sensitive headers from entering model context.
- Route calls to typed adapters.
- Record tool-call audit events.

The Tool Broker is the only component that should use the user's token for
OpenShift or observability API calls. The token must not be passed to the Agent
Orchestrator, Model Gateway / OLS Adapter, Host Diagnostics Agent, traces,
logs, prompts, or persistent storage.

Production deployment requirements:

- separate Deployment
- separate ServiceAccount
- internal ClusterIP Service only
- default-deny NetworkPolicy
- Gateway can register and refresh credential contexts
- Gateway can request EvidenceAccessGrant
- Agent Orchestrator can call read-only tool endpoints
- Approval API can call authorization revalidation and observational
  verification endpoints only
- Action Executor direct access is forbidden
- user-token credential memory isolated from Agent pods

Sidecar deployment is allowed only for local development and must not be used
as the production isolation model.

### Service-to-Service Workload Identity

NetworkPolicy limits traffic paths, but it does not prove the caller's
workload identity. Phase 1 must include authenticated service-to-service
identity for control-plane calls.

Recommended control:

- client-authenticated mTLS between control-plane services
- certificate SAN bound to namespace and ServiceAccount
- endpoint-level caller allow-list in each receiving service
- key and certificate rotation policy

Acceptable alternative:

- audience-bound projected ServiceAccount tokens
- receiving service validates tokens with TokenReview
- endpoint-level checks for audience, namespace, and ServiceAccount

Control-plane call matrix:

| Caller | Target | Allowed endpoint |
| --- | --- | --- |
| Gateway | Tool Broker | credential register, refresh, revoke, evidence access grant |
| Agent Orchestrator | Tool Broker | evidence tools only |
| Agent Orchestrator | Model Gateway / OLS Adapter | redacted prompt, provider policy, schema validation |
| Approval API | Tool Broker | identity and authorization revalidation |
| Approval API, including internal Execution Coordinator module | Action Executor | dry-run with PlanValidationGrant, execute with ExecutionGrant |
| Approval API, including internal Execution Coordinator module | Tool Broker | observational verification tools only |
| Tool Broker | Evidence Service | redacted evidence ingest, user and product-scoped evidence reads |
| Gateway | Evidence Service | UI download and preview with EvidenceAccessGrant |
| Diagnostics Controller | Evidence Service | evidence write |
| Tool Broker | Host Diagnostics Controller | DiagnosticRequestGrant-backed host diagnostics request |
| Agent Orchestrator | Evidence Service | denied |
| Model Gateway / OLS Adapter | Evidence Service | denied |
| Agent Orchestrator | Action Executor | denied |
| Tool Broker | Action Executor | denied |
| Gateway | Action Executor | denied |

MVP topology decision:

- Execution Coordinator is an internal module of the Approval API for Phase 3
  MVP.
- The Approval API ServiceAccount is the only service identity allowed to call
  Action Executor mutation endpoints in MVP.
- If Execution Coordinator becomes a separate workload later, it needs its own
  ServiceAccount, mTLS identity, endpoint allow-list entry, and call-matrix
  update before production use.

### Policy Engine

The Policy Engine evaluates contextual risk and authorization.

Inputs:

- Actor and effective identity.
- Identity mode: user token, read-only service account, action executor
  service account, or break-glass identity.
- Namespace, resource type, resource ownership, and cluster role.
- Replica count, PDB, workload kind, stateful/data sensitivity, and operator
  ownership.
- Policy bundle version and hash.
- Time, environment, maintenance window, and approval scope.

Outputs:

- allow, deny, or require approval.
- risk level.
- required preconditions.
- required post-verification.
- required evidence.
- policy decision ID.

The first implementation can use a versioned allow-list policy bundle delivered
through GitOps. A ConfigMap can be the delivery mechanism, but it is not a
security boundary.

Policy evaluation can use a shared library, but enforcement must happen
independently inside the Tool Broker and Action Executor. A policy decision
produced only by the Agent Orchestrator is never authoritative.

### Action Registry

The Action Registry is a versioned and signed bundle. It defines typed actions
and must generate both the authorization check and the actual Kubernetes API
request. This prevents drift where SSAR checks one resource or verb while
execution uses another.

Registry and policy bundles must include supply-chain metadata:

- bundle signature and signer identity
- monotonically increasing bundle version and anti-rollback check
- activation time
- previous-version verification grace period
- emergency revocation marker and distribution path

Each versioned registry entry must define:

```yaml
toolName: evict_one_unhealthy_controller_owned_pod
toolVersion: v1

authorization:
  verb: create
  apiGroup: ""
  resource: pods
  subresource: eviction

request:
  method: POST
  pathTemplate: /api/v1/namespaces/{namespace}/pods/{name}/eviction
```

The Tool Broker, Approval API, Policy Engine, and Action Executor must all use
the same registry version. Mismatch in action registry version marks the plan
as stale and requires reapproval.

Ownership rules:

- Approval API or its internal Execution Coordinator module uses the registry
  to build the SealedActionPlan.
- Action Executor uses the registry to build the execution request.
- Tool Broker uses only the registry authorization descriptor for SSAR.
- Tool Broker does not author action payloads or normalizedParameters.

### Approval API

The Approval API manages human approval and separation of duties.

Responsibilities:

- Verify product authorization: the approver has the product role required to
  approve the SealedActionPlan.
- Verify target authorization through the Tool Broker: the approver can perform
  the exact Kubernetes action on the exact target.
- Store approval scope, expiry, and target.
- Bind approval to a specific SealedActionPlan, policy decision, tool version, and
  expected current state.
- Reject stale or broadened execution attempts.
- Issue a one-time ExecutionGrant after authorization revalidation.
- Provide an audit trail for approval decisions.

Approval requires both product authorization and target authorization. SSAR can
prove target Kubernetes permission, but it does not prove that the user has the
product role to approve AIOps remediation. Medium-risk and high-risk actions
should require a dedicated `aiops-approver` product role.

### Action Executor

The Action Executor is a separate Rust service or worker that performs approved
mutations. It uses a separate ServiceAccount and a small typed action surface.

Responsibilities:

- Accept dry-run requests only with a valid PlanValidationGrant issued by the
  Approval API or its internal Execution Coordinator module.
- Accept mutation requests only with a valid one-time ExecutionGrant issued by
  the Approval API or its internal Execution Coordinator module.
- Validate ExecutionGrant signature, audience, expiry, target, plan digest, and
  embedded authorization attestation digest.
- Revalidate policy, target identity, and approval expiry.
- Re-run dry-run or server-side validation immediately before execution.
- Verify typed preconditions for the selected action.
- Execute only typed allow-listed actions.
- Verify hard postconditions through resource GET/watch, generation, replica,
  readiness, and ReplicaSet state.
- Record structured audit events.

Action Executor ingress:

- allowed: Approval API, including its internal Execution Coordinator module,
  only, for PlanValidationGrant dry-run and ExecutionGrant mutation endpoints
- denied: Agent Orchestrator, Tool Broker, Gateway, Node Agents

The Agent Orchestrator should never receive mutation RBAC. Adding mutation
permission to `aiops-agent` later would collapse the main trust boundary.

MVP mutation identity decision:

- Kubernetes mutations are performed by the `aiops-action-executor`
  ServiceAccount.
- The approver's authorization is checked at approval time and again
  immediately before execution. The Approval API asks the Tool Broker to run
  SelfSubjectAccessReview with the approver credential context for the exact
  verb, resource, subresource, namespace, and name.
- The Tool Broker returns a signed AuthorizationAttestation; the Approval API
  or its internal Execution Coordinator module converts it into a one-time
  ExecutionGrant.
- User tokens are not stored by the Action Executor.
- If the approver token is expired or cannot be revalidated, execution is
  rejected and reauthentication or reapproval is required.
- Kubernetes impersonation is out of scope for MVP.
- Audit records must store `actor` and `effective_identity` separately.

Separation-of-duties rules:

- Approval and execution should happen within a short expiry window.
- Medium-risk and higher actions require `requester != approver`.
- Break-glass actions require two-person approval.
- Scheduled execution is treated as automation policy, not as a user-token
  approval extension.

Initial action candidates:

```text
rollout_restart_deployment
set_replicas_within_bounds
evict_one_unhealthy_controller_owned_pod
```

Deferred or disabled actions:

```text
patch_preapproved_field
run_predefined_runbook
generic_patch_resource
apply_arbitrary_manifest
delete_arbitrary_resource
run_command
```

`delete_pod` should not be a default action. Prefer the Eviction API for
controller-owned unhealthy pods so disruption controls can be respected.

### Host Diagnostics Controller

The Host Diagnostics Controller coordinates node-local diagnostics. It should
combine a Kubernetes request object with a controlled transport channel.

Recommended pattern:

```text
DiagnosticRequest CRD
  - requester
  - target node
  - collector
  - time range
  - expiry
  - risk level
  - approval reference, when needed
  - DiagnosticRequestGrant reference
  - status and result reference

Host Diagnostics Controller
  - request validation
  - node agent selection
  - timeout, retry, and cancel
  - result storage
  - status updates

Node Agent
  - outbound mTLS connection to the controller
  - executes only collectors allowed for its node
  - returns structured evidence
```

Store only request status, summary, result reference, digest, and retention
metadata in the CRD. Store large logs or evidence in Loki or object storage.
The DiagnosticRequest CRD stores only `grantId` and grant digest references,
not the bearer DiagnosticRequestGrant object.

Avoid exposing per-node DaemonSet pods as directly callable HTTP services.
Outbound mTLS from node agents to the controller reduces service exposure,
arbitrary pod invocation, and node routing risks.

DiagnosticRequest trust rules:

- Normal users cannot directly create DiagnosticRequest objects.
- Only the Host Diagnostics Controller can create DiagnosticRequest CRD
  objects.
- Tool Broker has no DiagnosticRequest CRD create permission.
- Tool Broker can only call the Host Diagnostics Controller request API.
- The Kubernetes API requester for DiagnosticRequest creation is the Host
  Diagnostics Controller ServiceAccount.
- End-user requester identity is carried by Broker-signed
  DiagnosticRequestGrant or requester authorization attestation.
- Tool Broker sends the bearer DiagnosticRequestGrant only to the Host
  Diagnostics Controller API over authenticated service-to-service transport.
- The Controller validates the bearer grant, then records only grant ID and
  digest in the DiagnosticRequest CRD.
- `requester` is derived from the signed grant or attestation, not trusted from
  user-supplied CRD spec fields or the CRD creator ServiceAccount.
- `status` is updated only by the Controller.
- Result references are exposed according to requester RBAC and evidence
  classification.
- Node Agent certificate identity is bound to Node UID.
- The Controller rejects results submitted by an agent identity that is not
  bound to the target node.
- Node Agent certificate issuance, rotation, and revocation are part of the
  host diagnostics control plane.

Minimum DiagnosticRequestGrant claims:

```yaml
diagnosticRequestGrant:
  schemaVersion: v1
  issuer: aiops-tool-broker
  audience: aiops-host-diagnostics-controller
  grantId: diag-grant-123
  issuedAt: "2026-06-20T00:04:00Z"
  notBefore: "2026-06-20T00:04:00Z"
  expiresAt: "2026-06-20T00:05:00Z"
  clusterId: cluster-id
  requestDigest: sha256:...

  actor:
    username: user@example.com
    uid: stable-user-uid
    groupsDigest: sha256:...
  effectiveIdentity:
    serviceAccount: aiops-host-diagnostics
    namespace: aiops-system
  requester:
    username: user@example.com
    uid: stable-user-uid
    groupsDigest: sha256:...
  targetNode:
    name: worker-1.example.com
    uid: node-uid
  collector: kubelet_logs
  collectorVersion: v1
  collectorProfile: elevated-readonly
  timeRange:
    since: "2026-06-19T23:30:00Z"
    until: "2026-06-20T00:00:00Z"
  limits:
    deadline: 30s
    maxBytes: 10485760
    maxLines: 50000
  evidencePolicy:
    classification: restricted
    redactionPolicyDigest: sha256:...
    rawStorageAllowed: false
  authorization:
    decision: allowed
    identityMode: user-token
```

Minimum DiagnosticRequestCandidate:

```yaml
diagnosticRequestCandidate:
  schemaVersion: v1
  clusterId: cluster-id

  requester:
    username: user@example.com
    uid: stable-user-uid
    groupsDigest: sha256:...

  targetNode:
    name: worker-1.example.com
    uid: node-uid
  collector: kubelet_logs
  collectorVersion: v1
  collectorProfile: elevated-readonly
  timeRange:
    since: "2026-06-19T23:30:00Z"
    until: "2026-06-20T00:00:00Z"
  limits:
    deadline: 30s
    maxBytes: 10485760
    maxLines: 50000
  evidencePolicy:
    classification: restricted
    redactionPolicyDigest: sha256:...
    rawStorageAllowed: false
  policy:
    policyDecisionId: pd-diag-123
    policyBundleHash: sha256:...
    policyInputDigest: sha256:...
    policyDecisionDigest: sha256:...
```

Diagnostic request digest schema:

```yaml
diagnosticRequestDigest:
  includedFields:
    - /schemaVersion
    - /clusterId
    - /requester
    - /targetNode
    - /collector
    - /collectorVersion
    - /collectorProfile
    - /timeRange
    - /limits
    - /evidencePolicy
    - /policy
```

Host Diagnostics Controller checks before CRD creation:

```text
- validate DiagnosticRequestGrant signature, audience, expiry, and clusterId
- canonicalize DiagnosticRequestCandidate with RFC 8785 JCS
- recompute diagnosticRequestDigest from the allow-list projection
- compare recomputed digest with DiagnosticRequestGrant.requestDigest
- compare policy decision digest and policy bundle hash with the candidate
- create DiagnosticRequest CRD only after all checks pass
```

DiagnosticRequestGrant replay controls:

- `grantId` is recorded in a TTL replay cache for every collector.
- Expensive or sensitive collectors use one-time claim semantics.
- Cross-cluster replay is rejected by `clusterId`.
- Node name reuse is rejected by matching Node UID.

### Host Diagnostics DaemonSet Agent

The Host Diagnostics Agent is a Rust-based DaemonSet that runs one pod per
node. It is a node-local evidence collector, not a remote execution service.

Collector planning must be based on proven OpenShift permissions, not only on
desired feature categories.

| Collector | Preferred source | Expected profile |
| --- | --- | --- |
| CPU, memory, filesystem usage | Thanos / node-exporter | Agent API query |
| Pod and Node state | Kubernetes API | Agent API query |
| Basic `/proc` and `/sys` summary | limited read-only hostPath | Level 1 candidate |
| systemd journal, kubelet, CRI-O logs | hostPath plus SELinux/SCC validation | likely Level 2 |
| CRI-O socket status | runtime socket | Level 2 |
| host process details | hostPID | Level 2 |
| `nsenter`, `systemctl`, host modification | privileged Job | Level 3 |

Capability levels:

```text
Level 1: Passive Host Diagnostics
- default deployment profile if validated
- read-only hostPath only for specific collectors
- no privileged container
- no hostPID or hostNetwork by default
- no mutating operation

Level 2: Elevated Diagnostics
- optional profile
- hostPID or runtime socket access only when justified
- read-only runtime inspection
- separate ServiceAccount and SCC

Level 3: Break-glass Remediation
- disabled by default
- privileged access only through explicit approval
- short-lived Job preferred over always-on privileged DaemonSet
- fixed image digest and entrypoint
- no arbitrary command input
- node-specific scheduling
- egress restriction
- activeDeadlineSeconds and TTL cleanup
- separate audit channel
```

Do not duplicate data already available through OpenShift monitoring unless
the DaemonSet can add host-local evidence that the metrics path cannot provide.

A runtime socket is treated as an active privileged API capability, not as a
read-only file. A read-only hostPath mount does not guarantee read-only RPC
behavior.

Runtime socket controls:

- CRI-O socket collectors are disabled by default.
- They use a separate ServiceAccount and SCC profile.
- Prefer a constrained local proxy over direct socket access.
- Allowed RPC methods must be explicitly listed.
- Mutation, exec, attach, and remove-style RPCs are blocked.
- Mounting `/`, `/etc/kubernetes`, `/var/lib/kubelet/pods`, or a socket parent
  directory is forbidden.

### Model Gateway / OLS Adapter

The Model Gateway / OLS Adapter is separate from the Tool Broker. It should be
used for OpenShift knowledge, runbook explanation, natural language synthesis,
and reasoning assistance, but it is not an operational-data or credential
boundary.

Responsibilities:

- Explain OpenShift concepts and runbooks.
- Summarize collected evidence.
- Suggest likely causes.
- Produce operator-readable remediation plans.
- Enforce provider allow-list, retention policy, and prompt size limits.
- Validate model output against a schema before returning it to the Agent
  Orchestrator.

Restrictions:

- Use supported REST APIs only.
- Do not use internal UI endpoints as programmatic integration points.
- Do not treat the model as the authority for live cluster state.
- Do not pass user tokens, authorization headers, secrets, or raw sensitive
  logs to the model.
- Treat logs, runbooks, and retrieved documents as untrusted data.
- Validate model output against a schema before downstream use.
- Require evidence references for RCA claims.
- Never execute a command or URL produced only by the model.
- Record provider-specific data retention and telemetry rules.

## Identity and Permission Model

Use separate identities for separate risk profiles.

```text
aiops-gateway
- receives console calls
- terminates user token
- forwards identity metadata, not raw tokens, to planning components

aiops-agent-orchestrator
- no mutation permission
- no user token access
- plan, hypothesis, evidence synthesis only

aiops-tool-broker
- can use user token for user-scoped reads
- can use read-only service account for product-scoped diagnostics
- enforces no silent privilege escalation

aiops-action-executor
- separate mutation ServiceAccount
- typed actions only
- no arbitrary shell

aiops-host-diagnostics
- host-level read-only collectors
- collector-specific SCC validation

aiops-host-breakglass
- disabled by default
- elevated permission only after explicit approval
```

Execution identity guidance:

| Data or action | Recommended execution identity |
| --- | --- |
| User-visible Pods, Events, Logs | user token |
| User-scoped metrics | user token where supported |
| Product-level cluster diagnostics | read-only ServiceAccount |
| Host diagnostics request | Host Diagnostics SA plus requester authorization check |
| Normal mutation | Action Executor ServiceAccount plus approver SSAR revalidation |
| Standard runbook automation | limited Action Executor ServiceAccount |

If the user lacks permission, the system should say so. It must not silently
substitute a broader service account and present the result as user-scoped
evidence.

Product authorization authority:

- MVP product permissions are represented in OpenShift RBAC, not a separate
  internal IAM system.
- Product roles such as `aiops-approver`, `aiops-evidence-viewer`, and
  `aiops-verification` map to Kubernetes `Role` or `ClusterRole` bindings
  checked through SSAR against the product API group.
- If an internal IAM store is introduced later, it must become an explicit ADR
  and must still be bound to API-server-observed subject UID and group digest.

Phase 0 product authorization SSAR tuples:

```yaml
aiops-approver:
  apiGroup: aiops.komsco.com
  resource: actionapprovals
  verb: approve

aiops-evidence-viewer:
  apiGroup: aiops.komsco.com
  resource: evidence
  verb: get

aiops-verification:
  apiGroup: aiops.komsco.com
  resource: verifications
  verb: use
```

Cluster ID derivation:

```text
clusterId =
  "ocp:" + sha256(
    infrastructure.config.openshift.io/cluster metadata.uid
    + namespace/kube-system metadata.uid
  )
```

Cluster ID must be derived from API-server-observed immutable object UIDs, not
from user-supplied cluster names, console display names, or endpoint hostnames.

## Operational Data Source Adapters

Avoid hardcoding product-specific APIs inside the Agent Orchestrator. Use
adapters with explicit contracts.

```text
KubernetesOpenShiftAdapter
- typed kube API calls
- user-token or service-account mode
- pagination, timeout, and resource allow-list

MetricsAdapter
- OpenShift Thanos Querier first
- query timeout, range limit, sample limit
- user RBAC preservation where supported

AlertAdapter
- Alertmanager API
- alert fingerprint and status transition tracking

LogAdapter
- OpenShift Logging / Loki first
- Pod log API fallback when logging is unavailable
- max time range and max byte limits

EventAdapter
- Kubernetes Event API
- involvedObject and timestamp normalization

EvidenceServiceAdapter
- opaque evidence identifier resolution through Evidence Service only
- read-time authorization
- classification and retention enforcement

RunbookRagAdapter
- curated runbooks and internal docs
- source provenance and freshness
```

Model provider calls are handled by the Model Gateway / OLS Adapter, not by the
Tool Broker operational adapter set.

## Evidence and Decision Trace

The UI should show an evidence and decision trace rather than internal model
reasoning.

Operator-visible trace items:

- User request and detected intent.
- Tool calls and status.
- Evidence references and freshness.
- Redaction summary where applicable.
- Cause candidates and confidence.
- Policy decision and risk level.
- Proposed action, target, impact, rollback plan, and expiry.
- Approval state.
- Execution result and post-verification.

Every RCA claim should refer to one or more `evidence_ref` entries.

## Evidence Handling

Gateway redaction is not sufficient for host evidence because kubelet, CRI-O,
kernel, and journal data can be collected after the Gateway boundary. Evidence
must be filtered and classified before it enters shared storage or model input.

Recommended evidence flow:

```text
Node Agent / Collector
  -> source-side filtering
  -> collection metadata

Tool Broker / Diagnostics Controller
  -> classification
  -> secret/token redaction
  -> size and line limits
  -> model-safe evidence generation

Evidence Store
  -> redacted evidence

Restricted Raw Store
  -> encrypted raw evidence only when required
  -> no model access
  -> separate permission and short retention
```

Minimum evidence schema:

```text
evidence_id
source_type
target
collector_version
identity_mode
access_scope
originating_subject
namespace_scope
source_identity
query_or_collector_parameters
observed_at
collected_at
time_range
freshness_ttl
classification
redaction_profile
model_access_allowed
raw_access_policy
parent_evidence_id
transformation_chain
content_digest
storage_ref
retention_until
```

Evidence access rules:

- `storage_ref` is an opaque identifier, not a presigned URL.
- Evidence download must go through an authorized Evidence API.
- Evidence access is authorized at read time through Broker-issued grants, not
  only at collection time.
- Evidence Service never receives raw user tokens.
- UI evidence access uses a Broker-issued EvidenceAccessGrant:
  `Gateway -> Tool Broker -> EvidenceAccessGrant -> Gateway -> Evidence Service`.
- Tool Broker verifies the latest user or product authorization and issues
  EvidenceAccessGrant.
- Evidence Service validates grant signature, expiry, evidence target,
  classification, version, content digest, and local access policy.
- Read-time authorization is authoritative. Collection-time authorization is
  provenance, not a durable access grant.
- Expired user credential context returns `reauth_required` for user-scoped
  evidence.
- Product-scoped platform diagnostic evidence requires a product role such as
  `aiops-evidence-viewer`.
- Restricted raw evidence requires an elevated product role and an explicit
  access reason; raw evidence grants are one-time claim grants and raw evidence
  reads are always audited.
- Evidence read audit records include actor, effective identity, identity mode,
  evidence id, classification, access decision, and redaction profile.
- Raw evidence is never available to model adapters.
- Agent Orchestrator and model adapters cannot read object storage directly.

Minimum EvidenceAccessGrant claims:

```yaml
evidenceAccessGrant:
  schemaVersion: v1
  issuer: aiops-tool-broker
  audience: aiops-evidence-service
  grantId: evidence-grant-123
  issuedAt: "2026-06-20T00:04:00Z"
  notBefore: "2026-06-20T00:04:00Z"
  expiresAt: "2026-06-20T00:05:00Z"

  clusterId: cluster-id
  evidenceId: evidence-123
  evidenceVersion: 1
  contentDigest: sha256:...
  classification: internal
  namespace: example
  accessMode: redacted # redacted | raw
  accessReason: incident-review

  subject:
    username: user@example.com
    uid: stable-user-uid
    groupsDigest: sha256:...

  authorization:
    decision: allowed
    identityMode: user-token
    accessScope: namespace
```

Raw EvidenceAccessGrant state machine:

```text
issued
  -> claimed
  -> delivered | denied | expired
```

### Evidence Service / API

The Evidence Service owns evidence retrieval and read-time authorization.

Responsibilities:

- Resolve opaque `storage_ref` identifiers.
- Validate EvidenceAccessGrant and enforce local access policy on every
  evidence read.
- Enforce classification, retention, and raw evidence access policy.
- Return only redacted evidence to Agent and model paths.
- Allow restricted raw evidence only for designated operator roles.
- Record every evidence read in the audit stream.

Production deployment requirements:

- separate Deployment
- separate ServiceAccount
- no direct model access to object storage
- object storage access isolated to Evidence Service and storage writers

## Action Lifecycle Contracts

Approved execution must follow a fixed object lifecycle:

```text
Agent Orchestrator
  -> ActionProposal

Action Registry
  -> normalized action and exact API operation

Policy Engine
  -> risk, preconditions, postconditions

Approval API
  -> SealedActionPlan
  -> planDigest
  -> ApprovalDecision

Execution Coordinator
  -> ExecutionGrant

Action Executor
  -> ExecutionRecord
```

Approval sequence:

```text
Agent Orchestrator
  -> ActionProposal

Approval API
  -> resolves Action Registry entry
  -> creates deterministic normalizedParameters

Policy Engine
  -> risk, preconditions, postconditions

Approval API
  -> issues PlanValidationGrant

Action Executor
  -> dry-run only
  -> returns normalized diff and decision

Approval API
  -> constructs SealedActionPlan
  -> calculates planDigest

UI
  -> displays exact SealedActionPlan and planDigest

Approver
  -> approves sealedPlanId and expectedPlanDigest

Approval API
  -> verifies digest match
  -> records ApprovalDecision
  -> requests fresh authorization revalidation
  -> issues ExecutionGrant
```

Field ownership:

| Field | Owner |
| --- | --- |
| target, requested action | ActionProposal from Agent Orchestrator |
| normalizedParameters | Approval API or internal Execution Coordinator module using Action Registry |
| risk, preconditions, postconditions | Policy Engine |
| planDigest | Approval API |
| idempotencyKey | Approval API |
| approver and approval scope | Approval API |
| execution status and observed result | Action Executor |
| auditRequired | system invariant, not a plan input |

The Agent Orchestrator can propose a target and requested action, but it cannot
author security fields such as `risk`, `policyDecisionId`, `policyBundleHash`,
`preconditions`, `postconditions`, `planDigest`, `approver`, or approval
timestamps.

Minimum fields:

```yaml
sealedActionPlan:
  schemaVersion: v1
  clusterId: cluster-id
  metadata:
    planId: ap-123
    incidentId: inc-123
    requester:
      username: user@example.com
      uid: stable-user-uid
      groupsDigest: sha256:...
      authenticatedByCluster: cluster-id
    idempotencyKey: idem-123
    createdAt: "2026-06-20T00:04:30Z"
    apiCallTimeout: 30s
    verificationDeadline: 10m
    maxMutationAttempts: 1
    maxVerificationAttempts: 3

  target:
    apiVersion: apps/v1
    kind: Deployment
    namespace: example
    name: app
    uid: 00000000-0000-0000-0000-000000000000

  action:
    toolName: rollout_restart_deployment
    toolVersion: v1
    actionRegistry:
      version: v1
      digest: sha256:...
    normalizedParameters:
      restartedAt: "2026-06-20T00:05:10Z"

  safety:
    risk: medium
    policy:
      policyDecisionId: pd-123
      policyBundleHash: sha256:...
      policyInputDigest: sha256:...
      policyDecisionDigest: sha256:...
    dryRun:
      requestDigest: sha256:...
      normalizedDiffDigest: sha256:...
      decision: allowed
    preconditions:
      - type: UIDEquals
        value: 00000000-0000-0000-0000-000000000000
      - type: GenerationEquals
        value: 17
      - type: SelectedSpecDigestEquals
        value: sha256:...
      - type: AvailableReplicasAtLeast
        value: 2
      - type: NoActiveRollout
        value: true
    hardPostconditions:
      - type: ObservedGenerationEqualsTarget
        value: true
      - type: UpdatedReplicasEqualsDesired
        value: true
      - type: AvailableReplicasAtLeast
        value: 2
      - type: ProgressDeadlineNotExceeded
        value: true
      - type: NewReplicaSetObserved
        value: true
    observationalPostconditions:
      - type: NoNewDegradedAlert
        adapter: alertmanager-v1
        identityMode: product-readonly-service-account
        queryScope:
          namespace: example
          workloadUid: 00000000-0000-0000-0000-000000000000
        baselineRef: evidence-alert-baseline-123
        baselineDigest: sha256:...
        observationWindow: 5m
        missingDataResult: inconclusive
    rollbackDescription: >
      A restart is not directly reversible. If replacement pods fail, stop
      further remediation and follow the workload-specific recovery runbook.
    typedRollbackAction: null
    rollbackRequiresApproval: false
    rollbackPossible: false
    expiresAt: "2026-06-20T00:10:00Z"

  approvalPresentation:
    impact:
      affectedWorkloads: 1
      affectedPods: 3
      availabilityRisk: low
      summaryRef: evidence-impact-summary-123
      summaryDigest: sha256:...
    dryRun:
      normalizedDiffRef: evidence-diff-123
      normalizedDiffDigest: sha256:...
    evidenceRefs:
      - evidenceId: evidence-123
        evidenceVersion: 1
        contentDigest: sha256:...
        observedAt: "2026-06-20T00:03:45Z"
        freshnessTtl: 5m
        requiredFreshUntil: "2026-06-20T00:05:40Z"
    runbookRefs:
      - id: deployment-restart-v1
        version: 1
        contentDigest: sha256:...

  digest:
    planDigest: sha256:...
    canonicalization: rfc8785-jcs

---

approvalDecision:
  approvalId: approval-123
  planDigest: sha256:...
  status: approved # approved | revoked | cancelled | expired
  approver:
    username: user@example.com
    uid: stable-user-uid
    groupsDigest: sha256:...
    authenticatedByCluster: cluster-id
  approvedAt: "2026-06-20T00:05:00Z"
  expiresAt: "2026-06-20T00:10:00Z"
  approvalScope: single-target
```

Digest calculation:

```text
planDigest =
  SHA-256(
    canonical JSON of:
      metadata immutable fields
      target
      action
      safety validated fields
      approval presentation references
  )
```

Digest schema:

```yaml
digestSchema: sealed-action-plan-digest-v1
includedFields:
  - /schemaVersion
  - /clusterId
  - /metadata/planId
  - /metadata/incidentId
  - /metadata/requester
  - /metadata/idempotencyKey
  - /metadata/createdAt
  - /metadata/apiCallTimeout
  - /metadata/verificationDeadline
  - /metadata/maxMutationAttempts
  - /metadata/maxVerificationAttempts
  - /target
  - /action
  - /safety
  - /approvalPresentation
excludedFields:
  - /digest
```

Approval, execution status, observed results, and mutable timestamps are
excluded from `planDigest`. `ApprovalDecision` references `planDigest` instead
of being embedded in the immutable plan.

All evidence, normalized diff, impact summary text, and runbook references
shown on the approval screen must be immutable and restorable for approval and
audit retention. If the UI needs fresher evidence, the system creates a new
SealedActionPlan and a new planDigest.

Evidence freshness invariant:

```text
ExecutionGrant.expiresAt
<= min(approvalPresentation.evidenceRefs[*].requiredFreshUntil)
```

If required evidence is stale before execution, execution is rejected. The
system must collect new evidence, construct a new SealedActionPlan, and request
a new approval.

Any mismatch in policy bundle hash, policy input digest, policy decision
digest, action registry version, tool version, normalized parameters, target
UID, or plan digest marks the approval as stale and requires reapproval. If
policy re-evaluation returns a stricter decision or different preconditions,
the existing approval is stale.

### Signed Object Envelope

All signed grants and attestations use a common envelope. Phase 0 must select
the concrete crypto profile before production deployment.
The `signedEnvelope` block below is the product contract view. The actual wire
format is JWS Compact Serialization; only `protectedHeader` becomes the JOSE
Protected Header.

```yaml
signedEnvelope:
  type: aiops.execution-grant
  schemaVersion: v1
  serialization: jws-compact
  payloadCanonicalization: rfc8785-jcs
  unknownFields: reject
  protectedHeader:
    alg: EdDSA
    kid: approval-key-2026-06
    typ: aiops-execution-grant+jws
    cty: application/aiops.execution-grant+json
    "urn:komsco:aiops:schema": v1
    "urn:komsco:aiops:c14n": rfc8785-jcs
    crit:
      - "urn:komsco:aiops:schema"
      - "urn:komsco:aiops:c14n"
```

Envelope rules:

- treat `protectedHeader` as the concrete JOSE Protected Header, not an
  abstract metadata wrapper
- include standard JOSE `alg`; reject `alg` values that do not match the
  selected cryptoProfile
- use standard JOSE `cty` for the payload content type
- place schema and canonicalization markers in collision-resistant private
  header parameters
- include in `crit` only extension header names that are present in the JOSE
  Protected Header; never include standard JOSE header names in `crit`
- require `payload.schemaVersion ==
  protectedHeader["urn:komsco:aiops:schema"]`
- canonicalize the JWS payload with RFC 8785 JCS before base64url encoding it
- validate the JWS signature over the JWS signing input, not over an
  application-defined concatenation
- keep key ID and signing algorithm in the JOSE Protected Header only; signed
  payload schemas must not duplicate them as `keyId` or `algorithm`
- reject unknown signed-payload top-level fields and unknown
  protected-header critical fields
- reject duplicate JSON object members before canonicalization
- require signed payloads to be I-JSON compatible
- encode integer values outside the IEEE-754 double-precision safe exact range
  as schema-defined strings
- represent timestamps as RFC 3339 UTC strings
- represent durations with the documented schema type for each field
- reject schema type coercion such as numeric strings for numeric fields
- sort and deduplicate subject groups before calculating `groupsDigest`
- calculate list digests over canonical arrays with deterministic ordering
  defined by the schema
- include `schemaVersion` in every signed payload and every digest allow-list

Signed object header matrix:

| Object | `typ` | `cty` | Payload issuer | Payload audience | Signing key owner |
| --- | --- | --- | --- | --- | --- |
| EvidenceAccessGrant | `aiops-evidence-access-grant+jws` | `application/aiops.evidence-access-grant+json` | `aiops-tool-broker` | `aiops-evidence-service` | Tool Broker |
| DiagnosticRequestGrant | `aiops-diagnostic-request-grant+jws` | `application/aiops.diagnostic-request-grant+json` | `aiops-tool-broker` | `aiops-host-diagnostics-controller` | Tool Broker |
| PlanValidationGrant | `aiops-plan-validation-grant+jws` | `application/aiops.plan-validation-grant+json` | `aiops-approval-api` | `aiops-action-executor` | Approval API |
| AuthorizationAttestation | `aiops-authorization-attestation+jws` | `application/aiops.authorization-attestation+json` | `aiops-tool-broker` | `aiops-approval-api` | Tool Broker |
| ExecutionGrant | `aiops-execution-grant+jws` | `application/aiops.execution-grant+json` | `aiops-approval-api` | `aiops-action-executor` | Approval API |

Crypto profile:

```yaml
cryptoProfile:
  name: ocp-standard-v1 # or ocp-fips-v1
  grantSignatureAlgorithm: EdDSA
  tlsProfile: openshift-modern
  provider: openshift-secret-bootstrap
  kmsKeyClass: software
```

The example schemas use `EdDSA` only as the default `ocp-standard-v1` example.
FIPS, KMS, HSM, and organization policy can require a different approved
profile. Phase 0 owns that decision.

### PlanValidationGrant

Approval-time dry-run happens before ExecutionGrant exists. The Approval API
or its internal Execution Coordinator module issues a PlanValidationGrant that
permits only server-side dry-run validation for one candidate action.

Minimum PlanValidationGrant claims:

```yaml
planValidationGrant:
  schemaVersion: v1
  issuer: aiops-approval-api
  audience: aiops-action-executor
  grantId: validation-123
  issuedAt: "2026-06-20T00:04:45Z"
  notBefore: "2026-06-20T00:04:45Z"
  expiresAt: "2026-06-20T00:05:15Z"
  maxUses: 1

  clusterId: cluster-id
  candidateRequestDigest: sha256:...
  normalizedParametersDigest: sha256:...
  actionRegistryDigest: sha256:...
  requesterSubjectDigest: sha256:...
  policyDecisionDigest: sha256:...
  policyBindingDigest: sha256:...
  action:
    toolName: rollout_restart_deployment
    toolVersion: v1
  target:
    apiGroup: apps
    resource: deployments
    namespace: example
    name: app
    uid: 00000000-0000-0000-0000-000000000000
  allowedOperation: server_side_dry_run_only
```

PlanValidationGrant rules:

- issued only after requester product authorization for the exact typed action
  and target, plus target visibility authorization, pass
- does not represent that the requester has direct Kubernetes mutation
  permission
- accepted only by the Action Executor dry-run endpoint
- cannot be used on the mutation execution endpoint
- produces normalized diff, request digest, decision, and validation errors
- does not create ExecutionIntent or transition the execution ledger
- does not persist cluster mutation
- is rejected on replay after one successful claim or replay-cache hit

Minimum CandidateActionRequest:

```yaml
candidateActionRequest:
  schemaVersion: v1
  clusterId: cluster-id

  requester:
    username: user@example.com
    uid: stable-user-uid
    groupsDigest: sha256:...

  target:
    apiVersion: apps/v1
    kind: Deployment
    namespace: example
    name: app
    uid: 00000000-0000-0000-0000-000000000000

  action:
    toolName: rollout_restart_deployment
    toolVersion: v1
    actionRegistry:
      version: v1
      digest: sha256:...
    normalizedParameters:
      restartedAt: "2026-06-20T00:05:10Z"

  policy:
    policyDecisionId: pd-123
    policyBundleHash: sha256:...
    policyInputDigest: sha256:...
    policyDecisionDigest: sha256:...
```

CandidateActionRequest digest schema:

```yaml
candidateRequestDigest:
  includedFields:
    - /schemaVersion
    - /clusterId
    - /requester
    - /target
    - /action
    - /policy

normalizedParametersDigest:
  includedFields:
    - /action/normalizedParameters

requesterSubjectDigest:
  includedFields:
    - /requester/uid
    - /requester/username
    - /requester/groupsDigest

policyDecisionDigest:
  verification: exact_match
  sourceField: /policy/policyDecisionDigest

policyBindingDigest:
  includedFields:
    - /policy/policyDecisionId
    - /policy/policyBundleHash
    - /policy/policyInputDigest
    - /policy/policyDecisionDigest
```

PlanValidationGrant execution contract:

```text
Action Executor receives:
- PlanValidationGrant
- CandidateActionRequest

Executor checks:
- validate grant signature, audience, expiry, maxUses, and clusterId
- canonicalize CandidateActionRequest with RFC 8785 JCS
- recompute candidateRequestDigest
- recompute normalizedParametersDigest
- recompute actionRegistryDigest from the local registry bundle
- recompute requesterSubjectDigest
- compare CandidateActionRequest.policy.policyDecisionDigest with
  PlanValidationGrant.policyDecisionDigest
- recompute policyBindingDigest
- compare every recomputed digest and exact-match digest with the grant
- execute server-side dry-run only
```

### AuthorizationAttestation and ExecutionGrant

The Tool Broker issues an AuthorizationAttestation after running SSAR with the
approver credential context. The Approval API or its internal Execution
Coordinator module validates the attestation and uses it to issue a signed
ExecutionGrant. The Action
Executor validates the ExecutionGrant only; it does not verify the original
AuthorizationAttestation directly in MVP.

Minimum AuthorizationAttestation claims:

```yaml
authorizationAttestation:
  schemaVersion: v1
  issuer: aiops-tool-broker
  audience: aiops-approval-api
  attestationId: authz-123
  issuedAt: "2026-06-20T00:05:12Z"
  notBefore: "2026-06-20T00:05:12Z"
  expiresAt: "2026-06-20T00:05:42Z"

  clusterId: cluster-id
  approverAuthContextBinding: sha256:...
  approver:
    username: user@example.com
    uid: stable-user-uid
    groupsDigest: sha256:...

  planDigest: sha256:...
  action:
    toolName: rollout_restart_deployment
    toolVersion: v1
    actionRegistry:
      version: v1
      digest: sha256:...

  target:
    apiGroup: apps
    resource: deployments
    subresource: ""
    namespace: example
    name: app
    uid: 00000000-0000-0000-0000-000000000000

  kubernetesAuthorization:
    verb: patch
    ssarDecision: allowed
    evaluatedAt: "2026-06-20T00:05:12Z"
```

Minimum ExecutionGrant claims:

```yaml
executionGrant:
  schemaVersion: v1
  issuer: aiops-approval-api
  audience: aiops-action-executor
  grantId: jti-123
  issuedAt: "2026-06-20T00:05:15Z"
  notBefore: "2026-06-20T00:05:15Z"
  expiresAt: "2026-06-20T00:05:40Z"

  clusterId: cluster-id
  planDigest: sha256:...
  approvalId: approval-123
  authorization:
    attestationId: authz-123
    attestationDigest: sha256:...
    attestationIssuer: aiops-tool-broker
    evaluatedAt: "2026-06-20T00:05:12Z"
    expiresAt: "2026-06-20T00:05:42Z"
    approverSubjectDigest: sha256:...
    authorizationDescriptorDigest: sha256:...

  approver:
    username: user@example.com
    uid: stable-user-uid
    groupsDigest: sha256:...

  action:
    toolName: rollout_restart_deployment
    toolVersion: v1
    actionRegistry:
      version: v1
      digest: sha256:...

  target:
    apiGroup: apps
    resource: deployments
    subresource: ""
    namespace: example
    name: app
    uid: 00000000-0000-0000-0000-000000000000

  kubernetesAuthorization:
    verb: patch

  policyBundleHash: sha256:...
```

Execution request contract:

```text
Action Executor receives:
- ExecutionGrant
- full SealedActionPlan

Executor checks:
- validate SealedActionPlan schema
- build a projection using `digestSchema.includedFields`
- verify excluded fields such as `/digest` are not part of the projection
- canonicalize the projection with RFC 8785 JCS
- calculate SHA-256 over the canonical projection
- compare the calculated planDigest with ExecutionGrant.planDigest
- compare actionRegistry version and digest with the local registry bundle
- load immutable ApprovalDecision from the authoritative ledger by approvalId
- reject if ApprovalDecision status is revoked, cancelled, expired, or not
  approved
- compare ApprovalDecision.planDigest with ExecutionGrant.planDigest
```

Grant signing contract:

JOSE Protected Header:

- `alg`
- `kid`
- `typ`
- `cty`
- private critical headers for schema and canonicalization

Signed payload:

- `schemaVersion`
- `issuer`
- `audience`
- `issuedAt`
- `notBefore`
- `expiresAt`
- object-specific claims

Rules:

- `payload.schemaVersion` must match the protected schema header
- key ID and algorithm exist only as JOSE `kid` and `alg`
- rotate signing keys on a defined schedule
- reject grants signed by revoked keys
- reject grants with unexpected audience
- bind grant to planDigest, approvalId, target UID, tool name, tool version,
  action registry digest, and policy bundle hash

Validity invariant:

```text
ExecutionGrant.expiresAt
<= AuthorizationAttestation.expiresAt
<= ApprovalDecision.expiresAt
<= SealedActionPlan.expiresAt
<= min(required evidence freshness deadlines)
```

Signing key management:

- define signing key storage: KMS preferred, OpenShift Secret acceptable only
  for non-production or bootstrap profiles
- define keyId publication and cache TTL
- define previous-key verification grace period
- define emergency revocation procedure
- define allowed clock skew for `notBefore` and `expiresAt`
- restrict signing key access to the Approval API ServiceAccount
- define separate Broker signing keys for AuthorizationAttestation,
  EvidenceAccessGrant, and DiagnosticRequestGrant
- restrict Broker signing key access to Tool Broker ServiceAccount
- audit every signing and verification failure

A signed grant is not enough to guarantee one-time execution. The Action
Executor must atomically claim `grantId` in durable storage before calling the
Kubernetes API.

Authoritative ledger decision:

- Approval API, its internal Execution Coordinator module, and Action Executor share one
  authoritative execution ledger.
- Action Executor loads ExecutionGrant state and immutable ApprovalDecision by
  `grantId` and `approvalId` in the same transaction.
- Action Executor verifies planDigest, ApprovalDecision status, and all expiry
  invariants before any mutation intent is committed.
- Action Executor creates ExecutionIntent and pre-execution audit outbox
  records before attempting the claim.
- Action Executor claims `issued -> claimed` with a DB compare-and-set after
  the intent and outbox records are prepared.
- ExecutionIntent, audit outbox, approval validation, and grant claim must be
  in the same DB transaction when possible.
- If they cannot share one transaction, the transactional boundary and recovery
  reconciliation must be explicit before Phase 3 implementation.

Execution claim transaction:

```text
1. load grant and ApprovalDecision
2. verify planDigest, approval status, and expiry invariants
3. create ExecutionIntent and pre-execution audit outbox record
4. compare-and-set grant state issued -> claimed
5. commit before calling the Kubernetes API
```

Ledger DB permission boundary:

```text
Approval API DB role
- create SealedActionPlan
- record, cancel, or expire ApprovalDecision
- issue ExecutionGrant
- read ExecutionRecord
- must not update execution result, grant claim state, or execution outbox

Action Executor DB role
- read SealedActionPlan and ApprovalDecision
- read ExecutionGrant
- atomically transition only issued -> claimed for an existing grant
- record ExecutionIntent
- create and update ExecutionRecord
- create execution audit outbox entries
- must not create grants, change ApprovalDecision, or broaden plan scope

Audit Publisher DB role
- read audit outbox
- update delivery state, retry count, last error, and delivered timestamp
- must not update plans, approvals, grants, or execution outcomes
```

Phase 3 should prefer stored procedures or a narrow transaction API over direct
table updates for grant claim, approval cancellation, and audit delivery state.
If the Action Executor is compromised, it must still be unable to approve a
plan, create a new grant, or edit an existing ApprovalDecision.

ExecutionGrant state machine:

```text
issued
  -> claimed
  -> executing
  -> mutation_succeeded | mutation_failed | indeterminate
```

A second claim of the same `grantId` is rejected. If the API result is
indeterminate, the Executor must inspect the execution ledger and live resource
state before deciding whether retry is safe. It must not blindly repeat the
same mutation.

ExecutionRecord separates API mutation outcome from remediation effect:

```yaml
executionRecord:
  mutationOutcome:
    status: mutation_succeeded # mutation_succeeded | mutation_failed | indeterminate
    apiResponseDigest: sha256:...

  hardVerification:
    status: passed # passed | failed | timed_out
    completedAt: "2026-06-20T00:07:00Z"

  observationalVerification:
    status: passed # passed | degraded | inconclusive | timed_out
    identityMode: product-readonly-service-account
    productAuthorizationRequired: aiops-verification
    completedAt: "2026-06-20T00:10:00Z"

  overallOutcome:
    status: remediated # remediated | mutation_failed | not_remediated | inconclusive
```

Observational verification failure is not the same as mutation failure. It must
not automatically trigger another rollout, scale change, or eviction.

Execution-time checks:

1. Validate ExecutionGrant signature, audience, expiry, target, and planDigest.
2. Validate AuthorizationAttestation digest binding inside the ExecutionGrant.
3. Check approval status and expiry from the authoritative ledger.
4. Check required evidence freshness deadlines.
5. Re-evaluate policy with the current policy bundle.
6. Verify typed preconditions.
7. Re-run dry-run or server-side validation.
8. Reject duplicate execution unless the idempotency state is complete and
   equivalent.
9. Compare current state with the approval-time state.
10. Verify desired postconditions after execution.

Action-specific precondition guidance:

| Action | Required preconditions |
| --- | --- |
| rollout_restart_deployment | UID, generation, PodTemplate digest, maxUnavailable, maxSurge, readiness, available replicas, no active rollout |
| set_replicas_within_bounds | UID, current replicas, `/scale` resourceVersion, HPA absence, min/max bounds |
| evict_one_unhealthy_controller_owned_pod | Pod UID, ownerReference, readiness state, PDB allowance, replacement capacity |

GitOps, OpenShift Operators, HPA, and external controllers can immediately
reconcile fields after execution. Plans must detect those ownership signals
before mutation and either deny, require a runbook-specific policy, or explain
that the requested change will not persist.

PDB is a hard gate for pod eviction. For Deployment restart safety, prioritize
Deployment rollout strategy, readiness, available replicas, and active rollout
state.

The `restartedAt` value is part of `normalizedParameters` and must be fixed
before execution. Repeating the same `idempotencyKey` must reuse the same patch
payload so a retry does not trigger a second rollout.

For MVP, `set_replicas_within_bounds` is denied when an HPA controls the target
workload. The system should propose an HPA-specific runbook instead of applying
a direct replica override.

Post-verification ownership:

```text
Action Executor
- exact target resource GET/watch
- generation, replicas, readiness, and ReplicaSet checks
- hard postconditions

Execution Coordinator
- calls Broker dedicated verification endpoints
- metrics, alerts, and events checks
- observational postconditions
- uses product read-only service account only when product authorization
  allows `aiops-verification`
- UI labels these checks as platform diagnostic verification, not user-scoped
  verification

Agent Orchestrator
- explains the result
- does not decide execution success
```

Time contracts:

```yaml
apiCallTimeout: 30s
verificationDeadline: 10m
observationWindow: 5m
```

Server-side dry-run validates admission, validation, and merge behavior. It
does not prove new Pods will become healthy or that alerts will not fire.
Dry-run output should be stored as normalized diff, decision, and request
digest rather than a raw object response because generated values can differ
from the real request.

## Action Policy

Actions should be classified by context, not only by action name.

Risk factors:

- Production or development namespace.
- Replica count and availability.
- StatefulSet or data-bearing workload.
- PDB and available replicas.
- Cluster Operator ownership.
- HPA ownership.
- OpenShift Operator ownership.
- Argo CD or GitOps reconciliation ownership.
- External controller field ownership.
- Number of affected pods and users.
- Change scope and timing.
- Rollback feasibility.

| Risk | Examples | Policy |
| --- | --- | --- |
| Read-only | list pods, get events, query metrics, read logs | allowed by default |
| Low-risk mutate | restart one Deployment with healthy replicas | approval and revalidation |
| Medium-risk mutate | bounded scale, approved eviction | approval, dry-run, preconditions |
| High-risk mutate | broad patch, operator resource, node drain | restricted runbook only |
| Break-glass | SSH, nsenter, systemctl, host modification | disabled by default |

`patch_resource` and `apply_manifest` are generic mutation interfaces. They
should be excluded from the initial allow-list unless reduced to preapproved
fields and schemas.

## Audit Model

OpenShift API audit is necessary but not sufficient. The product needs its own
structured audit records because API audit settings may not capture the full
decision context or request body.

Minimum audit fields:

```text
incident_id
session_id
trace_id
cluster_id
actor
subject_uid
effective_identity
identity_mode
tool_name
tool_version
target
plan_id
plan_digest
grant_id
normalized_input
evidence_refs
policy_decision_id
action_registry_digest
policy_bundle_hash
approval_id
risk
started_at
completed_at
result
error_category
redaction_summary
```

Recommended storage:

- DB for sessions, incidents, ActionProposal, SealedActionPlan,
  ApprovalDecision, ExecutionGrant, ExecutionRecord, and workflow status.
- Searchable log or SIEM for tool calls and execution events.
- Object storage for long-lived evidence and raw artifacts.
- OpenShift API audit for the actual Kubernetes API mutations.
- Kubernetes Events only as a user-facing status aid, not as the audit source
  of truth.

Mutation audit durability:

- Before mutation, commit ExecutionIntent and audit outbox records durably.
- If the pre-execution audit commit fails, reject the mutation.
- During mutation, atomically transition the grant to `claimed` and
  `executing`.
- After mutation, record the result in DB and outbox.
- SIEM or external log delivery is retried asynchronously.
- Delivery failure after execution sets `audit_pending` and raises an alert.
- A completed Kubernetes mutation is not rolled back solely because external
  audit delivery later fails.

Mutations fail closed unless the execution intent and audit outbox entry have
been durably committed before execution. Post-execution audit delivery is
retried and monitored; delivery failure cannot retroactively prevent a mutation
that has already occurred.

## Runtime Deployment Model

Recommended namespaces:

```text
komsco-ai-dev
- development and integration testing

aiops-system
- recommended production namespace for shared AIOps services

komsco-ai
- acceptable production namespace if the product boundary stays KOMSCO-local
```

Recommended workloads:

```text
Gateway
- Deployment
- Service
- Route or ConsolePlugin proxy

Agent Orchestrator
- Deployment
- Service
- no mutation RBAC

Tool Broker
- separate Deployment in production
- separate ServiceAccount
- internal ClusterIP Service only
- default-deny NetworkPolicy
- accepts credential endpoints only from Gateway
- accepts evidence tool endpoints only from Agent Orchestrator
- accepts authorization revalidation and observational verification endpoints
  only from Approval API
- no DiagnosticRequest CRD create permission
- user-token and read-only-service-account execution modes

Policy Engine
- shared library or service for MVP
- enforcement inside Tool Broker and Action Executor
- versioned GitOps-managed policy bundle

Approval API
- separate production Deployment
- separate ServiceAccount
- persistent approval store
- authoritative execution ledger owner
- the only caller permitted to invoke Action Executor
- module mode allowed only for local development

Action Executor
- Deployment or Job runner
- separate mutation ServiceAccount
- claims ExecutionGrant in authoritative ledger with compare-and-set
- no arbitrary shell

Evidence Service / API
- separate Deployment
- separate ServiceAccount
- opaque evidence reference resolver
- read-time authorization and audit
- classification and retention enforcement

Host Diagnostics Controller
- Deployment
- DiagnosticRequest CRD
- only workload with DiagnosticRequest CRD create permission
- validates bearer DiagnosticRequestGrant before CRD creation
- result reference management

Host Diagnostics Agent
- DaemonSet
- collector-specific ServiceAccount and SCC profile
- outbound mTLS to controller

Break-glass Tools
- disabled by default
- short-lived Job preferred over always-on privileged DaemonSet
```

## Primary User Flows

### Flow 1: Read-only RCA

```text
User asks about an alert or failing workload
-> Gateway validates request and terminates UserToken
-> Agent Orchestrator classifies intent
-> Tool Broker queries alerts, events, resources, logs, and metrics
-> Broker enforces RBAC, output limits, redaction, and audit
-> Host Diagnostics Controller is used only if node-local evidence is required
-> Agent Orchestrator synthesizes evidence-backed cause candidates
-> UI shows evidence trace, RCA, uncertainty, and suggested next steps
```

### Flow 2: Host-level Diagnostics

```text
OpenShift API and metrics are insufficient
-> Agent requests host diagnostics through the Tool Broker
-> Policy Engine checks requester authorization and collector profile
-> Tool Broker sends DiagnosticRequestGrant to Host Diagnostics Controller API
-> Host Diagnostics Controller validates the grant and creates DiagnosticRequest CRD
-> Host Diagnostics Controller selects the node agent
-> Node Agent runs the allowed collector
-> Large evidence is stored externally; CRD status records reference and digest
-> Agent correlates host evidence with cluster events and metrics
```

### Flow 3: Approval-gated Remediation

```text
User asks to fix a confirmed issue
-> Agent proposes an ActionProposal
-> Approval API resolves Action Registry entry and deterministic parameters
-> Policy Engine calculates contextual risk
-> Approval API issues PlanValidationGrant for server-side dry-run only
-> Action Executor returns normalized dry-run diff and decision
-> Approval API constructs SealedActionPlan and calculates planDigest
-> UI shows exact SealedActionPlan, planDigest, target, impact, dry-run, rollback, expiry, and evidence
-> Approver UI registers approver credential context through Gateway and Broker
-> Approval API verifies product authorization and target authorization
-> Approval API verifies expectedPlanDigest and records ApprovalDecision
-> Approval API issues a one-time ExecutionGrant
-> Action Executor validates ExecutionGrant
-> Action Executor revalidates policy, target state, preconditions, and dry-run
-> Action Executor runs the typed action using the ExecutionGrant
-> Executor verifies hard postconditions
-> Execution Coordinator verifies observational postconditions through Broker
-> Audit record is finalized
```

### Flow 4: Break-glass

```text
Normal tools cannot confirm or remediate the issue
-> Agent explains why break-glass is required
-> Policy Engine marks elevated risk
-> UI requires explicit approval and scope
-> Temporary privileged Job runs with fixed image, entrypoint, and arguments
-> Egress and node scheduling are restricted
-> Results are captured and stored
-> Job is cleaned up by deadline, TTL, and reconciliation
```

## Rust Implementation Direction

Recommended crates and implementation areas:

```text
HTTP
- axum

gRPC / streaming node-agent channel
- tonic

Kubernetes/OpenShift API
- kube
- k8s-openapi

Async runtime
- tokio

Serialization and tool schemas
- serde
- schemars

Policy
- versioned allow-list first
- OPA/Rego or CEL later if policy grows

Telemetry
- tracing
- opentelemetry from Phase 1

Transport security
- rustls
- mTLS for node-agent channel

Storage
- sqlx or sea-orm for DB-backed workflow state
- object-store crate if S3-compatible evidence storage is used
```

The first Rust implementation should keep the tool interface explicit and
typed. Avoid a generic `run_command` abstraction.

## Reliability and Operations

This product must be observable from Phase 1 because the safety model depends
on knowing which tool calls ran, which evidence was missing, and whether a
workflow is stuck.

Minimum operational contracts:

- workflow state machine with restart recovery
- idempotency for all mutations
- cancellation propagated to tool calls and collectors
- maximum tool steps, fan-out, evidence bytes, and wall-clock budget
- adapter-specific circuit breakers and concurrency limits
- mutation fail-closed when policy evaluation fails
- mutation fail-closed when pre-execution ExecutionIntent or audit outbox
  commit fails
- partial failure and missing evidence surfaced in read-only investigations
- Host Agent connection and node coverage monitoring
- approval pending, expired, executing, failed, and cancelled state monitoring

Core metrics:

```text
tool_call_latency
tool_call_error_total
evidence_age_seconds
workflow_stuck_total
approval_expired_total
action_precondition_failed_total
audit_write_failed_total
node_agent_connected_ratio
redaction_detected_total
model_schema_validation_failed_total
```

## Implementation Phases

### Phase 0: Security Envelope

- Threat model the full Copilot, Agent, Broker, Executor, and Host Diagnostics
  path.
- Define a user and ServiceAccount permission matrix.
- Define the Gateway-to-Broker credential delegation contract.
- Define approver credential context, EvidenceAccessGrant,
  PlanValidationGrant, DiagnosticRequestGrant, AuthorizationAttestation, and
  ExecutionGrant contracts.
- Define service-to-service workload identity, mTLS or audience-bound token
  validation, and endpoint caller matrix.
- Define data classification and redaction policy.
- Define ToolCall, Evidence, ActionProposal, SealedActionPlan,
  ApprovalDecision, ExecutionGrant, ExecutionRecord, and Audit schemas.
- Define typed preconditions, idempotency, and workflow state machines.
- Define ActionProposal, SealedActionPlan, ApprovalDecision, ExecutionGrant,
  and ExecutionRecord lifecycle.
- Define action lifecycle field ownership, RFC 8785 JCS digest rules, and
  ApprovalDecision schema.
- Define Action Registry entries that generate both SSAR attributes and actual
  Kubernetes API requests.
- Define actionRegistry version/digest propagation into SealedActionPlan,
  PlanValidationGrant, and ExecutionGrant.
- Define Broker credential routing by instance ID and reauth behavior on Broker
  pod loss.
- Define pre-execution durable audit outbox.
- Define the policy bundle format, versioning, and GitOps delivery.
- Define signed object envelope, cryptoProfile, and Grant canonicalization
  rules.
- Define JOSE Protected Header fields, private critical headers, and I-JSON
  payload constraints for all signed objects.
- Define signed payload `schemaVersion` requirements and protected-header
  schema equality checks.
- Define CandidateActionRequest schema and digest allow-lists.
- Define DiagnosticRequestCandidate schema and `diagnosticRequestDigest`
  allow-list.
- Define clusterId derivation from API-server-observed immutable object UIDs.
- Define product authorization authority and mapping to OpenShift RBAC.
- Define product authorization SSAR tuples for approval, evidence, and
  verification roles.
- Define execution ledger DB roles, stored procedure or transaction API
  boundaries, and denied table updates for each service.
- Define evidence freshness invariants for approval and execution.
- Define Action Registry and Policy Bundle signature, signer identity,
  anti-rollback, activation time, grace period, and emergency revocation
  rules.
- Split frozen v1 schema, grant, digest, and test-vector details into a
  dedicated implementation specification before Phase 2 or Phase 3 coding.
- Test cross-namespace access boundaries and prompt-injection handling.

Completion criteria:

- Threat model is approved.
- RBAC and SCC permission matrix is approved.
- Workload identity mechanism is selected and tested.
- Service call matrix tests pass.
- Token and credential leakage tests pass.
- Grant replay and stale-plan negative tests pass.
- Evidence classification and retention policy is approved.
- Signing key issuance, rotation, revocation, keyId publication, clock skew,
  and verification rules are approved.
- Read-only Tool Registry v1 is frozen for Phase 1.
- Mutation Action Registry v1 is drafted in Phase 0 and frozen before Phase 3.
- Crypto profile and signed envelope negative tests pass.
- Signed payload `schemaVersion` and protected-header schema mismatch tests
  pass.
- JWS protected-header and RFC 8785 I-JSON negative tests pass.
- CandidateActionRequest digest recomputation, `policyDecisionDigest`
  exact-match, and `policyBindingDigest` recomputation tests pass.
- DiagnosticRequestCandidate digest recomputation and policy binding tests
  pass.
- Execution ledger DB role permission tests pass.
- Evidence freshness expiry tests pass.
- Registry and policy bundle anti-rollback and revocation tests pass.
- Audit outbox failure tests pass.

### Phase 1: Read-only Evidence Platform

- Gateway.
- Agent Orchestrator with no mutation RBAC.
- Tool Broker.
- service-to-service workload identity.
- Evidence Service / API.
- EvidenceAccessGrant for UI evidence reads.
- Kubernetes/OpenShift, Thanos, Alertmanager, Log, Event, and Runbook
  adapters.
- Model Gateway / OLS Adapter.
- Evidence provenance and freshness display.
- Output limits, pagination, timeout, and redaction.
- OpenTelemetry traces and core metrics.
- No mutation RBAC exists in this phase.

Completion criteria:

- Every major RCA claim has an evidence reference.
- User RBAC boundaries are preserved.
- Tokens and Secrets do not appear in prompts, audit records, logs, or traces.
- Tool timeout, pagination, and output limits are enforced.
- Workflow recovery, cancellation, and partial failure behavior are observable.
- Workload identity is enforced on control-plane service calls.
- Evidence reads go through Evidence Service with read-time authorization.

### Phase 2: Host Diagnostics

- Validate each collector against OpenShift SCC, SELinux, hostPath, hostPID,
  and runtime socket requirements.
- Split passive and elevated collectors into separate profiles.
- Add DiagnosticRequest CRD and Host Diagnostics Controller.
- Add node-agent outbound mTLS channel.
- Add source-side filtering, classification, redaction, and restricted raw
  storage.
- Add Broker-signed DiagnosticRequestGrant or equivalent requester
  authorization attestation.
- Add DiagnosticRequestCandidate schema and Controller-side
  `diagnosticRequestDigest` recomputation before CRD creation.
- Ensure only Host Diagnostics Controller can create DiagnosticRequest CRDs;
  Tool Broker can call only the Controller request API.
- Store large evidence outside the CRD.
- Handle node-agent failure, timeout, cancellation, and partial success.
- Verify node-agent certificate identity, rotation, revocation, and Node UID
  binding.

### Phase 3: Approval-gated Actions

- Add ActionProposal, SealedActionPlan, ApprovalDecision, ExecutionGrant, and
  ExecutionRecord state model.
- Add separate Action Executor ServiceAccount.
- Add approver credential context, Broker SSAR revalidation, signed
  AuthorizationAttestation, and one-time ExecutionGrant.
- Add PlanValidationGrant for approval-time dry-run.
- Add grant signing key management, keyId, audience checks, rotation, and
  revocation.
- Add approvalPresentation references to SealedActionPlan and include them in
  planDigest.
- Add CandidateActionRequest schema and PlanValidationGrant digest
  recomputation in Action Executor.
- Add planDigest projection recomputation using `digestSchema.includedFields`
  rather than hashing the full SealedActionPlan object.
- Add evidence freshness check before grant issuance and before execution.
- Add DB role or stored-procedure enforcement for Approval API, Action
  Executor, and Audit Publisher ledger access.
- Add durable grant claim ledger with `issued`, `claimed`, `executing`,
  `mutation_succeeded`, `mutation_failed`, and `indeterminate` states.
- Block Agent Orchestrator, Tool Broker, Gateway, and Node Agents from Action
  Executor ingress.
- Add idempotency keys and action execution state machine.
- Add pre-execution audit outbox and `audit_pending` monitoring.
- Allow only:
  - `rollout_restart_deployment`
  - `set_replicas_within_bounds`
  - `evict_one_unhealthy_controller_owned_pod`
- Add dry-run, typed preconditions, stale-approval prevention, and
  post-verification.
- Split hard postconditions and observational postconditions with explicit time
  contracts.
- Detect HPA, GitOps, Operator, and external controller ownership before
  execution.

### Phase 4: Restricted Runbooks

- Convert common incident classes into predefined runbooks.
- Allow actions only through runbook-defined steps.
- Add stronger policy checks for namespace, resource type, owner, and user role.
- Introduce `patch_preapproved_field` only for documented field schemas.

### Phase 5: Break-glass Host Operations

- Add disabled-by-default break-glass profile.
- Use short-lived privileged Jobs with fixed image digests and fixed
  entrypoints.
- Reject arbitrary command input.
- Restrict node scheduling and egress.
- Enforce active deadlines, TTL cleanup, and reconciliation cleanup.
- Record separate audit events.

## Architecture Decisions

| ADR | Decision |
| --- | --- |
| ADR-001 | Use a hybrid read model. User-visible resources use user token; product diagnostics use read-only ServiceAccount. Silent elevation is forbidden. |
| ADR-002 | Use a separate Action Executor ServiceAccount for mutations. Approver authorization is checked with SSAR at approval and execution time. |
| ADR-003 | Use DiagnosticRequest CRD plus Host Diagnostics Controller and outbound mTLS/gRPC from node agents. |
| ADR-004 | Prefer a dedicated `aiops-system` namespace for production AIOps services. |
| ADR-005 | Initial mutation allow-list is rollout restart, bounded scale, and single unhealthy controller-owned pod eviction. |
| ADR-006 | Store workflow state in DB, searchable audit events in log/SIEM, evidence in object storage, and Kubernetes API mutations in OpenShift audit. Kubernetes Events are auxiliary only. |
| ADR-007 | Use OLS or other LLM APIs as knowledge and synthesis providers, not as authorities for live cluster state. |
| ADR-008 | Tool Broker is a separate production Deployment with isolated credential memory; sidecar mode is local-development only. |
| ADR-009 | Runtime socket access is a privileged API capability and is disabled by default. |
| ADR-010 | OpenTelemetry traces and core operational metrics are required from Phase 1. |
| ADR-011 | Approval-time credentials use a separate approverAuthContextId and Broker-issued AuthorizationAttestation. |
| ADR-012 | Action Executor accepts one-time ExecutionGrant requests only from Approval API in MVP; a separate Execution Coordinator requires its own workload identity decision. |
| ADR-013 | SealedActionPlan immutable digest excludes ApprovalDecision and execution status; stale digest, policy, tool, parameter, or target mismatches require reapproval. |
| ADR-014 | Broker credential contexts are instance-bound in MVP; Broker pod loss invalidates the context and requires reauthentication. |
| ADR-015 | Control-plane services require authenticated workload identity in addition to NetworkPolicy. |
| ADR-016 | Evidence reads must go through Evidence Service with read-time authorization and opaque storage references. |
| ADR-017 | Action Registry generates both SSAR attributes and concrete Kubernetes API requests. |
| ADR-018 | ExecutionGrant one-time use is enforced by a durable atomic claim ledger. |
| ADR-019 | Mutations require durable pre-execution audit outbox commit; post-execution external audit delivery is retried and monitored. |
| ADR-020 | UI evidence reads use Broker-issued EvidenceAccessGrant; Evidence Service never receives raw user tokens. |
| ADR-021 | Approval-time dry-run uses PlanValidationGrant and cannot persist mutations. |
| ADR-022 | AuthorizationAttestation audience is Approval API; Action Executor validates only the signed ExecutionGrant and attestation digest binding. |
| ADR-023 | PlanValidationGrant is bound to candidate request, normalized parameters, action registry, requester subject, and policy decision digests. |
| ADR-024 | SealedActionPlan and ExecutionGrant include action registry version and digest. |
| ADR-025 | Host diagnostics requester identity is carried by Broker-signed DiagnosticRequestGrant, not inferred from the CRD creator. |
| ADR-026 | PlanValidationGrant uses typed action dry-run delegation, not direct user mutation permission, and requires target visibility authorization. |
| ADR-027 | DiagnosticRequestGrant includes clusterId, Node UID, request digest, collector profile, limits, evidence policy, and replay controls. |
| ADR-028 | Observational verification uses product diagnostic identity and must be labeled separately from user-scoped verification. |
| ADR-029 | Approval presentation evidence, impact summary, dry-run diff, and runbook references are immutable and included in SealedActionPlan digest. |
| ADR-030 | Signed grants and attestations use a versioned JWS envelope with RFC 8785 JCS payload canonicalization and reject unknown critical fields. |
| ADR-031 | Action Executor loads ApprovalDecision from the authoritative ledger and rejects revoked, cancelled, expired, or non-approved decisions before claiming a grant. |
| ADR-032 | Model Gateway / OLS Adapter is separate from Tool Broker and never receives cluster credentials or raw evidence storage access. |
| ADR-033 | Phase 0 selects a cryptoProfile and registry or policy bundle supply-chain controls before production deployment. |
| ADR-034 | Signed object JWS Protected Headers use standard `alg`, `kid`, `typ`, and `cty` plus collision-resistant private critical headers for schema and canonicalization. |
| ADR-035 | CandidateActionRequest has an explicit schema and digest allow-lists for dry-run validation binding. |
| ADR-036 | Approval API, Action Executor, and Audit Publisher use separate ledger DB roles; Executor cannot create grants or modify ApprovalDecision. |
| ADR-037 | Execution requires all approvalPresentation evidence references to be fresh through the ExecutionGrant expiry. |
| ADR-038 | MVP product authorization roles are authoritative in OpenShift RBAC and checked with API-server-observed subject identity. |
| ADR-039 | clusterId is derived from API-server-observed immutable OpenShift and Kubernetes object UIDs. |
| ADR-040 | Policy Engine output digest is exact-matched as `policyDecisionDigest`; the enclosing policy binding uses a separate `policyBindingDigest`. |
| ADR-041 | Signed payload schemas do not duplicate JOSE `kid` or `alg`; key selection and algorithm are carried by the Protected Header. |
| ADR-042 | Lost in-memory credential contexts force dependent workflows into `reauth_required` before any further privileged step. |
| ADR-043 | Every signed grant or attestation payload includes `schemaVersion`, and it must match the private schema header in the JWS Protected Header. |
| ADR-044 | `planDigest` is calculated from the digest-schema projection, not from the complete SealedActionPlan object. |
| ADR-045 | Host Diagnostics Controller is the only DiagnosticRequest CRD creator; Tool Broker can only submit bearer DiagnosticRequestGrant to the Controller API. |
| ADR-046 | DiagnosticRequestGrant `requestDigest` is calculated from a DiagnosticRequestCandidate projection and verified by the Host Diagnostics Controller before CRD creation. |
| ADR-047 | Tool Broker accepts Approval API calls only for authorization revalidation and observational verification endpoint families. |
| ADR-048 | The architecture document is frozen at v1; detailed schemas, grants, digest rules, and test vectors move to separate implementation specification documents. |

## Recommended First Milestone

The first milestone should be the Security Envelope plus a read-only
end-to-end path:

```text
Console Plugin
  -> Gateway
    -> Agent Orchestrator
      -> Tool Broker
        -> Kubernetes/OpenShift API / Thanos / Alertmanager / Logs
      -> evidence-backed RCA response
```

The second milestone should add:

```text
Host Diagnostics Controller
  -> DiagnosticRequest CRD
  -> Rust Host Diagnostics DaemonSet
  -> node-local read-only evidence
  -> integrated RCA output
```

Mutating operations should start only after the read-only evidence platform,
identity boundaries, audit model, and host diagnostics path are stable and
auditable.

## Reference Links

- OpenShift dynamic plugin user token forwarding:
  <https://docs.redhat.com/en/documentation/openshift_container_platform/4.21/html/web_console/dynamic-plugins>
- OpenShift SCC management:
  <https://docs.redhat.com/en/documentation/openshift_container_platform/4.21/html/authentication_and_authorization/managing-pod-security-policies>
- Monitoring stack for Red Hat OpenShift:
  <https://docs.redhat.com/en/documentation/monitoring_stack_for_red_hat_openshift/4.21/html-single/about_monitoring/index>
- Kubernetes disruptions and Eviction API context:
  <https://kubernetes.io/docs/concepts/workloads/pods/disruptions/>
- Kubernetes API concepts and dry-run behavior:
  <https://kubernetes.io/docs/reference/using-api/api-concepts/>
- Kubernetes SelfSubjectAccessReview:
  <https://kubernetes.io/docs/reference/kubernetes-api/authorization-resources/self-subject-access-review-v1/>
- Kubernetes SelfSubjectReview:
  <https://kubernetes.io/docs/reference/kubernetes-api/authentication-resources/self-subject-review-v1/>
- Kubernetes authorization attributes:
  <https://kubernetes.io/docs/reference/access-authn-authz/authorization/>
- Kubernetes projected ServiceAccount tokens:
  <https://kubernetes.io/docs/tasks/configure-pod-container/configure-service-account/>
- Kubernetes NetworkPolicy:
  <https://kubernetes.io/docs/concepts/services-networking/network-policies/>
- Kubernetes API-initiated eviction:
  <https://kubernetes.io/docs/concepts/scheduling-eviction/api-eviction/>
- Kubernetes Deployment rollout and revision behavior:
  <https://kubernetes.io/docs/concepts/workloads/controllers/deployment/>
- RFC 8785 JSON Canonicalization Scheme:
  <https://www.rfc-editor.org/info/rfc8785>
- Kubernetes auditing:
  <https://kubernetes.io/docs/tasks/debug/debug-cluster/audit/>
- OpenShift audit log policy:
  <https://docs.redhat.com/en/documentation/openshift_container_platform/4.21/html/security_and_compliance/audit-log-policy-config>
- OpenShift Logging log forwarding:
  <https://docs.redhat.com/en/documentation/red_hat_openshift_logging/6.0/html/configuring_logging/configuring-log-forwarding>
- OpenShift Lightspeed overview:
  <https://docs.redhat.com/en/documentation/red_hat_openshift_lightspeed/1.0/html/about/ols-about-openshift-lightspeed>
- Kubernetes TTL-after-finished Jobs:
  <https://kubernetes.io/docs/concepts/workloads/controllers/ttlafterfinished/>
