// Copyright (c) Microsoft. All rights reserved.

using HelloHttpApi.AppHost;

var builder = DistributedApplication.CreateBuilder(args);

var azOpenAiResource = builder.AddParameterFromConfiguration("AzureOpenAIName", "AzureOpenAI:Name");
var azOpenAiResourceGroup = builder.AddParameterFromConfiguration("AzureOpenAIResourceGroup", "AzureOpenAI:ResourceGroup");
var chatModel = builder.AddAIModel("chat-model").AsAzureOpenAI("gpt-4o", o => o.AsExisting(azOpenAiResource, azOpenAiResourceGroup));

var apiService = builder.AddProject<Projects.HelloHttpApi_ApiService>("apiservice")
        .WithReference(chatModel);

builder.AddProject<Projects.HelloHttpApi_Web>("webfrontend")
    .WithExternalHttpEndpoints()
    .WithReference(apiService)
    .WaitFor(apiService);

builder.Build().Run();
