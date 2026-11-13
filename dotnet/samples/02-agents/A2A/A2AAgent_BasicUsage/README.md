# A2A Agent Basic Usage

This sample shows how to send a single message to an existing A2A agent and receive its response using default settings.
It discovers the remote agent's card using `A2ACardResolver`, creates an `A2AAgent` through
`GetAIAgentAsync()`, and uses the standard `AIAgent.RunAsync()` method to send a prompt and print the response.

## Prerequisites

- .NET 10.0 SDK or later
- A running A2A agent server that exposes an agent card and an HTTP+JSON or JSON-RPC interface

If you do not have an A2A server, you can run the
[local echo agent](https://github.com/a2aproject/a2a-dotnet/blob/main/samples/AgentServer/README.md).

## Run the sample

From the repository root:

```powershell
cd dotnet\samples\02-agents\A2A\A2AAgent_BasicUsage
$env:A2A_AGENT_HOST="http://localhost:5000"  # Replace with your A2A server's base URL
dotnet run
```

The sample prints the remote agent's response to "Tell me a joke about a pirate."
The echo agent repeats the prompt instead of generating a joke.

For more advanced scenarios, see the other [A2A samples](../README.md).
