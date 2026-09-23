// Copyright (c) Microsoft. All rights reserved.

using AGUIDojoServer;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting;
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
builder.Services.AddAGUIServer();

// A session store is REQUIRED for mixed client/server tool continuation. When write_document and
// confirm_changes are requested together, invocable function bypassing saves the server's write_document
// call in the session and sends only confirm_changes to the client. The client's result returns in a
// separate HTTP request for the same thread, which must reload that session to execute the saved call.
// Without a session store, the deferred call is lost between requests. Client-replayed tool calls are not
// a trusted substitute for the server-side record. The registration key must match the agent's name so
// MapAGUIServer can find its store.
// In production, use a persistent session store instead of the in-memory one: InMemoryAgentSessionStore
// loses sessions on restart and keeps every session for the lifetime of the process, with no size limit,
// expiry or eviction. Thread ids are client-supplied, so multi-user hosts also need the isolation below.
// This store has no atomic consume: concurrent continuations on one thread can read the same pending call
// before either saves its updated session, potentially executing that call more than once.
builder.Services.AddKeyedSingleton<AgentSessionStore>("PredictiveStateUpdatesAgent", new InMemoryAgentSessionStore());

// WARNING: When session persistence is enabled, in a multi-user deployment you must also register an
// AgentIsolationKeyProvider to scope sessions by principal, e.g.:
// builder.Services.UseClaimsBasedAgentIsolation(new() { ClaimType = ClaimTypes.NameIdentifier });
//
// This sample does not authenticate AG-UI callers. Multi-user hosts must configure authentication
// and enforce endpoint authorization, for example with MapAGUIServer(...).RequireAuthorization().
// For claims-based isolation of persisted sessions, call builder.Services.AddHttpContextAccessor()
// and builder.Services.UseClaimsBasedAgentIsolation(), using a claim that uniquely identifies each caller.
// See the AG-UI samples README's "Security considerations" for configuration and client requirements.

WebApplication app = builder.Build();

app.UseHttpLogging();

// Initialize the factory
ChatClientAgentFactory.Initialize(app.Configuration);

// Map the AG-UI agent endpoints for different scenarios
app.MapAGUIServer("/agentic_chat", ChatClientAgentFactory.CreateAgenticChat());

app.MapAGUIServer("/backend_tool_rendering", ChatClientAgentFactory.CreateBackendToolRendering());

app.MapAGUIServer("/human_in_the_loop", ChatClientAgentFactory.CreateHumanInTheLoop());

app.MapAGUIServer("/tool_based_generative_ui", ChatClientAgentFactory.CreateToolBasedGenerativeUI());

var jsonOptions = app.Services.GetRequiredService<IOptions<Microsoft.AspNetCore.Http.Json.JsonOptions>>();
app.MapAGUIServer("/agentic_generative_ui", ChatClientAgentFactory.CreateAgenticUI(jsonOptions.Value.SerializerOptions));

app.MapAGUIServer("/shared_state", ChatClientAgentFactory.CreateSharedState(jsonOptions.Value.SerializerOptions));

app.MapAGUIServer("/predictive_state_updates", ChatClientAgentFactory.CreatePredictiveStateUpdates(jsonOptions.Value.SerializerOptions));

await app.RunAsync();

public partial class Program;
