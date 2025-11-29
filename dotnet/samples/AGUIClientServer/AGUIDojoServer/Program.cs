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

WebApplication app = builder.Build();

app.UseHttpLogging();

// Initialize the factory
ChatClientAgentFactory.Initialize(app.Configuration);

// Map the AG-UI agent endpoints for different scenarios
app.MapAGUI("/agentic_chat", ChatClientAgentFactory.CreateAgenticChat());

app.MapAGUI("/backend_tool_rendering", ChatClientAgentFactory.CreateBackendToolRendering());

app.MapAGUI("/human_in_the_loop", ChatClientAgentFactory.CreateHumanInTheLoop());

app.MapAGUI("/tool_based_generative_ui", ChatClientAgentFactory.CreateToolBasedGenerativeUI());

app.MapAGUI("/agentic_generative_ui", ChatClientAgentFactory.CreateAgenticUI());

var jsonOptions = app.Services.GetRequiredService<IOptions<Microsoft.AspNetCore.Http.Json.JsonOptions>>();
app.MapAGUI("/shared_state", ChatClientAgentFactory.CreateSharedState(jsonOptions.Value.SerializerOptions));

// Map an AG-UI agent endpoint with per-request agent selection based on route parameter
app.MapAGUI("/agents/{agentId}", (context) =>
{
    string agentId = context.Request.RouteValues["agentId"]?.ToString() ?? string.Empty;
    return ValueTask.FromResult(agentId switch
    {
        "agentic_chat" => ChatClientAgentFactory.CreateAgenticChat(),
        "backend_tool_rendering" => ChatClientAgentFactory.CreateBackendToolRendering(),
        "human_in_the_loop" => ChatClientAgentFactory.CreateHumanInTheLoop(),
        "tool_based_generative_ui" => ChatClientAgentFactory.CreateToolBasedGenerativeUI(),
        "agentic_generative_ui" => ChatClientAgentFactory.CreateAgenticUI(),
        "shared_state" => ChatClientAgentFactory.CreateSharedState(jsonOptions.Value.SerializerOptions),
        _ => throw new ArgumentException($"Unknown agent ID: {agentId}"),
    });
});

await app.RunAsync();

public partial class Program;
