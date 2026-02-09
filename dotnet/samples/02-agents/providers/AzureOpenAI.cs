// Copyright (c) Microsoft. All rights reserved.

// Provider: Azure OpenAI (Chat Completion)
// Create an agent using Azure OpenAI Chat Completion as the backend.
//
// For docs: https://learn.microsoft.com/agent-framework/agents/providers

using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using OpenAI.Chat;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// <azure_openai>
AIAgent agent = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential())
    .GetChatClient(deploymentName)
    .AsAIAgent(instructions: "You are good at telling jokes.", name: "Joker");
// </azure_openai>

Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate."));
