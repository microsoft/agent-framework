// Copyright (c) Microsoft. All rights reserved.

// Sample: a resilient background workflow hosted with the Foundry Responses protocol. AgentServer
// re-invokes an interrupted response, while the workflow resumes from its durable checkpoint.
// It deploys directly from source, so Foundry builds and runs the uploaded project.

using Azure.AI.Projects;
using Azure.Identity;
using DotNetEnv;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

Env.TraversePath().Load();

var projectEndpoint = new Uri(System.Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set."));
var deployment = FirstNonBlank(
    System.Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME"),
    System.Environment.GetEnvironmentVariable("FOUNDRY_MODEL"),
    "gpt-4o");
var agentName = System.Environment.GetEnvironmentVariable("AGENT_NAME") ?? "hosted-workflow-resilient";

IChatClient chatClient = new AIProjectClient(projectEndpoint, new DefaultAzureCredential())
    .GetProjectOpenAIClient()
    .GetChatClient(deployment)
    .AsIChatClient();

AIAgent frenchAgent = chatClient.AsAIAgent(new ChatClientAgentOptions
{
    Id = "french-translator",
    Name = "French Translator",
    ChatOptions = new() { Instructions = "Translate the provided text to French. Return only the translation." },
});
AIAgent spanishAgent = chatClient.AsAIAgent(new ChatClientAgentOptions
{
    Id = "spanish-translator",
    Name = "Spanish Translator",
    ChatOptions = new() { Instructions = "Translate the provided text to Spanish. Return only the translation." },
});
AIAgent englishAgent = chatClient.AsAIAgent(new ChatClientAgentOptions
{
    Id = "english-translator",
    Name = "English Translator",
    ChatOptions = new() { Instructions = "Translate the provided text to English. Return only the translation." },
});

AIAgent agent = new WorkflowBuilder(frenchAgent)
    .AddEdge(frenchAgent, spanishAgent)
    .AddEdge(spanishAgent, englishAgent)
    .Build()
    .AsAIAgent(name: agentName);

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddFoundryResponses(agent, configure: options => options.ResilientBackground = true);

var app = builder.Build();
app.MapFoundryResponses();
app.Run();

static string FirstNonBlank(params string?[] candidates) =>
    Array.Find(candidates, candidate => !string.IsNullOrWhiteSpace(candidate))!;
