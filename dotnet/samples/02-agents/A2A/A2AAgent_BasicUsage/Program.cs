// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to send a message to an existing A2A agent and receive its response using default settings.

using A2A;
using Microsoft.Agents.AI;

var a2aAgentHost = Environment.GetEnvironmentVariable("A2A_AGENT_HOST") ?? throw new InvalidOperationException("A2A_AGENT_HOST is not set.");

A2ACardResolver agentCardResolver = new(new Uri(a2aAgentHost));
AIAgent agent = await agentCardResolver.GetAIAgentAsync();

AgentResponse response = await agent.RunAsync("Tell me a joke about a pirate.");
Console.WriteLine(response);
