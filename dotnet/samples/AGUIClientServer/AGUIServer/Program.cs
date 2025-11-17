// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using AGUIServer;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;
using Microsoft.Extensions.AI;
using OpenAI;

WebApplicationBuilder builder = WebApplication.CreateBuilder(args);
builder.Services.AddHttpClient().AddLogging();
builder.Services.ConfigureHttpJsonOptions(options => options.SerializerOptions.TypeInfoResolverChain.Add(AGUIServerSerializerContext.Default));
builder.Services.AddAGUI();

WebApplication app = builder.Build();

string endpoint = builder.Configuration["AZURE_OPENAI_ENDPOINT"] ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
string deploymentName = builder.Configuration["AZURE_OPENAI_DEPLOYMENT_NAME"] ?? throw new InvalidOperationException("AZURE_OPENAI_DEPLOYMENT_NAME is not set.");

// Create the AI agent with tools
var agent = new AzureOpenAIClient(
        new Uri(endpoint),
        new DefaultAzureCredential())
    .GetChatClient(deploymentName)
    .CreateAIAgent(
        name: "AGUIAssistant",
        tools: [
            AIFunctionFactory.Create(
                () => DateTimeOffset.UtcNow,
                name: "get_current_time",
                description: "Get the current UTC time."
            ),
            AIFunctionFactory.Create(
                ([Description("The weather forecast request")]ServerWeatherForecastRequest request) => {
                    return new ServerWeatherForecastResponse()
                    {
                        Summary = "Sunny",
                        TemperatureC = 25,
                        Date = request.Date
                    };
                },
                name: "get_server_weather_forecast",
                description: "Gets the forecast for a specific location and date",
                AGUIServerSerializerContext.Default.Options)
        ]);

// Map the AG-UI agent endpoint
app.MapAGUI("/", agent);

await app.RunAsync();
