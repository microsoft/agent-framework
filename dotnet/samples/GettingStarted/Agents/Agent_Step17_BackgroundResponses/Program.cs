// Copyright (c) Microsoft. All rights reserved.

// This sample shows how use background responses with ChatClientAgent and OpenAI Responses.

using Microsoft.Agents.AI;
using OpenAI;

var apiKey = Environment.GetEnvironmentVariable("OPENAI_APIKEY") ?? throw new InvalidOperationException("OPENAI_APIKEY is not set.");
var model = Environment.GetEnvironmentVariable("OPENAI_MODEL") ?? "gpt-4o-mini";

AIAgent agent = new OpenAIClient(apiKey)
     .GetOpenAIResponseClient(model)
     .CreateAIAgent(instructions: "You are good at telling jokes.", name: "Joker");

// Enable background responses (only supported by OpenAI Responses at this time).
AgentRunOptions options = new() { AllowBackgroundResponses = true };

// Start the initial run.
AgentRunResponse response = await agent.RunAsync("Tell me a joke about a pirate.", options: options);

// Poll until the response is complete.
while (response.ContinuationToken is { } token)
{
    // Wait before polling again.
    await Task.Delay(TimeSpan.FromSeconds(2));

    // Continue with the token.
    options.ContinuationToken = token;

    response = await agent.RunAsync([], options: options);
}

// Display the result.
Console.WriteLine(response.Text);

// Reset options for streaming.
options = new() { AllowBackgroundResponses = true };

AgentRunResponseUpdate? lastReceivedUpdate = null;
// Start streaming.
await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync("Tell me a joke about a pirate.", options: options))
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
options.ContinuationToken = lastReceivedUpdate?.ContinuationToken;

await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync([], options: options))
{
    // Output each update.
    Console.Write(update.Text);
}
