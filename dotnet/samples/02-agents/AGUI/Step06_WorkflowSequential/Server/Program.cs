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

AIAgent producer = chatClient.AsAIAgent(
    name: "Producer",
    instructions: "Draft a concise answer to the user's request.");
AIAgent reviewer = chatClient.AsAIAgent(
    name: "Reviewer",
    instructions: "Review the draft and return an improved final answer.");

Workflow workflow = SequentialWorkflow.Create(producer, reviewer);
AIAgent workflowAgent = workflow.AsAIAgent(name: "SequentialWorkflow");

WebApplication app = builder.Build();
app.MapAGUIServer("/", workflowAgent);
await app.RunAsync();
