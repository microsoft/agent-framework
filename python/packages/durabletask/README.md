# Get Started with Microsoft Agent Framework Durable Task

[![PyPI](https://img.shields.io/pypi/v/agent-framework-durabletask)](https://pypi.org/project/agent-framework-durabletask/)

Please install this package via pip:

```bash
pip install agent-framework-durabletask --pre
```

## Durable Task Integration

The durable task integration lets you host Microsoft Agent Framework agents using the [Durable Task](https://github.com/microsoft/durabletask-python) framework so they can persist state, replay conversation history, and recover from failures automatically.

### Basic Usage Example

See the durable task integration sample in the repository to learn how to:

```python
from durabletask import TaskHubGrpcWorker
from agent_framework_durabletask import AgentWorker

# Wrap the durabletask worker
durable_worker = TaskHubGrpcWorker(host_address="localhost:4001")
worker = AgentWorker(durable_worker)

# Register your agent
worker.add_agent(agent)
```

- Register agents with `AgentWorker`
- Run agents using `AgentClient` or `AgentOrchestrator`

For more details, review the Python [README](https://github.com/microsoft/agent-framework/tree/main/python/README.md) and the samples directory.
