// Copyright (c) Microsoft. All rights reserved.

using AgentWebChat.AppHost;

var builder = DistributedApplication.CreateBuilder(args);

var azOpenAiResource = builder.AddParameterFromConfiguration("AzureOpenAIName", "AzureOpenAI:Name");
var azOpenAiResourceGroup = builder.AddParameterFromConfiguration("AzureOpenAIResourceGroup", "AzureOpenAI:ResourceGroup");
var chatModel = builder.AddAIModel("chat-model").AsAzureOpenAI("gpt-4o", o => o.AsExisting(azOpenAiResource, azOpenAiResourceGroup));

var cosmosDbResource = builder.AddParameterFromConfiguration("CosmosDbName", "CosmosDb:Name");
var cosmosDbResourceGroup = builder.AddParameterFromConfiguration("CosmosDbResourceGroup", "CosmosDb:ResourceGroup");
var cosmos = builder.AddAzureCosmosDB("agent-web-chat-cosmosdb").RunAsExisting(cosmosDbResource, cosmosDbResourceGroup);

var stateDb = cosmos.AddCosmosDatabase("actor-state-db");

var agentHost = builder.AddProject<Projects.AgentWebChat_AgentHost>("agenthost")
        .WithReference(chatModel)
        .WithReference(cosmos).WaitFor(cosmos);

builder.AddProject<Projects.AgentWebChat_Web>("webfrontend")
    .WithExternalHttpEndpoints()
    .WithReference(agentHost)
    .WaitFor(agentHost);

builder.Build().Run();
