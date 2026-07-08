// Copyright (c) Microsoft. All rights reserved.

// Background Responses — Asynchronous agent execution with polling
//
// This sample shows how to use background responses with ChatClientAgent
// and Azure AI Foundry for non-blocking agent execution.

using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;

var endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4-mini";

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIAgent agent = new AIProjectClient(
    new Uri(endpoint),
    new DefaultAzureCredential())
     .AsAIAgent(model: deploymentName, instructions: "You are a helpful assistant.");

// Enable background responses (only supported by OpenAI Responses at this time).
AgentRunOptions options = new() { AllowBackgroundResponses = true };

AgentSession session = await agent.CreateSessionAsync();

// Start the initial run.
AgentResponse response = await agent.RunAsync("Write a very long novel about otters in space.", session, options);

// Poll until the response is complete.
while (response.ContinuationToken is { } token)
{
    // Wait before polling again.
    await Task.Delay(TimeSpan.FromSeconds(2));

    // Continue with the token.
    options.ContinuationToken = token;

    response = await agent.RunAsync(session, options);
}

// Display the result.
Console.WriteLine(response.Text);

// Reset options and session for streaming.
options = new() { AllowBackgroundResponses = true };
session = await agent.CreateSessionAsync();

AgentResponseUpdate? lastReceivedUpdate = null;
// Start streaming.
await foreach (AgentResponseUpdate update in agent.RunStreamingAsync("Write a very long novel about otters in space.", session, options))
{
    // Output each update.
    Console.Write(update.Text);

    // Track the last update that carries a resumable continuation token.
    // Lifecycle events like response.completed return null tokens (response is finished),
    // so we only update our reference when a token is actually present.
    if (update.ContinuationToken is not null)
    {
        lastReceivedUpdate = update;
    }

    // Simulate connection loss after first piece of content received.
    if (update.Text.Length > 0)
    {
        break;
    }
}

// Resume from interruption point.
options.ContinuationToken = lastReceivedUpdate?.ContinuationToken;

await foreach (AgentResponseUpdate update in agent.RunStreamingAsync(session, options))
{
    // Output each update.
    Console.Write(update.Text);
}
