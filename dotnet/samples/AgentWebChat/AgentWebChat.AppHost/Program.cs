// Copyright (c) Microsoft. All rights reserved.

using AgentWebChat.AppHost;

var builder = DistributedApplication.CreateBuilder(args);

var azOpenAiResource = builder.AddParameterFromConfiguration("AzureOpenAIName", "AzureOpenAI:Name");
var azOpenAiResourceGroup = builder.AddParameterFromConfiguration("AzureOpenAIResourceGroup", "AzureOpenAI:ResourceGroup");
var chatModel = builder.AddAIModel("chat-model").AsAzureOpenAI("gpt-4o", o => o.AsExisting(azOpenAiResource, azOpenAiResourceGroup));

var agentHost = builder.AddProject<Projects.AgentWebChat_AgentHost>("agenthost")
    .WithHttpEndpoint(name: "devui")
    .WithUrlForEndpoint("devui", (url) => new() { Url = "/devui", DisplayText = "Dev UI" })
    .WithReference(chatModel);

builder.AddProject<Projects.AgentWebChat_Web>("webfrontend")
    .WithExternalHttpEndpoints()
    .WithReference(agentHost)
    .WaitFor(agentHost);

builder.Build().Run();
