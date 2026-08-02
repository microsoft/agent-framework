// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to reconnect to an A2A agent's streaming response using continuation tokens,
// allowing recovery from stream interruptions without losing progress.

using A2A;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

var a2aAgentHost = Environment.GetEnvironmentVariable("A2A_AGENT_HOST") ?? throw new InvalidOperationException("A2A_AGENT_HOST is not set.");

// Initialize an A2ACardResolver to get an A2A agent card.
A2ACardResolver agentCardResolver = new(new Uri(a2aAgentHost));

// Get the agent card
AgentCard agentCard = await agentCardResolver.GetAgentCardAsync();

// Create an instance of the AIAgent for an existing A2A agent specified by the agent card.
AIAgent agent = agentCard.AsAIAgent();

AgentSession session = await agent.CreateSessionAsync();

ResponseContinuationToken? continuationToken = null;

await foreach (var update in agent.RunStreamingAsync("Conduct a comprehensive analysis of quantum computing applications in cryptography, including recent breakthroughs, implementation challenges, and future roadmap. Please include diagrams and visual representations to illustrate complex concepts.", session))
{
    // Saving the continuation token to be able to reconnect to the same response stream later.
    // Note: Continuation tokens are only returned for long-running tasks. If the underlying A2A agent
    // returns a message instead of a task, the continuation token will not be initialized.
    // A2A agents do not support stream resumption from a specific point in the stream,
    // but only reconnection to obtain the same response stream from the beginning.
    // So, A2A agents will return an initialized continuation token in the first update
    // representing the beginning of the stream, and it will be null in all subsequent updates.
    if (update.ContinuationToken is { } token)
    {
        continuationToken = token;
    }

    // Imitating stream interruption
    break;
}

// Reconnect to the same response stream using the continuation token obtained from the previous run.
// As a first update, the agent will return an update representing the current state of the response at the moment of calling
// RunStreamingAsync with the same continuation token, followed by other updates until the end of the stream is reached.
if (continuationToken is not null)
{
    await foreach (var update in agent.RunStreamingAsync(session, options: new() { ContinuationToken = continuationToken }))
    {
        if (!string.IsNullOrEmpty(update.Text))
        {
            Console.WriteLine(update.Text);
        }
    }
}
