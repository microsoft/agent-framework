// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use background responses with ChatClientAgent and Azure OpenAI Responses for long-running operations.
// It shows polling for completion using continuation tokens, function calling during background operations,
// and persisting/restoring agent state between polling cycles.

#pragma warning disable CA1050 // Declare types in namespaces

using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-5";

var stateStore = new AgentStateStore();

AIAgent agent = new AzureOpenAIClient(
    new Uri(endpoint),
    new AzureCliCredential())
     .GetOpenAIResponseClient(deploymentName)
     .CreateAIAgent(
        name: "SpaceNovelWriter",
        instructions: "You are a space novel writer. Always research relevant facts and generate character profiles for the main characters before writing novels." +
                      "Write complete chapters without asking for approval or feedback. Do not ask the user about tone, style, pace, or format preferences - just write the novel based on the request.",
        tools: [.. new AgentFunctions().AsAITools()]);

// Enable background responses (only supported by {Azure}OpenAI Responses at this time).
AgentRunOptions options = new() { AllowBackgroundResponses = true };

AgentThread thread = agent.GetNewThread();

// Start the initial run.
AgentRunResponse response = await agent.RunAsync("Write a very long novel about a team of astronauts exploring an uncharted galaxy.", thread, options);

// Poll for background responses until complete.
while (response.ContinuationToken is not null)
{
    stateStore.PersistAgentState(thread, response.ContinuationToken);

    await Task.Delay(TimeSpan.FromSeconds(10));

    stateStore.RestoreAgentState(agent, out thread, out object? continuationToken);

    options.ContinuationToken = continuationToken;
    response = await agent.RunAsync(thread, options);
}

Console.WriteLine(response.Text);
