# Agent Framework Orchestrations

Orchestration patterns for Microsoft Agent Framework. This package provides high-level builders for common multi-agent workflow patterns.

## Installation

```bash
pip install agent-framework-orchestrations --pre
```

## Orchestration Patterns

### SequentialBuilder

Chain agents/executors in sequence, passing conversation context along:

```python
from agent_framework.orchestrations import SequentialBuilder

workflow = SequentialBuilder(participants=[agent1, agent2, agent3]).build()

# Preserve agent1 and agent2 as visible progress, while the default builder output remains Workflow Output.
workflow = SequentialBuilder(
    participants=[agent1, agent2, agent3],
    intermediate_output_from=[agent1, agent2],
).build()
```

### ConcurrentBuilder

Fan-out to multiple agents in parallel, then aggregate results:

```python
from agent_framework.orchestrations import ConcurrentBuilder

workflow = ConcurrentBuilder(participants=[agent1, agent2, agent3]).build()
```

### HandoffBuilder

Decentralized agent routing where agents decide handoff targets:

```python
from agent_framework.orchestrations import HandoffBuilder

workflow = (
    HandoffBuilder()
    .participants([triage, billing, support])
    .with_start_agent(triage)
    .build()
)
```

### GroupChatBuilder

Orchestrator-directed multi-agent conversations:

```python
from agent_framework.orchestrations import GroupChatBuilder

workflow = GroupChatBuilder(
    participants=[agent1, agent2],
    selection_func=my_selector,
    intermediate_output_from=[agent1, agent2],
).build()
```

### MagenticBuilder

Sophisticated multi-agent orchestration using the Magentic One pattern:

```python
from agent_framework.orchestrations import MagenticBuilder

workflow = MagenticBuilder(
    participants=[researcher, writer, reviewer],
    manager_agent=manager_agent,
    intermediate_output_from=[researcher, writer, reviewer],
).build()
```

## Output Selection

Orchestration builders expose Workflow Output selection using participant names. The core rule is that `output_from`
is an allow-list for Workflow Output, not a routing rule for every other participant output. Unselected participant
payloads are hidden unless `intermediate_output_from` explicitly selects them as Intermediate Output.

- `output_from` designates participant emissions as Workflow Output (`type='output'` events).
- `intermediate_output_from` designates participant emissions as Intermediate Output (`type='intermediate'` events).

If neither list is provided, each builder uses its documented default Workflow Output contract. Sequential emits the
last participant; Concurrent, GroupChat, and Magentic emit their aggregator/orchestrator/manager output; Handoff emits
participants.

| Selection | Workflow Output | Intermediate Output | Hidden payloads |
| --- | --- | --- | --- |
| Omit both selections | Builder default Workflow Output contract | None | Builder-specific non-output participant payloads |
| `output_from="all"` | Every output-capable participant | None | None |
| `output_from=[writer]` | Only `writer` | None | All other participant payloads |
| `output_from=[writer], intermediate_output_from="all_other"` | Only `writer` | Every output-capable participant not selected by `output_from` | None |
| `intermediate_output_from="all_other"` | None, except builder-internal default output executors where applicable | Every output-capable participant | Builder-internal plumbing payloads |
| `output_from=[], intermediate_output_from="all_other"` | None, except builder-internal default output executors where applicable | Every output-capable participant | Builder-internal plumbing payloads |
| `output_from=[writer], intermediate_output_from=[researcher, reviewer]` | Only `writer` | `researcher` and `reviewer` | Any other participant payloads |

Invalid selections fail at construction or build time:

| Invalid selection | Why it fails |
| --- | --- |
| `output_from="all_other"` | `"all_other"` is only valid for `intermediate_output_from` |
| `intermediate_output_from="all"` | `"all"` is only valid for `output_from` |
| The same participant in both selections | One payload cannot be both Workflow Output and Intermediate Output |
| Duplicate participant selections | Duplicates are treated as configuration errors |
| Unknown participant selections | Typos and missing participants are rejected |
| `output_from=[], intermediate_output_from=[]` | Both explicit selections are empty |

When an orchestration is wrapped with `workflow.as_agent()`, Workflow Output becomes normal response text. Intermediate
Output becomes `text_reasoning` content so callers can inspect progress without changing `.text` behavior.

## Documentation

For more information, see the [Agent Framework documentation](https://aka.ms/agent-framework).
