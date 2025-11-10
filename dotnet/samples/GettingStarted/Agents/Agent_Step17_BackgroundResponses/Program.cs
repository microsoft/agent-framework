// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use background responses with ChatClientAgent and Azure OpenAI Responses.

using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using OpenAI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

AIAgent agent = new AzureOpenAIClient(
    new Uri(endpoint),
    new AzureCliCredential())
     .GetOpenAIResponseClient(deploymentName)
     .CreateAIAgent();

AgentThread thread = agent.GetNewThread();

// Start the initial run.
AgentRunResponse response = await agent.RunBackgroundAsync("Write a very long novel about otters in space.", thread);

// Poll until the response is complete.
while (response.ContinuationToken is { } token)
{
    // Wait before polling again.
    await Task.Delay(TimeSpan.FromSeconds(2));

    // Continue with the token.
    response = await agent.RunBackgroundAsync(thread, token);
}

// Display the result.
Console.WriteLine(response.Text);

thread = agent.GetNewThread();

AgentRunResponseUpdate? lastReceivedUpdate = null;
// Start streaming.
await foreach (AgentRunResponseUpdate update in agent.RunBackgroundStreamingAsync("Write a very long novel about otters in space.", thread))
{
    // Output each update.
    Console.Write(update.Text);

    // Track last update.
    lastReceivedUpdate = update;

    // Simulate connection loss after first piece of content received.
    if (update.Text.Length > 0)
    {
        break;
    }
}

// Resume from interruption point.
await foreach (AgentRunResponseUpdate update in agent.RunBackgroundStreamingAsync(thread, lastReceivedUpdate?.ContinuationToken))
{
    // Output each update.
    Console.Write(update.Text);
}
