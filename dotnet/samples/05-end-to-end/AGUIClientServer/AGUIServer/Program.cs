// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel.Primitives;
using System.ComponentModel;
using AGUIServer;
using Azure.Identity;
using Microsoft.Agents.AI.Hosting;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Responses;

WebApplicationBuilder builder = WebApplication.CreateBuilder(args);
builder.Services.AddHttpClient().AddLogging();
builder.Services.ConfigureHttpJsonOptions(options => options.SerializerOptions.TypeInfoResolverChain.Add(AGUIServerSerializerContext.Default));
builder.Services.AddAGUIServer();

string endpoint = builder.Configuration["AZURE_OPENAI_ENDPOINT"] ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
string deploymentName = builder.Configuration["AZURE_OPENAI_DEPLOYMENT_NAME"] ?? throw new InvalidOperationException("AZURE_OPENAI_DEPLOYMENT_NAME is not set.");

const string AgentName = "AGUIAssistant";

// Create a Responses-backed OpenAI client that sends a bearer token to the Azure endpoint.
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
IChatClient chatClient = new OpenAIClient(
        new BearerTokenPolicy(new DefaultAzureCredential(), "https://ai.azure.com/.default"),
        new OpenAIClientOptions { Endpoint = new Uri(endpoint) })
    .GetResponsesClient()
    .AsIChatClientWithStoredOutputDisabled(model: deploymentName);

// WARNING: When adding session persistence (e.g., WithInMemorySessionStore), or running in production,
// make sure to also register an AgentIsolationKeyProvider to scope sessions by principal in multi-user
// deployments, e.g.:
// builder.Services.UseClaimsBasedAgentIsolation(new() { ClaimType = ClaimTypes.NameIdentifier });

// Register the agent with the host and configure it to use an in-memory session store
// so that conversation state is maintained across requests. In production, you may want to use a persistent session store.
builder
    .AddAIAgent(AgentName, "You are a helpful assistant.", chatClient)
    .WithAITools(
        new HostedWebSearchTool(),
        AIFunctionFactory.Create(
            () => DateTimeOffset.UtcNow,
            name: "get_current_time",
            description: "Get the current UTC time."),
        AIFunctionFactory.Create(
            ([Description("The weather forecast request")] ServerWeatherForecastRequest request) =>
            {
                return new ServerWeatherForecastResponse()
                {
                    Summary = "Sunny",
                    TemperatureC = 25,
                    Date = request.Date
                };
            },
            name: "get_server_weather_forecast",
            description: "Gets the forecast for a specific location and date",
            AGUIServerSerializerContext.Default.Options))
    .WithInMemorySessionStore();

WebApplication app = builder.Build();

// Map the AG-UI agent endpoint
app.MapAGUIServer(AgentName, "/");

await app.RunAsync();
