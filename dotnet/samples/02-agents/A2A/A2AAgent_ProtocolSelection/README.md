# A2A Agent Protocol Selection

This sample demonstrates how to select the A2A protocol binding when creating an `AIAgent` from an A2A agent card.

A2A agents can expose multiple interfaces with different protocol bindings (e.g., HTTP+JSON, JSON-RPC). By default, `AsAIAgent()` prefers HTTP+JSON with JSON-RPC as a fallback. This sample shows how to use `A2AClientOptions.PreferredBindings` to explicitly control which protocol binding is used.

The sample:

- Connects to an A2A agent server specified in the `A2A_AGENT_HOST` environment variable
- Configures `A2AClientOptions` to prefer the HTTP+JSON protocol binding
- Creates an `AIAgent` from the resolved agent card using the specified binding
- Sends a message to the agent and displays the response

## Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10.0 SDK or later
- An A2A agent server running and accessible via HTTP

**Note**: These samples need to be run against a valid A2A server. If no A2A server is available, they can be run against the echo-agent that can be spun up locally by following the guidelines at: https://github.com/a2aproject/a2a-dotnet/blob/main/samples/AgentServer/README.md

Set the following environment variable:

```powershell
$env:A2A_AGENT_HOST="http://localhost:5000"  # Replace with your A2A agent server host
```
