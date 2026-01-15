// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with an existing A2A agent.

using A2A;
using Microsoft.Agents.AI;

var a2aAgentHost = Environment.GetEnvironmentVariable("A2A_AGENT_HOST") ?? throw new InvalidOperationException("A2A_AGENT_HOST is not set.");

// Initialize an A2ACardResolver to get an A2A agent card.
A2ACardResolver agentCardResolver = new(new Uri(a2aAgentHost));

// Create an instance of the AIAgent for an existing A2A agent specified by the agent card.
AIAgent agent = await agentCardResolver.GetAIAgentAsync();

// Invoke the agent and output the text result.
AgentResponse response = await agent.RunAsync("Tell me a joke about a pirate.");
Console.WriteLine(response);
