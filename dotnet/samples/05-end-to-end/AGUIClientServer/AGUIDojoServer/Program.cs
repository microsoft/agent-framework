// Copyright (c) Microsoft. All rights reserved.

using AGUIDojoServer;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;
using Microsoft.AspNetCore.HttpLogging;
using Microsoft.Extensions.Options;

WebApplicationBuilder builder = WebApplication.CreateBuilder(args);

builder.Services.AddHttpLogging(logging =>
{
    logging.LoggingFields = HttpLoggingFields.RequestPropertiesAndHeaders | HttpLoggingFields.RequestBody
        | HttpLoggingFields.ResponsePropertiesAndHeaders | HttpLoggingFields.ResponseBody;
    logging.RequestBodyLogLimit = int.MaxValue;
    logging.ResponseBodyLogLimit = int.MaxValue;
});

builder.Services.AddHttpClient().AddLogging();
builder.Services.ConfigureHttpJsonOptions(options => options.SerializerOptions.TypeInfoResolverChain.Add(AGUIDojoServerSerializerContext.Default));
builder.Services.AddAGUI();

// WARNING: When adding session persistence (e.g., WithInMemorySessionStore), or running in production,
// make sure to also register a SessionIsolationKeyProvider to scope sessions by principal in multi-user
// deployments, e.g.:
// builder.Services.UseClaimsBasedSessionIsolation(new() { ClaimType = ClaimTypes.NameIdentifier });

WebApplication app = builder.Build();

app.UseHttpLogging();

// Initialize the factory
ChatClientAgentFactory.Initialize(app.Configuration);

// Map the AG-UI agent endpoints for different scenarios
app.MapAGUI("/agentic_chat", ChatClientAgentFactory.CreateAgenticChat());

app.MapAGUI("/backend_tool_rendering", ChatClientAgentFactory.CreateBackendToolRendering());

app.MapAGUI("/human_in_the_loop", ChatClientAgentFactory.CreateHumanInTheLoop());

app.MapAGUI("/tool_based_generative_ui", ChatClientAgentFactory.CreateToolBasedGenerativeUI());

var jsonOptions = app.Services.GetRequiredService<IOptions<Microsoft.AspNetCore.Http.Json.JsonOptions>>();
app.MapAGUI("/agentic_generative_ui", ChatClientAgentFactory.CreateAgenticUI(jsonOptions.Value.SerializerOptions));

app.MapAGUI("/shared_state", ChatClientAgentFactory.CreateSharedState(jsonOptions.Value.SerializerOptions));

app.MapAGUI("/predictive_state_updates", ChatClientAgentFactory.CreatePredictiveStateUpdates(jsonOptions.Value.SerializerOptions));

await app.RunAsync();

public partial class Program;
