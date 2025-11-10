// Copyright (c) Microsoft. All rights reserved.

using Azure;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
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

// Two agents used by the orchestration to demonstrate concurrent execution.
const string PhysicistName = "PhysicistAgent";
const string PhysicistInstructions = "You are an expert in physics. You answer questions from a physics perspective.";

const string ChemistName = "ChemistAgent";
const string ChemistInstructions = "You are an expert in chemistry. You answer questions from a chemistry perspective.";

AIAgent physicistAgent = client.GetChatClient(deploymentName).CreateAIAgent(PhysicistInstructions, PhysicistName);
AIAgent chemistAgent = client.GetChatClient(deploymentName).CreateAIAgent(ChemistInstructions, ChemistName);

using IHost app = FunctionsApplication
    .CreateBuilder(args)
    .ConfigureFunctionsWebApplication()
    .ConfigureDurableAgents(options =>
    {
        options.AddAIAgent(physicistAgent);
        options.AddAIAgent(chemistAgent);
    })
    .Build();

app.Run();
