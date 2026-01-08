// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel;
using System.ClientModel.Primitives;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting.AzureFunctions;
using Microsoft.Azure.Functions.Worker.Builder;
using Microsoft.Extensions.Hosting;
using OpenAI;
using OpenAI.Chat;

// Get the Azure OpenAI endpoint and deployment name from environment variables.
string endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_DEPLOYMENT is not set.");

// Use Azure Key Credential if provided, otherwise use Azure CLI Credential.
string? azureOpenAiKey = System.Environment.GetEnvironmentVariable("AZURE_OPENAI_KEY");
OpenAIClientOptions clientOptions = new() { Endpoint = new Uri($"{endpoint}/openai/v1") };
OpenAIClient client = !string.IsNullOrEmpty(azureOpenAiKey)
    ? new OpenAIClient(new ApiKeyCredential(azureOpenAiKey), clientOptions)
    : new OpenAIClient(new BearerTokenPolicy(new AzureCliCredential(), "https://ai.azure.com/.default"), clientOptions);

// Two agents used by the orchestration to demonstrate conditional logic.
const string SpamDetectionName = "SpamDetectionAgent";
const string SpamDetectionInstructions = "You are a spam detection assistant that identifies spam emails.";

const string EmailAssistantName = "EmailAssistantAgent";
const string EmailAssistantInstructions = "You are an email assistant that helps users draft responses to emails with professionalism.";

AIAgent spamDetectionAgent = client.GetChatClient(deploymentName)
    .CreateAIAgent(SpamDetectionInstructions, SpamDetectionName);

AIAgent emailAssistantAgent = client.GetChatClient(deploymentName)
    .CreateAIAgent(EmailAssistantInstructions, EmailAssistantName);

using IHost app = FunctionsApplication
    .CreateBuilder(args)
    .ConfigureFunctionsWebApplication()
    .ConfigureDurableAgents(options =>
    {
        options
            .AddAIAgent(spamDetectionAgent)
            .AddAIAgent(emailAssistantAgent);
    })
    .Build();

app.Run();
