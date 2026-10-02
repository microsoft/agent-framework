// Copyright (c) Microsoft. All rights reserved.

// A hosted research harness: planning, browsing, file memory, and an execute-mode todo loop.
// The browsing tool is shared with the existing console research sample.

using System.ClientModel.Primitives;
using Azure.AI.Projects;
using Azure.Identity;
using DotNetEnv;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Extensions.AI;
using SampleApp;

Env.NoClobber().TraversePath().Load();

string endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME")
    ?? throw new InvalidOperationException("AZURE_AI_MODEL_DEPLOYMENT_NAME is not set.");

// Foundry mounts the home directory per session; the application directory is read-only there.
bool isHosted = !string.IsNullOrEmpty(Environment.GetEnvironmentVariable("FOUNDRY_HOSTING_ENVIRONMENT"));
if (isHosted)
{
    Directory.SetCurrentDirectory(System.Environment.GetFolderPath(System.Environment.SpecialFolder.UserProfile));
}

string fileMemoryDir = isHosted
    ? Path.Combine(System.Environment.GetFolderPath(System.Environment.SpecialFolder.UserProfile), "agent-files")
    : Path.Combine(AppContext.BaseDirectory, "agent-files");

const int MaxContextWindowTokens = 1_050_000;
const int MaxOutputTokens = 128_000;

IChatClient modelClient = new AIProjectClient(
        new Uri(endpoint),
        new DefaultAzureCredential(),
        new AIProjectClientOptions { RetryPolicy = new ClientRetryPolicy(3) })
    .GetProjectOpenAIClient()
    .GetProjectResponsesClientForModel(deploymentName)
    .AsIChatClient();

IChatClient chatClient = new StatelessWebSearchChatClient(modelClient);

AIAgent agent = chatClient.AsHarnessAgent(new HarnessAgentOptions
{
    Name = "hosted-harness-research",
    Description = "Plans and performs research using web search and browsing.",
    MaxContextWindowTokens = MaxContextWindowTokens,
    MaxOutputTokens = MaxOutputTokens,
    FileMemoryStore = new FileSystemAgentFileStore(fileMemoryDir),
    LoopEvaluators = [new TodoCompletionLoopEvaluator(new TodoCompletionLoopEvaluatorOptions { Modes = ["execute"] })],
    LoopAgentOptions = new LoopAgentOptions { MaxIterations = 10 },
    ChatOptions = new ChatOptions
    {
        ModelId = deploymentName,
        Instructions =
            """
            You are a research assistant. Plan complex research using the todo and mode tools.
            Verify important claims with web search and browsing, cross-check sources, and cite
            the sources you used. Save the final report to file memory so it survives compaction.
            """,
        Tools = [new WebBrowsingTool(new WebBrowsingToolOptions { AllowPublicNetworks = true })],
        MaxOutputTokens = MaxOutputTokens,
        Reasoning = new() { Effort = ReasoningEffort.Medium },
    },
});

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddFoundryResponses(agent);

var app = builder.Build();
app.MapFoundryResponses();
app.Run();
