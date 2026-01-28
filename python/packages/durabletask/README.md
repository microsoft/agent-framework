# Get Started with Microsoft Agent Framework Durable Task

[![PyPI](https://img.shields.io/pypi/v/agent-framework-durabletask)](https://pypi.org/project/agent-framework-durabletask/)

Please install this package via pip:

```bash
pip install agent-framework-durabletask --pre
```

## Durable Task Integration

The durable task integration lets you host Microsoft Agent Framework agents using the [Durable Task](https://github.com/microsoft/durabletask-python) framework so they can persist state, replay conversation history, and recover from failures automatically.

### Basic Usage Example

```python
from durabletask import TaskHubGrpcWorker
from agent_framework.azure import DurableAIAgentWorker

# Create the worker
with TaskHubGrpcWorker(...) as worker:
    
    # Register the agent worker wrapper
    agent_worker = DurableAIAgentWorker(worker)
    
    # Register the agent
    agent_worker.add_agent(my_agent)
```

For more details, review the Python [README](https://github.com/microsoft/agent-framework/tree/main/python/README.md) and the samples directory.
