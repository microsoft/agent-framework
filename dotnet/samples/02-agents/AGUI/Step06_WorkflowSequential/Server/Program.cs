// Copyright (c) Microsoft. All rights reserved.

using AGUI.WorkflowSequential;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;
using Microsoft.Agents.AI.Workflows;
using OpenAI.Chat;

WebApplicationBuilder builder = WebApplication.CreateBuilder(args);
builder.Services.AddHttpClient().AddLogging();
builder.Services.AddAGUIServer();

string endpoint = builder.Configuration["AZURE_OPENAI_ENDPOINT"]
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
string deploymentName = builder.Configuration["AZURE_OPENAI_DEPLOYMENT_NAME"]
    ?? throw new InvalidOperationException("AZURE_OPENAI_DEPLOYMENT_NAME is not set.");

ChatClient chatClient = new AzureOpenAIClient(
        new Uri(endpoint),
        new DefaultAzureCredential())
    .GetChatClient(deploymentName);

AIAgent writer = chatClient.AsAIAgent(
    name: "Writer",
    instructions: "Draft a concise answer to the user's request.");
AIAgent reviewer = chatClient.AsAIAgent(
    name: "Reviewer",
    instructions: "Review the draft and return an improved final answer.");

AIAgent workflowAgent = SequentialWorkflow.Create(writer, reviewer).AsAIAgent(name: "SequentialWorkflow");

WebApplication app = builder.Build();
app.MapAGUIServer("/", workflowAgent);
await app.RunAsync();
