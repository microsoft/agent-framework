// Copyright (c) Microsoft. All rights reserved.

// Background Responses
// Use background responses for long-running agent tasks with polling and resumption.
// Supports both non-streaming (polling) and streaming (with interruption recovery).
//
// For docs: https://learn.microsoft.com/agent-framework/agents/background-responses

using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using OpenAI.Responses;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

AIAgent agent = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential())
    .GetResponsesClient(deploymentName)
    .AsAIAgent();

// <background_polling>
AgentRunOptions options = new() { AllowBackgroundResponses = true };
AgentSession session = await agent.CreateSessionAsync();

AgentResponse response = await agent.RunAsync("Write a very long novel about otters in space.", session, options);

// Poll until the response is complete.
while (response.ContinuationToken is { } token)
{
    await Task.Delay(TimeSpan.FromSeconds(2));
    options.ContinuationToken = token;
    response = await agent.RunAsync(session, options);
}

Console.WriteLine(response.Text);
// </background_polling>

// <background_streaming>
options = new() { AllowBackgroundResponses = true };
session = await agent.CreateSessionAsync();

AgentResponseUpdate? lastUpdate = null;
await foreach (AgentResponseUpdate update in agent.RunStreamingAsync("Write a very long novel about otters in space.", session, options))
{
    Console.Write(update.Text);
    lastUpdate = update;

    // Simulate connection loss
    if (update.Text.Length > 0) break;
}

// Resume from interruption point
options.ContinuationToken = lastUpdate?.ContinuationToken;
await foreach (AgentResponseUpdate update in agent.RunStreamingAsync(session, options))
{
    Console.Write(update.Text);
}
// </background_streaming>
