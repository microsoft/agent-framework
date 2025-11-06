// Copyright (c) Microsoft. All rights reserved.

using AGUIDojoServer;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;
using Microsoft.AspNetCore.HttpLogging;

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

// Register AgentFactory
builder.Services.AddSingleton<ChatClientAgentFactory>();

WebApplication app = builder.Build();

app.UseHttpLogging();

// Get the factory instance
var chatClientAgentFactory = app.Services.GetRequiredService<ChatClientAgentFactory>();

// Map the AG-UI agent endpoints for different scenarios
app.MapAGUI("/chat-client/agentic_chat", chatClientAgentFactory.CreateAgenticChat());

app.MapAGUI("/chat-client/tool_call", chatClientAgentFactory.CreateBackendToolRendering());

app.MapAGUI("/chat-client/human_in_the_loop", chatClientAgentFactory.CreateHumanInTheLoop());

app.MapAGUI("/chat-client/tool_based_generative_ui", chatClientAgentFactory.CreateToolBasedGenerativeUI());

app.MapAGUI("/chat-client/agentic_generative_ui", chatClientAgentFactory.CreateAgenticUI());

app.MapAGUI("/chat-client/shared_state", chatClientAgentFactory.CreateSharedState());

await app.RunAsync();

public partial class Program { }
