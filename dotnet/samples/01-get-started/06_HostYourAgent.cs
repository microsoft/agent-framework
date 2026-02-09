// Copyright (c) Microsoft. All rights reserved.

// Step 6: Host Your Agent
// Expose an agent over the A2A (Agent-to-Agent) protocol so other agents can call it.
// This sample shows how to consume an A2A agent's skills as function tools.
//
// For more on hosting, see: ../04-hosting/
// For docs: https://learn.microsoft.com/agent-framework/hosting/a2a

using A2A;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI.Chat;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
var a2aAgentHost = Environment.GetEnvironmentVariable("A2A_AGENT_HOST")
    ?? throw new InvalidOperationException("A2A_AGENT_HOST is not set.");

// <discover_a2a_agent>
// Discover and connect to a remote A2A agent
A2ACardResolver agentCardResolver = new(new Uri(a2aAgentHost));
AgentCard agentCard = await agentCardResolver.GetAgentCardAsync();
AIAgent a2aAgent = agentCard.AsAIAgent();
// </discover_a2a_agent>

// <use_a2a_agent>
// Create a local agent that can use the remote agent's skills as tools
AIAgent agent = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential())
    .GetChatClient(deploymentName)
    .AsAIAgent(
        instructions: "You are a helpful assistant that helps people with travel planning.",
        tools: [.. a2aAgent.AsAIFunctions(agentCard)]);

Console.WriteLine(await agent.RunAsync(
    "Plan a route from '1600 Amphitheatre Parkway, Mountain View, CA' to 'San Francisco International Airport'"));
// </use_a2a_agent>
