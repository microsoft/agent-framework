// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to poll for long-running task completion using continuation tokens with an A2A AI agent.

using A2A;
using Microsoft.Agents.AI;

var a2aAgentHost = Environment.GetEnvironmentVariable("A2A_AGENT_HOST") ?? throw new InvalidOperationException("A2A_AGENT_HOST is not set.");

// Initialize an A2ACardResolver to get an A2A agent card.
A2ACardResolver agentCardResolver = new(new Uri(a2aAgentHost));

// Get the agent card
AgentCard agentCard = await agentCardResolver.GetAgentCardAsync();

// Create an instance of the AIAgent for an existing A2A agent specified by the agent card.
AIAgent agent = agentCard.GetAIAgent();

AgentThread thread = agent.GetNewThread();

// Start the initial run with a long-running task.
AgentRunResponse response = await agent.RunAsync("Conduct a comprehensive analysis of quantum computing applications in cryptography, including recent breakthroughs, implementation challenges, and future roadmap. Please include diagrams and visual representations to illustrate complex concepts.", thread);

// Poll until the response is complete.
while (response.ContinuationToken is { } token)
{
    // Wait before polling again.
    await Task.Delay(TimeSpan.FromSeconds(2));

    // Continue with the token.
    response = await agent.RunAsync(thread, options: new AgentRunOptions { ContinuationToken = token });
}

// Display the result
Console.WriteLine(response);
