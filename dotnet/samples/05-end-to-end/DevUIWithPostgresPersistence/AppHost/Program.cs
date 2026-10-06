// Copyright (c) Microsoft. All rights reserved.

var builder = DistributedApplication.CreateBuilder(args);

var postgres = builder.AddPostgres("postgres")
    .WithDataVolume();
var conversations = postgres.AddDatabase("conversations");

string apiKey = builder.Configuration["OPENAI_API_KEY"]
    ?? throw new InvalidOperationException("OPENAI_API_KEY is required.");

var agentService = builder.AddProject<Projects.DevUIWithPostgresPersistence_AgentService>("agent-service")
    .WithHttpEndpoint(name: "http")
    .WithExternalHttpEndpoints()
    .WithReference(conversations)
    .WaitFor(conversations)
    .WithEnvironment("OPENAI_API_KEY", apiKey)
    .WithUrlForEndpoint("http", url => new()
    {
        Url = "/devui",
        DisplayText = "DevUI",
    });

if (builder.Configuration["OPENAI_MODEL"] is { Length: > 0 } model)
{
    agentService.WithEnvironment("OPENAI_MODEL", model);
}

if (builder.Configuration["OPENAI_ENDPOINT"] is { Length: > 0 } endpoint)
{
    agentService.WithEnvironment("OPENAI_ENDPOINT", endpoint);
}

builder.Build().Run();
