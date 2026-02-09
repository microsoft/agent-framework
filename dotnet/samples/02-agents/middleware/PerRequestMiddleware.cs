// Copyright (c) Microsoft. All rights reserved.

// Per-Request Middleware
// Middleware that is scoped to a single agent run, not the entire agent lifetime.
// Useful for request-specific behavior like adding per-request tools or chat client middleware.
//
// For docs: https://learn.microsoft.com/agent-framework/agents/middleware

using System.ComponentModel;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o";

[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";

[Description("The current datetime offset.")]
static string GetDateTime() => DateTimeOffset.Now.ToString();

var agent = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential())
    .GetChatClient(deploymentName)
    .AsIChatClient()
    .BuildAIAgent(
        instructions: "You are a helpful assistant.",
        tools: [AIFunctionFactory.Create(GetDateTime, name: nameof(GetDateTime))]);

// <per_request_middleware>
// Per-request function middleware
async ValueTask<object?> PerRequestFunctionMiddleware(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
{
    Console.WriteLine($"[Per-Request] Function: {context.Function.Name}");
    return await next(context, cancellationToken);
}

// Per-request chat client middleware
async Task<ChatResponse> PerRequestChatClientMiddleware(IEnumerable<ChatMessage> messages, ChatOptions? options, IChatClient innerChatClient, CancellationToken cancellationToken)
{
    Console.WriteLine("[Per-Request] Chat Client Middleware");
    return await innerChatClient.GetResponseAsync(messages, options, cancellationToken);
}

// Add per-request tools and middleware via run options
var options = new ChatClientAgentRunOptions(new()
{
    Tools = [AIFunctionFactory.Create(GetWeather, name: nameof(GetWeather))]
})
{
    ChatClientFactory = (chatClient) => chatClient
        .AsBuilder()
        .Use(PerRequestChatClientMiddleware, null)
        .Build()
};

// Build a per-request middleware pipeline on top of the base agent
var response = await agent
    .AsBuilder()
    .Use(PerRequestFunctionMiddleware)
    .Build()
    .RunAsync("What's the current time and the weather in Seattle?", options: options);

Console.WriteLine(response);
// </per_request_middleware>
