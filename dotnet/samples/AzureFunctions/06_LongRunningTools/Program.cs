// Copyright (c) Microsoft. All rights reserved.

using Azure;
using Azure.AI.OpenAI;
using Azure.Identity;
using LongRunningTools;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting.AzureFunctions;
using Microsoft.Azure.Functions.Worker.Builder;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
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

// Agent used by the orchestration to write content.
const string WriterAgentName = "Writer";
const string WriterAgentInstructions =
    """
    You are a professional content writer who creates high-quality articles on various topics.
    You write engaging, informative, and well-structured content that follows best practices for readability and accuracy.
    """;

AIAgent writerAgent = client.GetChatClient(deploymentName).CreateAIAgent(WriterAgentInstructions, WriterAgentName);

// Agent that can start content generation workflows using tools
const string PublisherAgentName = "Publisher";
const string PublisherAgentInstructions =
    """
    You are a publishing agent that can manage content generation workflows.
    You have access to tools to start, monitor, and raise events for content generation workflows.
    """;

using IHost app = FunctionsApplication
    .CreateBuilder(args)
    .ConfigureFunctionsWebApplication()
    .ConfigureDurableAgents(options =>
    {
        // Add the writer agent used by the orchestration
        options.AddAIAgent(writerAgent);

        // Define the agent that can start orchestrations from tool calls
        options.AddAIAgentFactory(PublisherAgentName, sp =>
        {
            // Initialize the tools to be used by the agent.
            Tools publisherTools = new(sp.GetRequiredService<ILogger<Tools>>());

            return client.GetChatClient(deploymentName).CreateAIAgent(
                instructions: PublisherAgentInstructions,
                name: PublisherAgentName,
                services: sp,
                tools: [
                    AIFunctionFactory.Create(publisherTools.StartContentGenerationWorkflow),
                    AIFunctionFactory.Create(publisherTools.GetWorkflowStatusAsync),
                    AIFunctionFactory.Create(publisherTools.SubmitHumanApprovalAsync),
                ]);
        });
    })
    .Build();

app.Run();
