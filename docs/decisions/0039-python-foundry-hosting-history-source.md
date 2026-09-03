---
status: proposed
contact: eavanvalkenburg
date: 2026-09-01
deciders: eavanvalkenburg, moonbox3
---

# Select the conversation history source for Python Foundry hosting

## Context and Problem Statement

`ResponsesHostServer` currently replays the AgentServer response transcript into every agent run. An `AgentSession`
can also restore a downstream `service_session_id`, causing the model service to combine its stored conversation with
the replayed AgentServer transcript. This duplicates prior turns and compounds on each request.

Conversation data can exist in four places:

1. the AgentServer `ResponseProviderProtocol`;
2. an Agent Framework `HistoryProvider`;
3. `AgentSession.state`, persisted by a `SessionStore` and used by `InMemoryHistoryProvider`; and
4. the downstream model service when `store=True`.

The host must prevent duplicate model history without removing the regular agent storage choices.

## Decision Drivers

- Feed one canonical conversation transcript into each model call.
- Keep AgentServer response persistence independent from the model's history source.
- Preserve the normal agent choice between `HistoryProvider` and downstream service storage.
- Let applications choose storage that satisfies their compliance, residency, retention, deletion, encryption, and
  audit requirements.
- Retain AgentServer response history as the default hosting behavior.
- Make existing sessions containing a downstream service ID safe after upgrade.

## Considered Options

### Always use AgentServer response history

- Good: one simple default and parity with current .NET Foundry hosting.
- Good: the selected response provider controls the transcript used by the model.
- Bad: users cannot use normal agent history providers or service-side continuation.
- Bad: applications cannot choose a history backend that meets their data-governance requirements independently of
  AgentServer protocol storage.

### Clear the service ID but leave downstream storage enabled

- Good: avoids duplicated input.
- Bad: creates an untracked stored response or conversation on every model call.
- Bad: service-side storage incurs retention and cost but is never used for continuation.

### Add separate AgentServer, history-provider, service, and automatic modes

- Good: makes each possible authority explicit at the hosting layer.
- Bad: duplicates history-selection behavior already implemented by `Agent`.
- Bad: an automatic mode changes authority based on provider output, making retention and recovery unpredictable.

### Select AgentServer history or regular agent history

- Good: the host makes only the decision it owns: whether AgentServer history supersedes normal agent behavior.
- Good: regular agent mode preserves service storage, in-session history, and external history providers.
- Good: `ResponseProviderProtocol`, `HistoryProvider`, and `SessionStore` remain independent extension points.
- Good: applications can select the storage boundary and lifecycle required by their compliance policies.
- Neutral: AgentServer still manages protocol-level Responses persistence in regular agent mode, according to the outer
  request, but does not replay that transcript into the model.

## Decision Outcome

Add `history_source: Literal["agent_server", "agent"] = "agent_server"` to `ResponsesHostServer`.

With `history_source="agent_server"`:

- load-enabled `HistoryProvider` instances are rejected;
- regular agents must implement `RawAgent` and their clients must declare `STORES_BY_DEFAULT` so hosting can enforce
  runtime storage options;
- agent-level `conversation_id`, `previous_response_id`, and `conversation` defaults are rejected;
- the configured response provider transcript and current input are passed to the agent;
- clients advertising `STORES_BY_DEFAULT=True` receive a downstream `store=False` override;
- for other clients, an explicit agent-level `store` option is removed and no storage option is forwarded;
- a restored `service_session_id` is cleared before the run;
- a client that still returns a service ID fails the response and the contaminated session is not saved; and
- a transient `InMemoryHistoryProvider` supports intra-run function calls but is removed before session persistence.

With `history_source="agent"`:

- only current request input is passed by hosting;
- load-enabled history providers are allowed;
- downstream storage options are not changed; and
- normal `Agent` behavior selects service storage, an explicit history provider, or automatic in-session history;
- custom `SupportsAgentRun` implementations remain supported without receiving unsupported runtime chat options.

The AgentServer response provider continues to control Responses API persistence and retrieval in both modes, according
to the outer request. The session-store provider also remains independent. Consequently, regular agent mode can combine
`InMemoryHistoryProvider` with the default `FoundryAgentSessionStore` to persist model history in Foundry without using
the AgentServer response transcript as model input.

## Developer Experience

```python
# Default: AgentServer response history is model history.
ResponsesHostServer(agent)

# Regular Agent history and downstream storage behavior.
ResponsesHostServer(agent, history_source="agent")
```

Passing `store=None` or omitting `store` continues to select the environment's default AgentServer response provider.
It does not disable response persistence.

## Consequences

- Good: existing applications keep AgentServer history as their default.
- Good: applications can choose service-side, session-backed, or external history storage to meet data-governance
  requirements.
- Good: the API does not introduce a second history-selection state machine.
- Bad: default mode mutates the supplied `RawAgent` by installing a transient history provider.
- Neutral: a `ResponsesHostServer` owns its supplied agent instance; reusing that agent with another host or invoking it
  directly after server construction is unsupported.
- Bad: regular agent history and AgentServer response history may differ, which response-oriented evaluations must
  document.
- Neutral: switching an existing conversation between modes may require resetting its persisted session/history.

## More Information

- [Issue #7955](https://github.com/microsoft/agent-framework/issues/7955)
- [Closed Python PR #7957](https://github.com/microsoft/agent-framework/pull/7957)
- [Merged .NET PR #7525](https://github.com/microsoft/agent-framework/pull/7525)
- [Merged .NET follow-up PR #7572](https://github.com/microsoft/agent-framework/pull/7572)
