// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to expose an A2A agent as a function tool that another agent can call.

using A2A;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;

var endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
var model = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4-mini";
var a2aAgentHost = Environment.GetEnvironmentVariable("A2A_AGENT_HOST") ?? throw new InvalidOperationException("A2A_AGENT_HOST is not set.");

// Initialize an A2ACardResolver to get an A2A agent card.
A2ACardResolver agentCardResolver = new(new Uri(a2aAgentHost));

// Get the agent card
AgentCard agentCard = await agentCardResolver.GetAgentCardAsync();

// Create an instance of the AIAgent for an existing A2A agent specified by the agent card.
AIAgent a2aAgent = agentCard.AsAIAgent();

// Create the main agent, and provide the A2A agent as a function tool.
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIAgent agent = new AIProjectClient(new Uri(endpoint), new DefaultAzureCredential())
    .AsAIAgent(
        model: model,
        instructions: "You are a helpful assistant. Use the available tools to answer the user's questions.",
        tools: [a2aAgent.AsAIFunction()]
    );

// Invoke the agent and output the text result.
Console.WriteLine(await agent.RunAsync("What can you help me with?"));
