// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using AGUI.WorkflowTools;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;
using OpenAI.Chat;

WebApplicationBuilder builder = WebApplication.CreateBuilder(args);
builder.Services.AddHttpClient().AddLogging();
builder.Services.AddAGUIServer();

string endpoint = builder.Configuration["AZURE_OPENAI_ENDPOINT"]
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
string deploymentName = builder.Configuration["AZURE_OPENAI_DEPLOYMENT_NAME"]
    ?? throw new InvalidOperationException("AZURE_OPENAI_DEPLOYMENT_NAME is not set.");

[Description("Gets a deterministic weather forecast for a city.")]
static string GetWeather([Description("The city to inspect.")] string city)
    => $"The weather in {city} is sunny and 24 C.";

ChatClient chatClient = new AzureOpenAIClient(
        new Uri(endpoint),
        new DefaultAzureCredential())
    .GetChatClient(deploymentName);

AIAgent weatherAgent = chatClient.AsAIAgent(
    name: "WeatherAgent",
    instructions: "Use the weather tool and answer with the returned forecast.",
    tools: [AIFunctionFactory.Create(GetWeather)]);
AIAgent workflowAgent = ToolWorkflow.Create(weatherAgent).AsAIAgent(name: "ToolWorkflow");

WebApplication app = builder.Build();
app.MapAGUIServer("/", workflowAgent);
await app.RunAsync();
