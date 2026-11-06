---
status: proposed
contact: karthik-0306
date: 2026-11-06
deciders: eavanvalkenburg, westey-m
consulted: []
informed: []
---

# Cross-process ownership and result handoff for background agent tasks

## Context and Problem Statement

`BackgroundAgentsProvider` lets a parent agent start work on named background agents and collect the results on a later
turn. The Python and .NET implementations split every task into two parts:

- The **record** (`BackgroundTaskInfo`: id, agent name, description, status, result and error text) is serialized into
  session state, so it travels with the session to whichever process loads it next.
- The **runtime** (the running tasks, their cancellation, and the child agent sessions that `continue` needs) is
  process-local and never serialized. Python keeps it per session id inside the provider instance. .NET keeps it in a
  non-serialized provider state attached to the `AgentSession` instance, and a deserialized session starts with an empty
  runtime.

The provider refreshes the records whenever one of its tools reads them and when the host asks for the incomplete tasks.
Python also refreshes at the start of every turn, before the model sees the task list. A record that says `Running` and
has no local runtime entry is marked `Lost` and the new status is persisted. That is correct when the process that owned
the task is gone, and wrong when the owner is alive but is not serving this turn. The provider cannot tell the two
apart, because its only signal is its own process memory.

Hosts that run several replicas without session affinity hit this whenever the next turn is served by a different
replica. The behavior was reported in [#8760](https://github.com/microsoft/agent-framework/issues/8760) as seven
scenarios:

| # | Scenario | Effect |
|---|----------|--------|
| S1 | Turn N starts a task on process A and turn N+1 is served by process B | B marks the task `Lost`, the model restarts the work, and both copies run |
| S2 | The task finishes on A after B marked it `Lost` | The result is never recorded anywhere another process can read it |
| S3 | A run ends while tasks are still live (pending approval, call or time limits, provider error, user stop) | The next turn becomes S1 |
| S4 | A finished task is continued on another process | The child session exists only on the owner, so the call fails |
| S5 | Process restart or rolling deploy | `Lost` is correct, but looks the same as S1 |
| S6 | The host releases a session on a process that does not own its tasks | Nothing is cancelled and the tasks keep running for a conversation that no longer exists |
| S7 | `wait` or `get_all_tasks` on another process | The remote task cannot be seen or waited on |

The .NET provider has the same record and runtime split, so the same scenarios apply to it.

The maintainers split the work into two tracks:

- **Track 1** fixes the existing single-process semantics. In Python
  ([#9387](https://github.com/microsoft/agent-framework/pull/9387), merged) finished tasks are kept until they are
  cleared or the session is released, and each start or continuation gets a persisted `execution_id`. The related
  release-timeout defect [#9231](https://github.com/microsoft/agent-framework/issues/9231) was also addressed by it.
  .NET still removes a finished task from its in-flight map in `FinalizeTask` and has no execution identity yet.
- **Track 2**, the subject of this ADR, is the cross-process contract. The first prototype
  ([#9040](https://github.com/microsoft/agent-framework/pull/9040)) was closed with the direction to "define the
  cross-process ownership and result-handoff contract in a shared .NET/Python ADR before implementation".

Terminology: a **task** in this document is a `BackgroundAgentsProvider` task. It is unrelated to a protocol task such
as an A2A `task_id` (see [ADR-0033](0033-python-agent-session-identity.md)).

This ADR decides the semantics that both languages must implement. It does not add any code or public API.

## Decision Drivers

- Never mark a task `Lost` while its owner is alive. Do mark it `Lost` when the owner is gone (S1, S5).
- Deliver a finished task's result to whichever process serves the next turn (S2, S7).
- Let a release or cancel request reach the process that owns the work (S6).
- Give .NET and Python the same observable behavior. The contract must not expose runtime types such as `Task`,
  `asyncio.Task`, or `AgentSession`.
- Keep today's behavior as the default. Single-process hosts need no new infrastructure and see no change.
- Stay storage-agnostic and consistent with how sessions are already keyed and stored
  ([ADR-0045](0045-shared-agent-session-store.md), [ADR-0038](0038-python-session-store-serialization.md)).
- Be correct under stale or duplicate writers, partial failures, store outages, and shutdown. The review of the first
  prototype showed that these cases decide whether a design is usable.
- Bound memory, storage, and release time. Nothing may be retained forever, and a release must return within its
  timeout.
- Keep the new public surface small and experimental, and build on the Track 1 execution identity.

## Considered Options

1. Keep the current behavior and document the need for session affinity.
2. Add a liveness-only lease.
3. Store ownership and outcomes through the existing session store.
4. Define a shared coordination contract with per-language bindings and an in-memory default.
5. Run background tasks on a durable execution backend.

## Decision Outcome

Chosen option: **Define a shared coordination contract with per-language bindings and an in-memory default**, because it
covers ownership, result handoff, and cancellation (S1 to S3 and S5 to S7; S4, cross-process continue, is not supported
and fails with a clear message, see below) without a new hosting model, using primitives that both languages can
implement identically and that common stores can provide. The remaining options are rejected or deferred in
[Pros and Cons of the Options](#pros-and-cons-of-the-options).

The status stays `proposed`. The rules below are the proposed decision; the [Open Questions](#open-questions) list the
points on which the deciders may want a different answer.

### Identity

Every coordination entry is addressed by `(sessionKey, taskId, executionId)`.

- `sessionKey` is an opaque string that identifies the session in the shared store. It defaults to the session id. Hosts
  that partition sessions (tenant, user, and so on) provide a scope that the provider combines with the session id, so
  two sessions that share an id in different partitions never share entries. How the scope reaches the provider is Open
  Question 1.
- `taskId` is the integer the tools already use.
- `executionId` is an opaque, globally unique value created whenever an execution starts: the initial run and every
  continuation. It is persisted in the task record. Python already does this; .NET adds it.

Execution ids are never reused, so entries that belong to different executions never collide. This removes the need to
delete the previous outcome when a task is continued, and it makes a stale writer harmless because it can only address
its own execution.

### Entries

| Entry | Written by | Fields | Notes |
|-------|-----------|--------|-------|
| Claim | The owner | key, `ownerId`, expiry | `ownerId` is an opaque instance identifier for diagnostics and routing. The store computes the expiry from a TTL. |
| Outcome | The owner | key, terminal status (`Completed` or `Failed`), result text, error text | Write-once. |
| Cancel request | Any process | key | Idempotent. |

### Operations and invariants

In the table, `key` is the full address `(sessionKey, taskId, executionId)`.

| Operation | Semantics |
|-----------|-----------|
| `Claim(key, ownerId, ttl)` | Atomic create-if-absent for one execution. Fails when the store cannot guarantee atomicity. |
| `Renew(key, ttl)` | Extends the claim. Also tells the owner whether a cancel request exists for this execution. |
| `GetClaim(key)` | Returns whether a claim exists and is still live, and its `ownerId`. |
| `PublishOutcome(key, outcome)` | Write-once. The first write wins and later writes are ignored without error. |
| `GetOutcome(key)` | Returns the outcome, or nothing. |
| `RequestCancel(key)` | Records that the execution should stop. |
| `Remove(key)` | Deletes the claim and outcome of one execution. |

Invariants that every binding must preserve:

1. Expiry is decided by the store, using its own TTL or server clock. Processes never compare timestamps from their own
   clocks.
2. Every entry has a bounded lifetime, so abandoned entries disappear without a cleanup job.
3. Operations are idempotent, so retries are safe.
4. A failed or timed-out operation is reported as a failure. It is never reported as "not found" or as an empty result,
   because the reader rules treat the two differently.

Final names and signatures are chosen in the implementation pull requests so that each language stays idiomatic. The
working name of the prototype was `BackgroundTaskRuntimeStore`.

### Deciding the status of a record

This applies to a `Running` record, or a `Lost` one, whose execution this process does not track. A `Lost` record only
goes through step 1, so it can never return to `Running`.

1. Call `GetOutcome`. If an outcome exists, the record takes its status and text. This also applies to a record that
   currently says `Lost`: `Lost` is a presumption, and an outcome for the same execution supersedes it.
2. Otherwise, for a `Running` record, call `GetClaim`. If the claim is live, the record stays `Running` and is
   reported as running on another instance.
3. Otherwise (the claim is missing or expired) call `GetOutcome` again. If an outcome now exists, apply it as in
   step 1. If not, mark the record `Lost`. The second read covers an owner that publishes between the first read and
   the claim expiry.
4. If any store call fails, change nothing, persist nothing, and report the status as temporarily unavailable. A store
   outage never produces `Lost`. The next refresh tries again.

The refresh persists the record only when its status changes, so it does not rewrite `Lost` on every turn.

A record whose execution this process does track follows today's rules. A record without an execution id, for example
one that was persisted before this change, cannot be looked up in the store and also follows today's rules.

### Owner rules

- **Start.** Create the execution id and call `Claim`. Start the agent run only if the claim is granted. If the claim
  fails, no run starts, nothing is persisted, and the tool returns an error to the model. A start that races with a
  release is either fully registered before the release takes its snapshot, or it is rejected and its claim is removed.
- **While running.** Call `Renew` at an interval well below the TTL (one third is suggested). If `Renew` reports a
  cancel request, cancel the local execution. Transient renewal failures are retried and the execution keeps running.
- **Finish.** Call `PublishOutcome` with bounded retries and backoff. Publishing does not require a live claim.
- **Lapsed ownership.** If the claim expires while the execution is still running (a long store outage or a paused
  process), the execution continues and still publishes. Another process may have marked the record `Lost` and the model
  may have restarted the work; the outcome supersedes `Lost` when it is read. This is the same exposure as today, but it
  now needs an outage longer than the TTL.
- **Continue.** Only the process that retains the finished execution and its child session can continue it. A
  continuation gets a new execution id and a new claim. The earlier outcome stays readable until it is removed or
  expires.
- **Clear.** Remove the local state and call `Remove` for the record's execution. Other executions of the same task id
  are not touched.
- **Release.** (1) Close the local runtime to new starts. (2) Call `RequestCancel` for every execution that the session
  record lists as `Running`, including executions this process does not own. (3) Cancel and await the local executions
  within the release timeout. (4) Await pending outcome publications within the same timeout, before dropping the
  runtime. (5) Call `Remove` for the entries this process owns. Cancel requests are left to expire so that remote owners
  can still observe them. Store failures during release are logged and do not fail the release, and release stays
  bounded by its timeout, as established by the fix for #9231.

### Cancellation

Cancel requests are addressed to one execution and are derived from the session record, not from a session-wide flag.
A session id can therefore be reused after a release without cancelling the new work. An execution that the releasing
process's copy of the record does not list (for example, one started after that copy was loaded) is not reached.
Open Question 2 covers an additional session-level marker.

### Continue across processes

Version 1 does not support continuing a task on a process that does not own its child session. The call fails with a
clear message that names the cause, and the outcome stays readable everywhere. Two later extensions fit the same
contract without changes: the host routes the call to the process named by `ownerId`, or the owner stores the child
session when the agent's session is serializable.

### Visibility to the model

No new persisted status is added. `BackgroundTaskStatus` is public in both languages, and the extra state is a property
of the observer, not of the task. The tools mark a task that is live but not local as "running on another instance",
and a task whose status could not be read (reader rule 4) as "status temporarily unavailable". `wait` polls the store
for such tasks at a bounded interval, up to its normal wait timeout.

### Default, opt-in, and formats

The provider accepts an optional coordination store. The default implementation keeps everything in process, so a claim
is never visible to another process and every execution is local. It reproduces today's behavior and today's tests.
The new types are experimental in both languages, and each language exports the store type and its default from the
package's public entry point, so that hosts can supply their own implementation.

Record JSON already differs between the languages (for example `agentName` and `resultText` in .NET, `agent_name` and
`result_text` in Python). Sessions are not shared across languages today, so record compatibility is not required. Each
binding encodes coordination entries in the idiom of its store. A store that is shared by a Python service and a .NET
service is not a goal of this ADR.

### Alignment items for the implementations

- Release semantics differ today. .NET rewrites leftover `Running` records to `Failed` with a release message. Python
  leaves the persisted records unchanged. The implementations must agree on what release does to records of remote
  executions. The suggestion is to keep a published outcome if one exists and otherwise record the cancellation.
- The .NET Track 1 parity change (retention of finished tasks and the persisted execution id) must land first, because
  the contract relies on both.

### Consequences

- Good, because six scenarios are resolved (S1 to S3 and S5 to S7), and S4, cross-process continue, fails with a clear
  message instead of an unrelated one.
- Good, because the contract is built from small primitives (atomic create, expiry, write-once) that common key-value
  stores provide natively, so a reference binding such as Redis stays small.
- Good, because keying by execution id removes three hard cases of the first prototype: stale-outcome cleanup, stale
  publishers, and sticky session-wide cancellation.
- Good, because the default is unchanged and the new surface is experimental.
- Bad, because cross-process benefits need a shared store that the host must run and configure.
- Bad, because starting or continuing a task requires a successful claim, so no new background work starts while the
  store is unavailable. This is deliberate: work that cannot be tracked would be marked `Lost` by other processes while
  it runs.
- Bad, because outcomes carry result text. The store must be protected like session state, and the session key must
  include any tenant or user scope so that one session cannot read another's entries.
- Bad, because renewals and polling add store traffic and latency.
- Bad, because a dead owner is only detected when its claim expires. Until then (up to one TTL after the last renewal)
  other processes report the task as running on another instance, so the TTL trades detection speed against tolerance
  for slow renewals.
- Bad, because two implementations must stay in sync, which the shared conformance tests below are meant to enforce.
- Bad, because an outage longer than the TTL can still produce duplicate work if the model restarts a task that was
  presumed `Lost`.

## Validation

- A behavior matrix of conformance tests, written once as a table and implemented in both languages. It runs against the
  in-memory default and against every shipped store binding. It covers each invariant and each reader and owner rule
  above.
- One test per scenario S1 to S7 that uses two provider instances over one shared store to simulate two processes.
- Fault injection: store errors during every operation, a failed initial claim, a publish that fails and then succeeds,
  a stale publisher, a claim that expires before a late outcome, a release that races with a start, and a release with
  pending publications. Each test must fail on an implementation that breaks the rule it covers.
- The existing single-process tests of both providers pass unchanged against the default store.
- Documentation and the harness samples describe the opt-in, the TTL, and the limitations above.

## Pros and Cons of the Options

### 1. Keep the current behavior and document the need for session affinity

Track 1 already fixes the single-process defects. This option adds documentation only.

- Good, because it needs no new API or infrastructure.
- Neutral, because affinity works for hosts that can pin sessions and never restart.
- Bad, because restarts and rolling deploys still produce false `Lost` (S5), and some hosts cannot pin reliably.
- Bad, because a delete that lands on another process cannot cancel anything (S6).
- Bad, because the result is paid work that is duplicated or lost, which documentation cannot prevent.

### 2. Add a liveness-only lease

An owner records a lease and renews it. Refresh asks the store before marking `Lost`.

- Good, because it is the smallest seam and removes false `Lost` while the owner is healthy (S1).
- Neutral, because it could later grow into option 4.
- Bad, because the result still never reaches another process (S2) and a remote task cannot be cancelled (S6).
- Bad, because it would change an experimental API twice, first for liveness and then again for results.

### 3. Store ownership and outcomes through the existing session store

Keep coordination entries as extra items in the store that already holds sessions.

- Good, because no new abstraction is introduced and the existing session backends (such as file, Azure Blob, and the
  Foundry state store) are reused.
- Neutral, because the key conventions of [ADR-0045](0045-shared-agent-session-store.md) and
  [ADR-0038](0038-python-session-store-serialization.md) could be reused.
- Bad, because both session store contracts are whole-session get, save or set, and delete. Neither offers a conditional
  write, an expiry, or change notification, so an atomic claim, a write-once outcome, and lease expiry cannot be built
  on them.
- Bad, because a background owner that edits the session record races with the live turn on another process and can
  overwrite conversation state.

### 4. Define a shared coordination contract with per-language bindings and an in-memory default (chosen)

See the Decision Outcome.

- Good, because it covers S1 to S3 and S5 to S7 (S4, cross-process continue, is a clear error) and is expressed without
  runtime types.
- Good, because the in-memory default preserves today's behavior and keeps the feature opt-in.
- Good, because execution ids from Track 1 make claims, outcomes, and cancel requests unambiguous.
- Neutral, because it adds an experimental public type in each language.
- Bad, because hosts need a shared store, and the two implementations need ongoing parity work.

### 5. Run background tasks on a durable execution backend

Use a durable orchestration engine (for example the Durable Task integration `agent-framework-durabletask`, which
[ADR-0039](0039-durable-azure-functions-extraction.md) moves to a separate repository) to run each task.

- Good, because tasks survive process death and can be resumed.
- Neutral, because a durable engine could later sit behind option 4 as a binding.
- Bad, because it is a different hosting model and much heavier than a liveness claim.
- Bad, because `BackgroundAgentsProvider` runs child agents inside the host process, not on a durable engine, so the
  provider's own `Lost` decision for in-process tasks remains.

## Open Questions

1. **Session scope.** What is the best way for a host to supply the scope that is combined with the session id?
   Candidates are a provider option holding a prefix or a key factory, or reuse of the partitions of
   `AgentSessionStoreKey` ([ADR-0045](0045-shared-agent-session-store.md)) in .NET.
2. **Cancellation reach.** Is per-execution cancellation derived from the record enough, or should release also write a
   session-level marker with an epoch so that executions the releasing process does not know about are cancelled too?
3. **Superseding `Lost`.** This ADR proposes that a published outcome supersedes `Lost` for the same execution. Should
   `Lost` stay terminal instead? That is simpler but loses results after a long outage.
4. **Placement.** Should the contract live in the core packages next to the provider in both languages, and where should
   a reference store such as Redis live?
5. **Defaults.** The default claim TTL, the renewal interval, the outcome retention, and the polling interval for
   `wait`.
6. **Continue.** Should a later version store the child session, route to the owner, or leave cross-process continue
   unsupported?
7. **Deciders.** Which .NET maintainers sign off, and should a .NET co-author review the .NET binding?

## More Information

Related decisions and issues:

- [ADR-0045](0045-shared-agent-session-store.md) and [ADR-0038](0038-python-session-store-serialization.md) define the
  session stores and keys that this contract deliberately does not extend.
- [ADR-0033](0033-python-agent-session-identity.md) separates session, task, and continuation identity for protocol
  tasks. The execution id here is provider-internal and does not replace any of them.
- [ADR-0041](0041-foundry-hosting-resilient-long-running-agents.md) covers platform recovery of a hosted run. It is a
  different layer from child tasks started by a parent agent.
- [#9531](https://github.com/microsoft/agent-framework/issues/9531) reports process-local state in the .NET
  `MessageInjectingChatClient`. It needs a pending-message source, not ownership, so it is related but outside this
  contract.

The closed prototype showed which cases a design must settle. Each reported finding maps to a rule in this ADR (finding
titles are paraphrased from the pull request review):

| Finding on the prototype | Where it is settled |
|--------------------------|---------------------|
| Use per-task cancellation generations | Cancel requests are addressed to one execution |
| Do not mark tasks `Lost` during store outages | Reader rule 4 |
| Prevent release races during task acquisition | Start rule on racing with release |
| Fence stale publishers with attempt generations | Unique execution ids and write-once outcomes |
| Re-export the pluggable store protocol | Default, opt-in, and formats: the store type is exported from the package |
| Use shared-store TTL or server time for expiry | Invariant 1 |
| Require atomic lease acquisition and stale-outcome removal | Atomic `Claim`; entries are keyed by execution, so nothing stale exists |
| Require atomic outcome publication and lease removal | Readers check the outcome before the claim, so no atomic pair is needed |
| Handle publication failures with retries or durable handoff | Finish rule: bounded retries; release awaits pending publications |
| Avoid repeated `Lost` writes during refresh | The refresh persists only on change |
| Outcomes are never removed | Invariant 2, `Clear`, and `Release` |
| A failed initial lease still starts the task | Start rule: no claim, no run |
| Release does not drain pending publications | Release step 4 |

Sequencing after acceptance, each as a separate pull request:

1. .NET Track 1 parity: retention of finished tasks and a persisted execution id.
2. The Python implementation with the conformance suite.
3. The .NET implementation with the same suite.
4. A reference store binding, if the deciders want one in this repository.
