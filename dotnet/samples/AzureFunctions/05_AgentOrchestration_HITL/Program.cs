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
OpenAIClient client = !string.IsNullOrEmpty(azureOpenAiKey)
    ? new OpenAIClient(new ApiKeyCredential(azureOpenAiKey), new OpenAIClientOptions() { Endpoint = new Uri($"{endpoint}/openai/v1") })
    : new OpenAIClient(new BearerTokenPolicy(new AzureCliCredential(), "https://ai.azure.com/.default"), new OpenAIClientOptions() { Endpoint = new Uri($"{endpoint}/openai/v1") });

// Single agent used by the orchestration to demonstrate human-in-the-loop workflow.
const string WriterName = "WriterAgent";
const string WriterInstructions =
    """
    You are a professional content writer who creates high-quality articles on various topics.
    You write engaging, informative, and well-structured content that follows best practices for readability and accuracy.
    """;

AIAgent writerAgent = client.GetChatClient(deploymentName).CreateAIAgent(WriterInstructions, WriterName);

using IHost app = FunctionsApplication
    .CreateBuilder(args)
    .ConfigureFunctionsWebApplication()
    .ConfigureDurableAgents(options => options.AddAIAgent(writerAgent))
    .Build();

app.Run();
