// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to select the A2A protocol binding (HTTP+JSON, JSON-RPC, or gRPC) when
// creating an AIAgent from an A2A agent card using A2AClientOptions.PreferredBindings.

using A2A;
using A2A.Grpc;
using Microsoft.Agents.AI;

var a2aAgentHost = Environment.GetEnvironmentVariable("A2A_AGENT_HOST") ?? throw new InvalidOperationException("A2A_AGENT_HOST is not set.");

// Possible values: "HTTP+JSON" (default), "JSONRPC", or "GRPC".
var protocolBinding = Environment.GetEnvironmentVariable("A2A_PROTOCOL_BINDING") ?? ProtocolBindingNames.HttpJson;

// Register gRPC explicitly once during startup when using agent-card discovery.
// Direct construction of an A2AGrpcClient does not require registration.
if (string.Equals(protocolBinding, ProtocolBindingNames.Grpc, StringComparison.OrdinalIgnoreCase))
{
    // Register A2AGrpcClient with the SDK factory so AsAIAgent() can use a card's gRPC interface.
    // The optional A2A.Grpc package does not register this binding automatically.
    A2AGrpcClientRegistration.Register();
}

// Initialize an A2ACardResolver to get an A2A agent card.
A2ACardResolver agentCardResolver = new(new Uri(a2aAgentHost));

// Get the agent card
AgentCard agentCard = await agentCardResolver.GetAgentCardAsync();

// Use A2AClientOptions to explicitly select the configured protocol binding.
// This tells the A2A client factory to select only the configured interface when the agent card
// advertises multiple supported interfaces.
A2AClientOptions options = new()
{
    PreferredBindings = [protocolBinding]
};

// Create an instance of the AIAgent for an existing A2A agent, using the specified protocol binding.
AIAgent agent = agentCard.AsAIAgent(options: options);

// A gRPC client owns a channel; release it after the agent's final operation.
using var clientLifetime = agent.GetService<IA2AClient>() as IDisposable;

// Invoke the agent and output the text result.
AgentResponse response = await agent.RunAsync("Tell me a joke about a pirate.");
Console.WriteLine(response);
