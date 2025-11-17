// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to configure AI agents to be accessible as MCP tools.
// When using AddAIAgent and enabling MCP tool triggers, the Functions host will automatically
// generate a remote MCP endpoint for the app at /runtime/webhooks/mcp with a agent-specific
// query tool name.

using Azure;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.DurableTask;
using Microsoft.Agents.AI.Hosting.AzureFunctions;
using Microsoft.Azure.Functions.Worker.Builder;
using Microsoft.Extensions.Hosting;
using OpenAI;

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

// Define three AI agents we are going to use in this application.
AIAgent agent1 = client.GetChatClient(deploymentName).CreateAIAgent("You are good at telling jokes.", "Joker");

AIAgent agent2 = client.GetChatClient(deploymentName)
    .CreateAIAgent("Check stock prices.", "StockAdvisor");

AIAgent agent3 = client.GetChatClient(deploymentName)
    .CreateAIAgent("Recommend plants.", "PlantAdvisor", description: "Get plant recommendations.");

using IHost app = FunctionsApplication
    .CreateBuilder(args)
    .ConfigureFunctionsWebApplication()
    .ConfigureDurableAgents(options =>
    {
        options
        .AddAIAgent(agent1)  // Enables HTTP trigger by default.
        .AddAIAgent(agent2, enableHttpTrigger: false, enableMcpToolTrigger: true) // Disable HTTP trigger, enable MCP Tool trigger.
        .AddAIAgent(agent3, agentOptions =>
        {
            agentOptions.McpToolTrigger.IsEnabled = true; // Enable MCP Tool trigger.
        });
    })
    .Build();
app.Run();
