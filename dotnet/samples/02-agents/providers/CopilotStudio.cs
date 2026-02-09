// Copyright (c) Microsoft. All rights reserved.

// Provider: Copilot Studio
// Create an agent backed by a Microsoft Copilot Studio agent.
// Note: Copilot Studio agents are accessed via the A2A protocol.
//
// For docs: https://learn.microsoft.com/agent-framework/agents/providers

using A2A;
using Microsoft.Agents.AI;

var a2aAgentHost = Environment.GetEnvironmentVariable("A2A_AGENT_HOST")
    ?? throw new InvalidOperationException("A2A_AGENT_HOST is not set.");

// <copilot_studio>
// Connect to a Copilot Studio agent via its A2A endpoint
A2ACardResolver agentCardResolver = new(new Uri(a2aAgentHost));
AIAgent agent = await agentCardResolver.GetAIAgentAsync();
// </copilot_studio>

Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate."));
