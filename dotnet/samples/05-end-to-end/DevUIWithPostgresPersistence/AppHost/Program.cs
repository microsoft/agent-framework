// Copyright (c) Microsoft. All rights reserved.

var builder = DistributedApplication.CreateBuilder(args);

var postgresUser = builder.AddParameter(
    "postgres-user",
    "postgres",
    publishValueAsDefault: true);
string postgresPasswordValue = builder.Configuration["POSTGRES_PASSWORD"]
    ?? throw new InvalidOperationException("POSTGRES_PASSWORD is required.");
var postgresPassword = builder.AddParameter(
    "postgres-password",
    postgresPasswordValue,
    secret: true);
var postgres = builder.AddPostgres("postgres", postgresUser, postgresPassword)
    .WithDataVolume();
var conversations = postgres.AddDatabase("conversations");

string foundryEndpoint = builder.Configuration["FOUNDRY_PROJECT_ENDPOINT"]
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is required.");

var agentService = builder.AddProject<Projects.DevUIWithPostgresPersistence_AgentService>("agent-service")
    .WithHttpEndpoint(name: "http")
    .WithExternalHttpEndpoints()
    .WithReference(conversations)
    .WaitFor(conversations)
    .WithEnvironment("FOUNDRY_PROJECT_ENDPOINT", foundryEndpoint)
    .WithUrlForEndpoint("http", url => new()
    {
        Url = "/devui",
        DisplayText = "DevUI",
    });

string? model = builder.Configuration["FOUNDRY_MODEL"]
    ?? builder.Configuration["FOUNDRY_MODEL_NAME"];
if (model is { Length: > 0 })
{
    agentService.WithEnvironment("FOUNDRY_MODEL", model);
}

builder.Build().Run();
