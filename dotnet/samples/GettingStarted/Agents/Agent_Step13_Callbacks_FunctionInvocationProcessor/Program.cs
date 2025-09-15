// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable RCS1110 // Declare type inside namespace
#pragma warning disable CA1812 // Declare type inside namespace

using System;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.Logging;

// Create a logger factory for the sample
using var loggerFactory = LoggerFactory.Create(builder =>
    builder.AddConsole().SetMinimumLevel(LogLevel.Information));

// Get Azure AI Foundry configuration from environment variables
var endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
var model = System.Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_MODEL_ID") ?? "gpt-4o-mini";

// Get a client to create/retrieve server side agents with
var persistentAgentsClient = new PersistentAgentsClient(endpoint, new AzureCliCredential());

// Example 3: Agent with custom middleware
Console.WriteLine("=== Agent with custom middleware ===");

var agent = persistentAgentsClient.CreateAIAgent(model)
    .AsBuilder()
    .UseCallbacks(config =>
{
    config.AddCallback(new UsedApiFunctionInvocationCallback());
    config.AddCallback(new CityInformationFunctionInvocationCallback());
}).Build();

Console.WriteLine("=== Wording Guardrail ===");
var guardRailedResponse = await agent.RunAsync("Tell me something harmful.");
Console.WriteLine(guardRailedResponse);

Console.WriteLine("=== Wording Guardrail - Streaming ===");
await foreach (var update in agent.RunStreamingAsync("Tell me something illegal."))
{
    Console.WriteLine(update);
}

Console.WriteLine("=== PII detection ===");
var piiResponse = await agent.RunAsync("My name is John Doe, call me at 123-456-7890 or email me at john@something.com");
Console.WriteLine(piiResponse);

Console.WriteLine("=== PII detection - Streaming ===");
await foreach (var update in agent.RunStreamingAsync("My name is Jane Smith, call me at 987-654-3210."))
{
    Console.WriteLine(update);
}

// Cleanup
await persistentAgentsClient.Administration.DeleteAgentAsync(agent.Id);

internal sealed class UsedApiFunctionInvocationCallback : CallbackMiddleware<AgentFunctionInvocationCallbackContext>
{
    public override async Task OnProcessAsync(AgentFunctionInvocationCallbackContext context, Func<AgentFunctionInvocationCallbackContext, Task> next, CancellationToken cancellationToken)
    {
        Console.WriteLine($"IsStreaming: {context!.IsStreaming}");

        await next(context);
    }
}

internal sealed class CityInformationFunctionInvocationCallback : CallbackMiddleware<AgentFunctionInvocationCallbackContext>
{
    public override async Task OnProcessAsync(AgentFunctionInvocationCallbackContext context, Func<AgentFunctionInvocationCallbackContext, Task> next, CancellationToken cancellationToken)
    {
        Console.WriteLine($"City Name: {(context!.Arguments.TryGetValue("location", out var location) ? location : "not provided")}");
        await next(context);
    }
}
