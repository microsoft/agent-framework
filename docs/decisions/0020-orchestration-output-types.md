---
status: proposed
contact: taochen
date: 2026-03-19
deciders:
consulted:
informed:
---

# Orchestration Run Output Types

> Note: this document only applies to Python. .Net is out of scope for now since it does not have the same orchestration patterns or output model.

## Context and Problem Statement

Python orchestrations (Concurrent, Sequential, Handoff, GroupChat, Magentic) currently all yield `list[Message]` — typically the full conversation history — as their final output via `ctx.yield_output(...)`. This creates several problems:

1. **The final output is semantically wrong.** Dumping the entire conversation into the output means consumers receive every intermediate message (user prompts, multi-round exchanges) rather than the orchestration's actual "answer." For example, a Sequential orchestration with three agents returns all messages from all three agents, even though only the last agent's response is the meaningful result.

2. **No clean distinction between intermediate and final outputs.** When `intermediate_outputs=True`, orchestrations surface `AgentResponse` / `AgentResponseUpdate` from individual agents as they run. The final output is also surfaced as an output event with the same `type='output'`. While callers could in theory distinguish them by inspecting the data type (e.g., intermediate outputs are `AgentResponse` while the final output is `list[Message]`), this is a fragile model — it couples control flow semantics to data representation and requires callers to know the internal output type of each orchestration pattern. More importantly, consumers like `WorkflowAgent` via `as_agent()` do not make this distinction: they convert all output events into the agent's response regardless of whether they are intermediate or final, producing a response that mixes progress updates with the actual answer.

3. **Inconsistent output types across orchestrations.** Most orchestrations yield `list[Message]`, but the content semantics vary wildly: Concurrent yields `[user_prompt, agent1_reply, agent2_reply, ...]`, Sequential yields the full chain, GroupChat/Magentic yield all rounds plus a completion message. Handoff yields `list[Message]` representing the full conversation at two different call sites. There is no unified contract for what a caller should expect.

## Orchestrations as Prebuilt Workflow Patterns

Orchestrations (Concurrent, Sequential, Handoff, GroupChat, Magentic) are not standalone features — they are prebuilt workflow patterns built on top of the workflow system APIs. They serve as both ready-to-use solutions and as reference implementations that demonstrate how to correctly compose agents using the workflow primitives (`Executor`, `WorkflowBuilder`, `yield_output`, `as_agent()`, etc.).

This dual role makes orchestrations critically important: the patterns they establish become the patterns that developers follow when building their own workflows. In practice, developers use the framework to build workflows that coordinate Foundry agents, and ultimately deploy those workflows as hosted agents on Azure AI Foundry. This path — from workflow definition to agent deployment — relies on a seamless integration between workflows and agents. If orchestrations model this integration poorly (e.g., producing outputs that don't compose cleanly with `as_agent()`), developers building custom workflows will inherit the same problems.

Getting the output contract right in orchestrations therefore has implications beyond the orchestrations themselves. It sets the standard for how any workflow should produce its final result, how that result flows through `as_agent()` to become an agent response, and how sub-workflows signal completion to their parent workflows.

### Usage Scenarios

Orchestrations are used in three primary ways, each with different output expectations:

#### 1. As Workflows (Basic Usage)

The most common scenario. The caller runs the workflow and iterates over events:

```python
workflow = SequentialBuilder(participants=[agent1, agent2, agent3]).build()
events = await workflow.run(message="Write a report")
for event in events:
    if event.type == "output":
        # Currently: event.data is either AgentResponse or list[Message] with ALL messages from ALL agents
        pass
```

When `intermediate_outputs=True`, the caller receives both intermediate agent outputs and the final output. While the data types differ (intermediate outputs are `AgentResponse` / `AgentResponseUpdate`, the final output is `list[Message]`), relying on type inspection to distinguish them is fragile and requires knowledge of each orchestration's internal output types. There is no explicit signal that says "the orchestration is done."

#### 2. As Agents via `as_agent()`

Orchestrations can be wrapped as agents using `workflow.as_agent()`. The `WorkflowAgent` processes workflow output events differently depending on the mode:

- **Non-streaming**: Collects all output events, then merges their data into a single `AgentResponse`. The full conversation dump from the orchestration's final output becomes `AgentResponse.messages` alongside any intermediate agent responses — producing a response that conflates progress with the actual answer.
- **Streaming**: Converts each output event into `AgentResponseUpdate` objects and yields them as they arrive. All updates — whether from intermediate agents or the final conversation dump — are yielded indiscriminately as streaming chunks.

In both modes, `WorkflowAgent` processes all output events without distinguishing intermediate from final. When `intermediate_outputs=True`, this means intermediate agent responses and the final conversation dump are merged together. Even when `intermediate_outputs=False`, the final output is still the full conversation rather than the meaningful answer.

#### 3. As Sub-Workflows

When an orchestration is embedded within a parent workflow, downstream executors receive output events from the orchestration. They must be able to:

- Process intermediate outputs (streaming chunks or agent responses) for real-time updates
- Identify when the orchestration has produced its final result
- Extract the meaningful answer from the final output

Currently, there is no mechanism to distinguish final from intermediate output events.

### Current State

| Orchestration | Final Output | What It Contains |
|---|---|---|
| **Concurrent** | `list[Message]` | User prompt + final assistant message from each agent |
| **Sequential** | `list[Message]` | Full conversation chain from all agents |
| **Handoff** | `list[Message]` | Full conversation history |
| **GroupChat** | `list[Message]` | All rounds + completion message |
| **Magentic** | `list[Message]` | Chat history + final answer |

## Decision Drivers

- The final output of an orchestration should be semantically meaningful — it should represent the orchestration's "answer," not a conversation dump.
- Consumers must be able to distinguish the orchestration's final output from intermediate progress updates without relying on data type inspection or positional heuristics.
- The output type should be `AgentResponse` so that orchestrations compose naturally with the agent system — particularly `as_agent()` and nested agent patterns.
- Different orchestration patterns have fundamentally different semantics for what constitutes the "answer," and the solution must accommodate this.

## Considered Options

### Option 1: Use data type as the discriminator

Introduce a wrapper type (e.g., `OrchestrationResult`) for the final output. Consumers check `isinstance(event.data, OrchestrationResult)` to identify the final output.

- Pro: No changes to the event system are needed.
- Con:
  - Introduces a new type that callers must know about and unwrap.
  - Conflates data representation with control flow semantics.

### Option 2: Add a new event type

Add a `"run_output"` event type alongside the existing `"output"` type.

- Pro: The distinction is clear and explicit.
- Con:
  - Adds a new concept to the workflow framework (`run_output` vs `output`).
  - `WorkflowAgent`, sub-workflow consumers, and event processing logic all need to handle two output event types.

### Option 3: Add `is_run_completed` flag to existing output event

Add an optional `is_run_completed: bool` parameter to the existing `yield_output()` method and `WorkflowEvent`:

```python
# WorkflowContext — existing API, new optional param
async def yield_output(self, output: W_OutT, *, is_run_completed: bool = False) -> None:
    ...

# WorkflowEvent.output factory — new optional param
@classmethod
def output(cls, executor_id: str, data: DataT, *, is_run_completed: bool = False) -> WorkflowEvent[DataT]:
    ...
```

- Pro:
  - Minimal, backward-compatible extension of the existing API.
  - The flag is on the event, not the data — separating control flow from representation.
  - Consumers can simply check `event.is_run_completed` without knowing about special types.
- Con:
  - Adds a new concept to the workflow framework, but it's a simple boolean flag rather than a whole new event type.

## Definition of a Run

A **run** represents a single invocation of the workflow — from receiving an initial request to the workflow returning to idle status. The `is_run_completed` flag on an output event signals that this output represents the final result of the current run.

Important considerations:

- A workflow going back to **idle** status after processing a request typically means a run has completed. All orchestration patterns emit an output event with `is_run_completed=True` when their run finishes. In some cases (e.g., Handoff), the completion event may carry no data — it serves purely as a signal that the run is done.
- A workflow entering **idle with pending requests** (e.g., waiting for human-in-the-loop approval) does **not** mean the run has completed. Rather, the run is suspended and will resume when the pending request is fulfilled. The `is_run_completed` flag should not be set on outputs emitted before or during a pending request pause.

## Decision Outcome

Chosen option: **Option 3 — Add `is_run_completed` flag to existing output event**, because it is the most minimal and backward-compatible approach. It does not introduce new types or event categories, and the semantic intent is clear: `is_run_completed=True` means "this output represents the final result of the current run."

### Per-Orchestration Output Changes

Each orchestration pattern changes what data it yields as the final output and sets `is_run_completed=True`:

| Orchestration | Current Final Output | New Final Output | Rationale |
|---|---|---|---|
| **Concurrent** | `list[Message]` (user prompt + one reply per agent) | `AgentResponse` containing all sub-agent response messages | The combined responses from all parallel agents represent the orchestration's answer. Messages are copied from each sub-agent's `AgentResponse`. |
| **Sequential** | `list[Message]` (full conversation chain) | `AgentResponse` from the last agent | The last agent in the chain produces the final answer. Earlier agents' outputs are intermediate steps. |
| **Handoff** | `list[Message]` (full conversation) | Empty output event with `is_run_completed=True` | Handoff emits agent responses as they become available (each agent's response is surfaced as an intermediate output). Since agents in handoff workflows are not sub-agents of a central orchestrator, all outputs are directly emitted — there is no separate "final answer." An empty completion event is emitted so consumers have a consistent signal that the run has finished. |
| **GroupChat** | `list[Message]` (all rounds + completion message) | `AgentResponse` containing the summary or completion message | The orchestrator's summary/end message is the meaningful result. Individual round messages are intermediate outputs visible when `intermediate_outputs=True`. |
| **Magentic** | `list[Message]` (chat history + final answer) | `AgentResponse` containing the synthesized final answer | The manager's synthesized final answer is the meaningful result. Individual agent work is intermediate. |

### Integration Points

#### WorkflowAgent (`as_agent()`)

When `WorkflowAgent` converts workflow events to an `AgentResponse`:

- Events with `is_run_completed=True` provide the `AgentResponse` that becomes the agent's response directly, with the name of the workflow as the author of the response.
- Events with `is_run_completed=False` are intermediate updates — they are included as streaming updates when `stream=True`, or merged into the response in non-streaming mode.
- When `intermediate_outputs=False` (recommended for agent usage), only the `is_run_completed=True` event is surfaced, producing a clean agent response.

> `intermediate_outputs` is always `True` for `handoff` since it has no single final answer — all agent responses are surfaced as intermediate outputs, and the completion event is empty.

#### Sub-Workflows

Downstream executors in a parent workflow can check `event.is_run_completed` to determine if the orchestration has produced its final answer:

- `is_run_completed == False` → intermediate progress (streaming chunk, individual agent response)
- `is_run_completed == True` → the orchestration is done; `event.data` contains the final `AgentResponse` (or empty for handoff) and the executor can proceed using the answer or assemble the received data as needed.

### Consequences

- Pro:
  - The final output is now semantically meaningful — consumers get the "answer" rather than a conversation dump.
  - The `is_run_completed` flag provides a clear, type-agnostic signal for consumers to identify completion.
  - `AgentResponse` as the output type means orchestrations compose naturally with the agent system.
  - The change is backward-compatible — existing code that doesn't check `is_run_completed` continues to work; it simply receives `AgentResponse` instead of `list[Message]`.
- Con: Workflow executors must remember to set `is_run_completed=True` on their final yield when appropriate.
- Neutral: The Handoff pattern emits an empty completion event (no data, just the flag) since it has no single "final answer." Consumers must handle the case where `is_run_completed=True` but `event.data` is empty.

## More Information

- See [ADR-0001: Agent Run Responses Design](0001-agent-run-response.md) for the foundational design of `AgentResponse`, primary vs secondary output, and the streaming model.
- The `intermediate_outputs` parameter on orchestration builders controls whether intermediate agent outputs are surfaced. When `False` (default), only outputs from designated output executors are visible. The `is_run_completed` flag adds a second dimension: even among visible outputs, only those marked `is_run_completed=True` represent the orchestration's final answer.
