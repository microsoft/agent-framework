// Copyright (c) Microsoft. All rights reserved.

var builder = DistributedApplication.CreateBuilder(args);

_ = builder.AddParameterFromConfiguration("tenant", "Azure:TenantId");
var existingFoundryName = builder.AddParameter("existingFoundryName")
    .WithDescription("The name of the existing Azure Foundry resource.");
var existingFoundryResourceGroup = builder.AddParameter("existingFoundryResourceGroup")
    .WithDescription("The resource group of the existing Azure Foundry resource.");

var foundry = builder.AddAzureAIFoundry("foundry")
    .AsExisting(existingFoundryName, existingFoundryResourceGroup);

// Add the writer agent service
var writerAgent = builder.AddProject<Projects.WriterAgent>("writer-agent")
    .WithHttpHealthCheck("/health")
    .WithReference(foundry).WaitFor(foundry);

// Add the editor agent service
var editorAgent = builder.AddProject<Projects.EditorAgent>("editor-agent")
    .WithHttpHealthCheck("/health")
    .WithReference(foundry).WaitFor(foundry);

// Add DevUI integration that aggregates agents from all agent services.
// Agent metadata is declared here so backends don't need a /v1/entities endpoint.
_ = builder.AddDevUI("devui")
    .WithAgentService(writerAgent, agents: [new("writer")])
    .WithAgentService(editorAgent, agents: [new("editor")])
    .WaitFor(writerAgent)
    .WaitFor(editorAgent);

builder.Build().Run();
