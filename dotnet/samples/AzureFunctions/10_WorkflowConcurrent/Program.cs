// Copyright (c) Microsoft. All rights reserved.

using Azure;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting.AzureFunctions;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Azure.Functions.Worker.Builder;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Hosting;
using OpenAI.Chat;
using SingleAgent;

// Get the Azure OpenAI endpoint and deployment name from environment variables.
string endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_DEPLOYMENT is not set.");

// Use Azure Key Credential if provided, otherwise use Azure CLI Credential.
string? azureOpenAiKey = System.Environment.GetEnvironmentVariable("AZURE_OPENAI_KEY");
AzureOpenAIClient client = !string.IsNullOrEmpty(azureOpenAiKey)
    ? new AzureOpenAIClient(new Uri(endpoint), new AzureKeyCredential(azureOpenAiKey))
    : new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential());

AIAgent physicist = client.GetChatClient(deploymentName).CreateAIAgent("You are an expert in physics. You answer questions from a physics perspective.", "Physicist");
AIAgent chemist = client.GetChatClient(deploymentName).CreateAIAgent("You are an expert in chemistry. You answer questions from a chemistry perspective.", "Chemist");

var startExecutor = new ConcurrentStartExecutor();
var aggregationExecutor = new ResultAggregationExecutor();

// Build the workflow by adding executors and connecting them
var workflow = new WorkflowBuilder(startExecutor)
    .WithName("FanOutWorkflow")
    .AddFanOutEdge(startExecutor, [physicist, chemist])
    .AddFanInEdge([physicist, chemist], aggregationExecutor)
    .Build();

// Configure the function app to host AI agents and workflows in a unified way.
// This will automatically generate HTTP API endpoints for agents and workflows.

FunctionsApplication.CreateBuilder(args)
    .ConfigureFunctionsWebApplication()
    .ConfigureDurableOptions(options =>
    {
        // Configure workflows
        options.Workflows.AddWorkflow(workflow, enableMcpToolTrigger: true);
    })
    .Build().Run();
