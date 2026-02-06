# Agent Framework Orchestrations

Orchestration patterns for Microsoft Agent Framework. This package provides high-level builders for common multi-agent workflow patterns.

## Installation

```bash
pip install agent-framework-orchestrations
```

## Orchestration Patterns

### SequentialBuilder

Chain agents/executors in sequence, passing conversation context along:

```python
from agent_framework_orchestrations import SequentialBuilder

workflow = SequentialBuilder().participants([agent1, agent2, agent3]).build()
```

### ConcurrentBuilder

Fan-out to multiple agents in parallel, then aggregate results:

```python
from agent_framework_orchestrations import ConcurrentBuilder

workflow = ConcurrentBuilder().participants([agent1, agent2, agent3]).build()
```

### HandoffBuilder

Decentralized agent routing where agents decide handoff targets:

```python
from agent_framework_orchestrations import HandoffBuilder

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
from agent_framework_orchestrations import GroupChatBuilder

workflow = (
    GroupChatBuilder()
    .with_orchestrator(selection_func=my_selector)
    .participants([agent1, agent2])
    .build()
)
```

### MagenticBuilder

Sophisticated multi-agent orchestration using the Magentic One pattern:

```python
from agent_framework_orchestrations import MagenticBuilder

workflow = (
    MagenticBuilder()
    .participants([researcher, writer, reviewer])
    .with_manager(agent=manager_agent)
    .build()
)
```

## Usage with agent_framework

You can also import orchestrations through the main agent_framework package:

```python
from agent_framework.orchestrations import SequentialBuilder, ConcurrentBuilder
```

## Documentation

For more information, see the [Agent Framework documentation](https://aka.ms/agent-framework).
