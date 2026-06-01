// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates using ConfigureDurableOptions to register BOTH agents AND workflows
// in a single Azure Functions app. It uses a workflow to translate text and a standalone AI agent
// accessible via HTTP and MCP tool triggers.

#pragma warning disable IDE0002 // Simplify Member Access

using Azure;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting.AzureFunctions;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Azure.Functions.Worker.Builder;
using Microsoft.Extensions.Hosting;
using OpenAI.Chat;
using WorkflowAndAgents;

// Get the Azure OpenAI endpoint and deployment name from environment variables.
string endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME")
    ?? throw new InvalidOperationException("AZURE_OPENAI_DEPLOYMENT_NAME is not set.");

// Use Azure Key Credential if provided, otherwise use Azure CLI Credential.
string? azureOpenAiKey = Environment.GetEnvironmentVariable("AZURE_OPENAI_API_KEY");
AzureOpenAIClient client = !string.IsNullOrEmpty(azureOpenAiKey)
    ? new AzureOpenAIClient(new Uri(endpoint), new AzureKeyCredential(azureOpenAiKey))
    : new AzureOpenAIClient(new Uri(endpoint), new DefaultAzureCredential());

ChatClient chatClient = client.GetChatClient(deploymentName);

// Define a standalone AI agent
AIAgent assistant = chatClient.AsAIAgent(
    "You are a helpful assistant. Answer questions clearly and concisely.",
    "Assistant",
    description: "A general-purpose helpful assistant.");

// Define workflow executors
TranslateText translateText = new();
FormatOutput formatOutput = new();

// Build a workflow: TranslateText -> FormatOutput
Workflow translateWorkflow = new WorkflowBuilder(translateText)
    .WithName("Translate")
    .WithDescription("Translate text to uppercase and format the result")
    .AddEdge(translateText, formatOutput)
    .Build();

// Use ConfigureDurableOptions to register both agents and workflows together
using IHost app = FunctionsApplication
    .CreateBuilder(args)
    .ConfigureFunctionsWebApplication()
    .ConfigureDurableOptions(options =>
    {
        // Register the standalone agent with HTTP and MCP tool triggers
        options.Agents.AddAIAgent(assistant, enableHttpTrigger: true, enableMcpToolTrigger: true);

        // Register the workflow with an HTTP endpoint and MCP tool trigger
        options.Workflows.AddWorkflow(translateWorkflow, exposeStatusEndpoint: false, exposeMcpToolTrigger: true);
    })
    .Build();
app.Run();
