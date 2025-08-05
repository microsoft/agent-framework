// Copyright (c) Microsoft. All rights reserved.

using HelloHttpApi.AppHost;

var builder = DistributedApplication.CreateBuilder(args);

var azOpenAiResource = builder.AddParameterFromConfiguration("AzureOpenAIName", "AzureOpenAI:Name");
var azOpenAiResourceGroup = builder.AddParameterFromConfiguration("AzureOpenAIResourceGroup", "AzureOpenAI:ResourceGroup");
var chatModel = builder.AddAIModel("chat-model").AsAzureOpenAI("gpt-4o", o => o.AsExisting(azOpenAiResource, azOpenAiResourceGroup));

var cosmosDbResource = builder.AddParameterFromConfiguration("CosmosDbName", "CosmosDb:Name");
var cosmosDbResourceGroup = builder.AddParameterFromConfiguration("CosmosDbResourceGroup", "CosmosDb:ResourceGroup");
var cosmos = builder.AddAzureCosmosDB("hello-http-api-cosmosdb").RunAsExisting(cosmosDbResource, cosmosDbResourceGroup);

var stateDb = cosmos.AddCosmosDatabase("actor-state-db");

var apiService = builder.AddProject<Projects.HelloHttpApi_ApiService>("apiservice")
        .WithReference(chatModel)
        .WithReference(cosmos).WaitFor(cosmos);

builder.AddProject<Projects.HelloHttpApi_Web>("webfrontend")
    .WithExternalHttpEndpoints()
    .WithReference(apiService)
    .WaitFor(apiService);

builder.Build().Run();
