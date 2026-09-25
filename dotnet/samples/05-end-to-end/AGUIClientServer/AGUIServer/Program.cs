// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel.Primitives;
using System.ComponentModel;
using AGUIServer;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Responses;

WebApplicationBuilder builder = WebApplication.CreateBuilder(args);
builder.Services.AddHttpClient().AddLogging();
builder.Services.ConfigureHttpJsonOptions(options => options.SerializerOptions.TypeInfoResolverChain.Add(AGUIServerSerializerContext.Default));
builder.Services.AddAGUIServer();

Uri endpoint = AzureOpenAIEndpoint.From(
    builder.Configuration["AZURE_OPENAI_ENDPOINT"])
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
string deploymentName = builder.Configuration["AZURE_OPENAI_DEPLOYMENT_NAME"] ?? throw new InvalidOperationException("AZURE_OPENAI_DEPLOYMENT_NAME is not set.");

const string AgentName = "AGUIAssistant";

// Create a Responses-backed OpenAI client that sends a bearer token to the Azure endpoint.
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
IChatClient chatClient = new OpenAIClient(
        new BearerTokenPolicy(new DefaultAzureCredential(), "https://ai.azure.com/.default"),
        new OpenAIClientOptions { Endpoint = endpoint })
    .GetResponsesClient()
    .AsIChatClientWithStoredOutputDisabled(model: deploymentName);

// WARNING: When adding session persistence (e.g., WithInMemorySessionStore), or running in production,
// make sure to also register an AgentIsolationKeyProvider to scope sessions by principal in multi-user
// deployments, e.g.:
// builder.Services.UseClaimsBasedAgentIsolation(new() { ClaimType = ClaimTypes.NameIdentifier });
//
// This sample does not authenticate AG-UI callers. Multi-user hosts must configure authentication
// and enforce endpoint authorization, for example with MapAGUIServer(...).RequireAuthorization().
// For claims-based isolation of persisted sessions, call builder.Services.AddHttpContextAccessor()
// and builder.Services.UseClaimsBasedAgentIsolation(), using a claim that uniquely identifies each caller.
// See the AG-UI samples README's "Security considerations" for configuration and client requirements.

// Register the agent with the host and configure it to use an in-memory session store
// so that conversation state is maintained across requests. In production, you may want to use a persistent session store.
builder
    .AddAIAgent(AgentName, (services, name) => chatClient.AsAIAgent(new ChatClientAgentOptions
    {
        Name = name,
        // Client tools are declarations on the server. If the model requests client and server tools
        // in the same response, the function-invocation loop returns both calls without executing them.
        // Bypassing keeps the non-approval-required server calls in the server session and initially
        // exposes only the client calls. The client executes them and sends each result with its
        // original call ID in a continuation request for the same thread. On that next request,
        // the server executes the stored calls rather than trusting calls replayed in client-supplied history.
        // The executed server calls and their matching results then appear in the continuation stream
        // as completed history, not as requests for the client to execute those server tools.
        // WithInMemorySessionStore below is required to retain those calls between HTTP requests;
        // without a session store, the deferred calls are lost when the client continues the run.
        EnableInvocableFunctionBypassing = true,
        ChatOptions = new ChatOptions
        {
            Instructions = "You are a helpful assistant.",
            Tools = services.GetKeyedServices<AITool>(name).ToList(),
        },
    }, services: services))
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
    // This sample is a single-user local demo with no isolation provider, so the builder's default strict
    // isolation wrapper would reject every request. Skipping it here lets MapAGUIServer add its own isolation
    // wrapper, which is strict only when an AgentIsolationKeyProvider is registered (see the warning above).
    .WithInMemorySessionStore(withIsolation: false);

WebApplication app = builder.Build();

// Map the AG-UI agent endpoint
app.MapAGUIServer(AgentName, "/");

await app.RunAsync();
