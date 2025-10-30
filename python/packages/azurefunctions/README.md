# Get Started with Microsoft Agent Framework Durable Functions

Please install this package via pip:

```bash
pip install agent-framework-azurefunctions --pre
```

## Durable Agent Extension

The durable agent extension lets you host Microsoft Agent Framework agents on Azure Durable Functions so they can persist state, replay conversation history, and recover from failures automatically.

### Basic Usage Example

See the durable functions integration sample in the repository to learn how to:

- Register agents with `AgentFunctionApp`
- Post messages using the generated `/api/agents/{agent_name}/run` endpoint
- Retrieve conversation history from `/api/agents/{agent_name}/{sessionId}`

For more details, review the Python [README](https://github.com/microsoft/agent-framework/tree/main/python/README.md) and the samples directory.
