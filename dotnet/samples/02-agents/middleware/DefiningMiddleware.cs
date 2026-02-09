// Copyright (c) Microsoft. All rights reserved.

// Defining Middleware
// Basic middleware setup showing agent-level middleware with function tools.
// Middleware intercepts agent invocations to add cross-cutting behavior.
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

[Description("The current datetime offset.")]
static string GetDateTime() => DateTimeOffset.Now.ToString();

// <define_middleware>
// Function invocation middleware that logs before and after function calls
async ValueTask<object?> FunctionCallMiddleware(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
{
    Console.WriteLine($"[Middleware] Pre-Invoke: {context.Function.Name}");
    var result = await next(context, cancellationToken);
    Console.WriteLine($"[Middleware] Post-Invoke: {context.Function.Name}");
    return result;
}
// </define_middleware>

// <apply_middleware>
var agent = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential())
    .GetChatClient(deploymentName)
    .AsIChatClient()
    .BuildAIAgent(
        instructions: "You are an AI assistant that helps people find information.",
        tools: [AIFunctionFactory.Create(GetDateTime, name: nameof(GetDateTime))]);

var middlewareAgent = agent
    .AsBuilder()
    .Use(FunctionCallMiddleware)
    .Build();
// </apply_middleware>

Console.WriteLine(await middlewareAgent.RunAsync("What time is it?"));
