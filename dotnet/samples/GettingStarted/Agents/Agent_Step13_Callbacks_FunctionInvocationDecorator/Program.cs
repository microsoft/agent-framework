// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable RCS1110 // Declare type inside namespace
#pragma warning disable CA1812 // Declare type inside namespace

using System;
using System.ComponentModel;
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

Console.WriteLine("=== Example: Agent with custom function middleware ===");

[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";

var agent = persistentAgentsClient.CreateAIAgent(model)
    .AsBuilder()
    .Use((functionInvocationContext, next, ct) =>
    {
        Console.WriteLine($"IsStreaming: {functionInvocationContext!.IsStreaming}");

        return next(functionInvocationContext);
    })
    .Use((functionInvocationContext, next, ct) =>
    {
        Console.WriteLine($"City Name: {(functionInvocationContext!.Arguments.TryGetValue("location", out var location) ? location : "not provided")}");

        return next(functionInvocationContext);
    })
    .Build();

var thread = agent.GetNewThread();

var options = new ChatClientAgentRunOptions(new() { Tools = [AIFunctionFactory.Create(GetWeather)] });
var response = await agent.RunAsync("What's the weather in Seattle?", thread, options);
Console.WriteLine(response);

// Example 4: Streaming with middleware
Console.WriteLine("=== Example: Streaming Agent with custom function middleware ===");
await foreach (var update in agent.RunStreamingAsync("What's the weather in Seattle?", thread, options))
{
    if (update.Text is not null)
    {
        Console.Write(update.Text);
    }
}

// Cleanup
await persistentAgentsClient.Administration.DeleteAgentAsync(agent.Id);
