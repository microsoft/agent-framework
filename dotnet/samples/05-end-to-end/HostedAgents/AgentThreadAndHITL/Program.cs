// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates Human-in-the-Loop (HITL) capabilities with thread persistence.
// The agent wraps function tools with ApprovalRequiredAIFunction to require user approval
// before invoking them. Users respond with 'approve' or 'reject' when prompted.

using System.ComponentModel;
using Azure.AI.AgentServer.AgentFramework.Extensions;
using Azure.AI.AgentServer.AgentFramework.Persistence;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";

// Create the chat client and agent.
// Note: ApprovalRequiredAIFunction wraps the tool to require user approval before invocation.
// User should reply with 'approve' or 'reject' when prompted.
#pragma warning disable MEAI001 // Type is for evaluation purposes only
AIAgent agent = new AzureOpenAIClient(
    new Uri(endpoint),
    new AzureCliCredential())
    .GetChatClient(deploymentName)
    .AsIChatClient()
    .CreateAIAgent(
        instructions: "You are a helpful assistant",
        tools: [new ApprovalRequiredAIFunction(AIFunctionFactory.Create(GetWeather))]
    );
#pragma warning restore MEAI001

var threadRepository = new InMemoryAgentThreadRepository(agent);
await agent.RunAIAgentAsync(telemetrySourceName: "Agents", threadRepository: threadRepository);
