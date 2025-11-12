// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to integrate AI agents into a workflow pipeline.
// Three translation agents are connected sequentially to create a translation chain:
// English → French → Spanish → English, showing how agents can be composed as workflow executors.

using Azure.AI.AgentServer.AgentFramework.Extensions;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

// Set up the Azure OpenAI client
var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

IChatClient chatClient = new AzureOpenAIClient(new Uri(endpoint), new DefaultAzureCredential())
    .GetChatClient(deploymentName)
    .AsIChatClient();

// Create agents
AIAgent frenchAgent = GetTranslationAgent("French", chatClient);
AIAgent spanishAgent = GetTranslationAgent("Spanish", chatClient);
AIAgent englishAgent = GetTranslationAgent("English", chatClient);

// Build the workflow and turn it into an agent
AIAgent agent = new WorkflowBuilder(frenchAgent)
    .AddEdge(frenchAgent, spanishAgent)
    .AddEdge(spanishAgent, englishAgent)
    .Build()
    .AsAgent();

await agent.RunAIAgentAsync();

static ChatClientAgent GetTranslationAgent(string targetLanguage, IChatClient chatClient) =>
    new(chatClient, $"You are a translation assistant that translates the provided text to {targetLanguage}.");
