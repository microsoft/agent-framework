// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a Azure OpenAI AI agent as a function tool.

using System.ComponentModel;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";

// Create the chat client and agent, and provide the function tool to the agent.
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIAgent weatherAgent = new ProjectResponsesClient(
    projectEndpoint: new Uri(endpoint),
    tokenProvider: new DefaultAzureCredential())
    .AsIChatClient()
    .AsAIAgent(new ChatClientAgentOptions
    {
        Name = "WeatherAgent",
        Description = "An agent that answers questions about the weather.",
        ChatOptions = new()
        {
            ModelId = deploymentName,
            Instructions = "You answer questions about the weather.",
            Tools = [AIFunctionFactory.Create(GetWeather)]
        },
    });

// Create the main agent, and provide the weather agent as a function tool.
AIAgent agent = new ProjectResponsesClient(
    projectEndpoint: new Uri(endpoint),
    tokenProvider: new DefaultAzureCredential())
    .AsIChatClient()
    .AsAIAgent(new ChatClientAgentOptions
    {
        ChatOptions = new()
        {
            ModelId = deploymentName,
            Instructions = "You are a helpful assistant who responds in French.",
            Tools = [weatherAgent.AsAIFunction()]
        },
    });

// Invoke the agent and output the text result.
Console.WriteLine(await agent.RunAsync("What is the weather like in Amsterdam?"));
