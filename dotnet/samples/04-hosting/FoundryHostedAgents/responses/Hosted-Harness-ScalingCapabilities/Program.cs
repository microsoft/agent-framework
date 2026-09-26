// Copyright (c) Microsoft. All rights reserved.

// Host the finance harness from Claw_Step03_ScalingCapabilities with local skills,
// a confined shell, approval-gated trades, background research, and optional CodeAct.

using System.ClientModel.Primitives;
using Azure.AI.Projects;
using Azure.Identity;
using ClawSample;
using DotNetEnv;
using HyperlightSandbox.Guest.Python;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Agents.AI.Hyperlight;
using Microsoft.Agents.AI.Tools.Shell;
using Microsoft.Extensions.AI;
using SampleApp;

Env.NoClobber().TraversePath().Load();

string endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME")
    ?? throw new InvalidOperationException("AZURE_AI_MODEL_DEPLOYMENT_NAME is not set.");

bool isHosted = !string.IsNullOrEmpty(Environment.GetEnvironmentVariable("FOUNDRY_HOSTING_ENVIRONMENT"));
string seedDir = Path.Combine(AppContext.BaseDirectory, "working");
string skillsDir = Path.Combine(AppContext.BaseDirectory, "skills");
string workingDir = isHosted
    ? Path.Combine(System.Environment.GetFolderPath(System.Environment.SpecialFolder.UserProfile), "working")
    : seedDir;

if (isHosted)
{
    // Foundry mounts this home per session. Seed only missing files so previous edits,
    // reports, and reorganized confirmations survive the next turn or container restart.
    Directory.SetCurrentDirectory(System.Environment.GetFolderPath(System.Environment.SpecialFolder.UserProfile));
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

string vaultDir = Path.Combine(workingDir, "confirmations");
var credential = new DefaultAzureCredential(new DefaultAzureCredentialOptions
{
    ExcludeManagedIdentityCredential = !isHosted,
});
IChatClient modelClient = new AIProjectClient(
        new Uri(endpoint),
        credential,
        new AIProjectClientOptions { RetryPolicy = new ClientRetryPolicy(3) })
    .GetProjectOpenAIClient()
    .GetProjectResponsesClientForModel(deploymentName)
    .AsIChatClient();
IChatClient chatClient = new StatelessWebSearchChatClient(modelClient);

var skillsBuilder = new AgentSkillsProviderBuilder()
    .UseFileSkills([skillsDir], scriptRunner: new SubprocessScriptRunner().RunAsync);

HttpClient? toolboxHttpClient = null;
ModelContextProtocol.Client.McpClient? toolboxMcpClient = null;
string? toolboxUrl = Environment.GetEnvironmentVariable("TOOLBOX_MCP_SERVER_URL");
if (!string.IsNullOrWhiteSpace(toolboxUrl))
{
    (toolboxMcpClient, toolboxHttpClient) = await FoundrySkills.ConnectAsync(toolboxUrl, credential);
    skillsBuilder.UseMcpSkills(toolboxMcpClient);
}

AgentSkillsProvider skillsProvider = skillsBuilder.Build();
AIAgent researchAgent = ResearchAgent.Create(chatClient);

// The policy filters common mistakes, not adversarial shell input. The hosted
// container is the isolation boundary; every shell invocation still requires approval.
await using var shell = new LocalShellExecutor(new LocalShellExecutorOptions
{
    WorkingDirectory = vaultDir,
    ConfineWorkingDirectory = true,
    Policy = new ShellPolicy(denyList:
    [
        @"\brm\s+-rf\b",
        @"\bsudo\b",
        @":\(\)\s*\{",
        @"\bmkfs\b",
        @">\s*/dev/sd",
    ]),
    Timeout = TimeSpan.FromSeconds(15),
});

// Hosted containers may not expose nested virtualization. Enable CodeAct only
// on a host that supports Hyperlight rather than silently dropping failures.
HyperlightCodeActProvider? codeAct = null;
if (string.Equals(Environment.GetEnvironmentVariable("ENABLE_HYPERLIGHT_CODEACT"), "true", StringComparison.OrdinalIgnoreCase))
{
    codeAct = new HyperlightCodeActProvider(
        HyperlightCodeActProviderOptions.CreateForWasm(PythonGuestModule.GetModulePath()));
}

List<AIContextProvider> providers = [skillsProvider, new ShellEnvironmentProvider(shell)];
if (codeAct is not null)
{
    providers.Add(codeAct);
}

AIAgent agent = chatClient.AsHarnessAgent(new HarnessAgentOptions
{
    Name = "hosted-harness-scaling-capabilities",
    Description = "Analyzes a sample portfolio with skills, shell, CodeAct, and background research.",
    FileAccessStore = new FileSystemAgentFileStore(workingDir),
    FileMemoryStore = new FileSystemAgentFileStore(Path.Combine(workingDir, "agent-file-memory")),
    DisableAgentSkillsProvider = true,
    BackgroundAgents = [researchAgent],
    ToolApprovalAgentOptions = new ToolApprovalAgentOptions
    {
        AutoApprovalRules =
        [
            FileAccessProvider.ReadOnlyToolsAutoApprovalRule,
            AgentSkillsProvider.ReadOnlyToolsAutoApprovalRule,
        ],
    },
    AgentModeProviderOptions = new AgentModeProviderOptions { DefaultMode = "execute" },
    AIContextProviders = providers,
    ChatOptions = new ChatOptions
    {
        ModelId = deploymentName,
        Instructions =
            """
            You help users examine a sample stock portfolio. Read portfolio.csv before answering
            about holdings. Load the valuation and risk-scoring skills for relevant questions.
            Delegate independent ticker research to the background agent. To organize trade
            confirmations, inspect the vault first, then use the approved shell tool to copy
            the originals into organized/year/month without changing the source files.
            Explain any simulated trade before calling place_trade. You provide information,
            not personalized investment advice.
            """,
        Tools =
        [
            StockTools.CreateGetStockPriceTool(),
            TradingTools.CreatePlaceTradeTool(),
            shell.AsAIFunction(requireApproval: true),
        ],
        Reasoning = new() { Effort = ReasoningEffort.Medium },
    },
});

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddFoundryResponses(agent);

var app = builder.Build();
app.MapFoundryResponses();

try
{
    await app.RunAsync();
}
finally
{
    codeAct?.Dispose();
    if (toolboxMcpClient is not null)
    {
        await toolboxMcpClient.DisposeAsync().ConfigureAwait(false);
    }

    toolboxHttpClient?.Dispose();
}
