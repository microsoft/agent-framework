// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable RCS1110 // Declare type inside namespace
#pragma warning disable CA1812 // Declare type inside namespace

using System;
using System.ComponentModel;
using System.Linq;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.Logging;

// Create a logger factory for the sample
using var loggerFactory = LoggerFactory.Create(builder =>
    builder.AddConsole().SetMinimumLevel(LogLevel.Information));

// Get Azure AI Foundry configuration from environment variables
var endpoint = Environment.GetEnvironmentVariable("AZUREOPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
var deploymentName = System.Environment.GetEnvironmentVariable("AZUREOPENAI_DEPLOYMENT_NAME") ?? "gpt-4o";

// Get a client to create/retrieve server side agents with
var client = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential()).GetChatClient(deploymentName);

[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";

[Description("The current datetime offset.")]
static string GetDateTime()
    => DateTimeOffset.Now.ToString();

var agent = new ChatClientAgent(client.AsIChatClient(), new ChatClientAgentOptions(
        instructions: "You are an AI assistant that helps people find information.",
        tools: [AIFunctionFactory.Create(GetDateTime)]))
    .AsBuilder()
    .UseFunctionInvocationMiddleware(async (context, next) =>
    {
        Console.WriteLine($"""
            === Middleware 1 Before Invoke Start ===
              Function Name: {context!.Function.Name}
              Function call index: {context.FunctionCallIndex}
              Function iteration: {context.Iteration}
              Total number of functions: {context.FunctionCount}
            === Middleware 1 Before Invoke End ===
            """);
        await next(context);
        Console.WriteLine($"""
            === Middleware 1 After Invoke Start ===")
              Function Name: {context!.Function.Name}
              IsStreaming: {context.IsStreaming}
            === Middleware 1 After Invoke End ===
            """);
    })
    .UseFunctionInvocationMiddleware(async (context, next) =>
    {
        Console.WriteLine($"""
            === Middleware 2 Before Invoke Start ===
              Function Name: {context!.Function.Name}
              Location: {(context!.Arguments.TryGetValue("location", out var location) ? location : "location parameter not provided")}
            === Middleware 2 Before Invoke End  ===
            """);
        await next(context);
        Console.WriteLine($"""
            === Middleware 2 After Invoke Start ===")
              Function Name: {context!.Function.Name}
              Function Result: {context.FunctionResult}
            === Middleware 2 After Invoke End ===
            """);
    })
    .Build();

var thread = agent.GetNewThread();

var options = new ChatClientAgentRunOptions(new() { Tools = [AIFunctionFactory.Create(GetWeather)] });

Console.WriteLine("=== Example: Non-Streaming Agent with custom function middleware ===");
var runResponse = await agent.RunAsync("What's the current time and the weather in Seattle?", thread, options);

Console.WriteLine("=== Example: Streaming Agent with custom function middleware ===");
var streamingRunResponse = agent.RunStreamingAsync("What's the current time and the weather in Seattle?", thread, options).ToListAsync();
