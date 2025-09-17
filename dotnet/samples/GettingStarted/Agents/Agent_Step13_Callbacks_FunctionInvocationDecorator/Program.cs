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
    .UseFunctionInvocationContext(async (context, next) =>
    {
        // Example: get function information
        var functionName = context!.Function.Description;

        // Example: get chat history
        var chatHistory = context.Messages;

        // Example: get information about all functions which will be invoked
        var functionCalls = context.CallContent;

        // In function calling functionality there are two loops.
        // Outer loop is "request" loop - it performs multiple requests to LLM until user ask will be satisfied.
        // Inner loop is "function" loop - it handles LLM response with multiple function calls.

        // Workflow example:
        // 1. Request to LLM #1 -> Response with 3 functions to call.
        //      1.1. Function #1 called.
        //      1.2. Function #2 called.
        //      1.3. Function #3 called.
        // 2. Request to LLM #2 -> Response with 2 functions to call.
        //      2.1. Function #1 called.
        //      2.2. Function #2 called.

        // context.RequestSequenceIndex - it's a sequence number of outer/request loop operation.
        // context.FunctionSequenceIndex - it's a sequence number of inner/function loop operation.
        // context.FunctionCount - number of functions which will be called per request (based on example above: 3 for first request, 2 for second request).

        // Example: get request sequence index
        Console.WriteLine($"Request sequence index: {context.FunctionCallIndex}");

        // Example: get function sequence index
        Console.WriteLine($"Function sequence index: {context.Iteration}");

        // Example: get total number of functions which will be called
        Console.WriteLine($"Total number of functions: {context.FunctionCount}");

        // Calling next filter in pipeline or function itself.
        // By skipping this call, next filters and function won't be invoked, and function call loop will proceed to the next function.
        await next(context);

        // Example: Terminate the function call request loop after this function invocation.
        context.Terminate = true;

        Console.WriteLine($"IsStreaming: {context.IsStreaming}");
    })
    .UseFunctionInvocationContext((functionInvocationContext, next) =>
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
