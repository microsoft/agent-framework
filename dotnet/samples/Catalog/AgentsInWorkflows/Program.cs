// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to integrate AI agents into a workflow pipeline.
// Three translation agents are connected sequentially to create a translation chain:
// English → French → Spanish → English, showing how agents can be composed as workflow executors.

using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

// Set up the Azure OpenAI client
var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

IChatClient chatClient = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential())
    .GetChatClient(deploymentName)
    .AsIChatClient();

// Create agents
AIAgent frenchAgent = GetTranslationAgent("French", chatClient);
AIAgent spanishAgent = GetTranslationAgent("Spanish", chatClient);
AIAgent englishAgent = GetTranslationAgent("English", chatClient);

// Build the workflow by adding executors and connecting them
Workflow workflow = new WorkflowBuilder(frenchAgent)
    .AddEdge(frenchAgent, spanishAgent)
    .AddEdge(spanishAgent, englishAgent)
.Build();

// Execute the workflow
await using StreamingRun run = await InProcessExecution.StreamAsync(workflow, new ChatMessage(ChatRole.User, "Hello World!"));

// Must send the turn token to trigger the agents.
// The agents are wrapped as executors. When they receive messages,
// they will cache the messages and only start processing when they receive a TurnToken.
await run.TrySendMessageAsync(new TurnToken(emitEvents: true));
await foreach (WorkflowEvent evt in run.WatchStreamAsync())
{
    if (evt is AgentRunUpdateEvent executorComplete)
    {
        Console.WriteLine($"{executorComplete.ExecutorId}: {executorComplete.Data}");
    }
}

static ChatClientAgent GetTranslationAgent(string targetLanguage, IChatClient chatClient) =>
    new(chatClient, $"You are a translation assistant that translates the provided text to {targetLanguage}.");
