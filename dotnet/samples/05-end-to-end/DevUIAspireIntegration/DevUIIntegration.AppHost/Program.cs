// Copyright (c) Microsoft. All rights reserved.

var builder = DistributedApplication.CreateBuilder(args);

var foundry = builder.AddAzureAIFoundry("foundry");

// Comment the following lines to create a new Foundry instance instead of connecting to an existing one. If creating a new instance, the DevUI resource will wait for the Foundry to be ready before starting, ensuring the DevUI frontend is available as soon as the app starts.
var existingFoundryName = builder.AddParameter("existingFoundryName")
    .WithDescription("The name of the existing Azure Foundry resource.");
var existingFoundryResourceGroup = builder.AddParameter("existingFoundryResourceGroup")
    .WithDescription("The resource group of the existing Azure Foundry resource.");
foundry.AsExisting(existingFoundryName, existingFoundryResourceGroup);

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
    .WithAgentService(writerAgent, agents: [new("writer")]) // the name of the agent should match the agent declaration in WriterAgent/Program.cs
    .WithAgentService(editorAgent, agents: [new("editor")]) // the name of the agent should match the agent declaration in EditorAgent/Program.cs
    .WaitFor(writerAgent)
    .WaitFor(editorAgent);

builder.Build().Run();
