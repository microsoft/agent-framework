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
).build()
```

### MagenticBuilder

Sophisticated multi-agent orchestration using the Magentic One pattern:

```python
from agent_framework.orchestrations import MagenticBuilder

workflow = MagenticBuilder(
    participants=[researcher, writer, reviewer],
    manager_agent=manager_agent,
).build()
```

## Documentation

For more information, see the [Agent Framework documentation](https://aka.ms/agent-framework).
