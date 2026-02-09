# A2A Agent Examples

This folder contains examples demonstrating how to create and use agents with the A2A (Agent2Agent) protocol from the `agent_framework` package to communicate with remote A2A agents.

For more information about the A2A protocol specification, visit: https://a2a-protocol.org/latest/
## Examples

| File | Description |
|------|-------------|
| [`agent_with_a2a.py`](agent_with_a2a.py) | The simplest way to connect to and use a single A2A agent. Demonstrates agent discovery via agent cards and basic message exchange using the A2A protocol. |

## Environment Variables

Make sure to set the following environment variables before running the example:

### Required
- `A2A_AGENT_HOST`: URL of a single A2A agent (for simple sample, e.g., `http://localhost:5001/`)


## Quick Testing with .NET A2A Servers

For quick testing and demonstration, you can use the pre-built .NET A2A servers from this repository:

**Quick Testing Reference**: Use the .NET A2A Client Server sample at:
`..\agent-framework\dotnet\samples\A2AClientServer`

### Run Python A2A Sample
```powershell
# Simple A2A sample (single agent)
uv run python agent_with_a2a.py
```
