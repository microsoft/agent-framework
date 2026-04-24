// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to select the A2A protocol binding (HTTP+JSON vs JSON-RPC) when
// creating an AIAgent from an A2A agent card using A2AClientOptions.PreferredBindings.

using A2A;
using Microsoft.Agents.AI;

var a2aAgentHost = Environment.GetEnvironmentVariable("A2A_AGENT_HOST") ?? throw new InvalidOperationException("A2A_AGENT_HOST is not set.");

// Initialize an A2ACardResolver to get an A2A agent card.
A2ACardResolver agentCardResolver = new(new Uri(a2aAgentHost));

// Get the agent card
AgentCard agentCard = await agentCardResolver.GetAgentCardAsync();

// Use A2AClientOptions to explicitly select the HTTP+JSON protocol binding.
// This tells the A2A client factory to prefer the HTTP+JSON interface when the agent card
// advertises multiple supported interfaces.
A2AClientOptions options = new()
{
    PreferredBindings = [ProtocolBindingNames.HttpJson]
};

// To prefer JSON-RPC instead, use:
// A2AClientOptions options = new()
// {
//     PreferredBindings = [ProtocolBindingNames.JsonRpc]
// };

// Create an instance of the AIAgent for an existing A2A agent, using the specified protocol binding.
AIAgent agent = agentCard.AsAIAgent(options: options);

// Invoke the agent and output the text result.
AgentResponse response = await agent.RunAsync("Tell me a joke about a pirate.");
Console.WriteLine(response);
