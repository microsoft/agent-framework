// Copyright (c) Microsoft. All rights reserved.

// A hosted data-processing harness with approval-gated file writes and read-only auto-approval.

using System.ClientModel.Primitives;
using Azure.AI.Projects;
using Azure.Identity;
using DotNetEnv;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Extensions.AI;

Env.NoClobber().TraversePath().Load();

string endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME")
    ?? throw new InvalidOperationException("AZURE_AI_MODEL_DEPLOYMENT_NAME is not set.");

string seedDir = Path.Combine(AppContext.BaseDirectory, "working");
string workingDir;
if (!string.IsNullOrEmpty(Environment.GetEnvironmentVariable("FOUNDRY_HOSTING_ENVIRONMENT")))
{
    // Preserve files edited in prior turns; only seed files that do not yet exist in the
    // per-session writable home. The application directory is read-only in Foundry.
    string home = System.Environment.GetFolderPath(System.Environment.SpecialFolder.UserProfile);
    Directory.SetCurrentDirectory(home);
    workingDir = Path.Combine(home, "working");
    foreach (string file in Directory.GetFiles(seedDir, "*", SearchOption.AllDirectories))
    {
        string destination = Path.Combine(workingDir, Path.GetRelativePath(seedDir, file));
        if (!File.Exists(destination))
        {
            Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
            File.Copy(file, destination);
        }
    }
}
else
{
    workingDir = seedDir;
}

const int MaxContextWindowTokens = 1_050_000;
const int MaxOutputTokens = 128_000;

IChatClient chatClient = new AIProjectClient(
        new Uri(endpoint),
        new DefaultAzureCredential(),
        new AIProjectClientOptions { RetryPolicy = new ClientRetryPolicy(3) })
    .GetProjectOpenAIClient()
    .GetProjectResponsesClientForModel(deploymentName)
    .AsIChatClient();

AIAgent agent = chatClient.AsHarnessAgent(new HarnessAgentOptions
{
    Name = "hosted-harness-data-processing",
    Description = "Reads and analyzes CSV files and writes reports with approval.",
    MaxContextWindowTokens = MaxContextWindowTokens,
    MaxOutputTokens = MaxOutputTokens,
    FileAccessStore = new FileSystemAgentFileStore(workingDir),
    ToolApprovalAgentOptions = new ToolApprovalAgentOptions
    {
        AutoApprovalRules = [FileAccessProvider.ReadOnlyToolsAutoApprovalRule],
    },
    DisableTodoProvider = true,
    DisableAgentModeProvider = true,
    DisableFileMemory = true,
    DisableWebSearch = true,
    ChatOptions = new ChatOptions
    {
        ModelId = deploymentName,
        MaxOutputTokens = MaxOutputTokens,
        Instructions =
            """
            You analyze data files in the working folder. List and read the files before answering
            questions about their contents. Present calculations and findings clearly. When asked
            for a report, write it with the file access tools, but never overwrite source data
            unless the user explicitly asks you to.
            """,
    },
});

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddFoundryResponses(agent);

var app = builder.Build();
app.MapFoundryResponses();
app.Run();
