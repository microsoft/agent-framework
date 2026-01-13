# Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10 SDK or later
- Access to the A2A agent host service

**Note**: These samples need to be run against a valid A2A server. If no A2A server is available, they can be run against the echo-agent that can be spun up locally by following the guidelines at: https://github.com/a2aproject/a2a-dotnet/blob/main/samples/AgentServer/README.md

Set the following environment variables:

```powershell
$env:A2A_AGENT_HOST="https://your-a2a-agent-host" # Replace with your A2A agent host endpoint
```

## Advanced scenario

This method can be used to create AI agents for A2A agents whose hosts support the [Direct Configuration / Private Discovery](https://github.com/a2aproject/A2A/blob/main/docs/topics/agent-discovery.md#3-direct-configuration--private-discovery) discovery mechanism.

```csharp
using A2A;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.A2A;

// Create an A2AClient pointing to your `echo` A2A agent endpoint
A2AClient a2aClient = new(new Uri("https://your-a2a-agent-host/echo"));

// Create an AIAgent from the A2AClient
AIAgent agent = a2aClient.GetAIAgent();

// Run the agent
AgentRunResponse response = await agent.RunAsync("Tell me a joke about a pirate.");
Console.WriteLine(response);
```