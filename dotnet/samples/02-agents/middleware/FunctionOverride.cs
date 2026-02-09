// Copyright (c) Microsoft. All rights reserved.

// Function Override Middleware
// Function invocation middleware that can modify or override tool results.
// Useful for testing, caching, or post-processing function outputs.
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

// <function_override>
async ValueTask<object?> FunctionOverrideMiddleware(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
{
    var result = await next(context, cancellationToken);

    // Override the weather function result
    if (context.Function.Name == nameof(GetWeather))
    {
        result = "The weather is sunny with a high of 25°C.";
    }

    return result;
}
// </function_override>

var agent = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential())
    .GetChatClient(deploymentName)
    .AsIChatClient()
    .BuildAIAgent(
        instructions: "You are a helpful assistant.",
        tools: [AIFunctionFactory.Create(GetWeather)]);

var overriddenAgent = agent
    .AsBuilder()
    .Use(FunctionOverrideMiddleware)
    .Build();

Console.WriteLine(await overriddenAgent.RunAsync("What's the weather in Seattle?"));
