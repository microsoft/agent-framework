// Copyright (c) Microsoft. All rights reserved.

// "Scaling its capabilities" — Post 3 of the "Build your own claw and agent harness with Microsoft
// Agent Framework" series.
// See: https://devblogs.microsoft.com/agent-framework/agent-harness-scaling-the-claw-or-harness-capabilities/.
//
// This sample builds on Post 2's personal finance assistant and makes it *more capable* in four ways:
//   1. Skills        — package finance know-how (valuation, risk-scoring) as discoverable SKILL.md
//                      files the agent loads on demand. Optionally fold in centrally-managed Foundry
//                      skills from a Foundry Toolbox MCP endpoint (opt-in via FOUNDRY_TOOLBOX_MCP_SERVER_URL).
//   2. Shell         — a sandboxed shell, confined to the trade-confirmation vault, that the agent
//                      uses to reorganize the accumulated confirmation files (year/month, rename,
//                      archive). Guarded by a deny-list policy and a confined working directory.
//   3. CodeAct       — the agent writes and runs Python to crunch portfolio numbers, in a sandboxed
//                      Hyperlight micro-VM (needs hardware virtualization).
//   4. Background agents — fan out a per-ticker research sub-agent so several tickers are researched
//                      concurrently, then aggregated.
//
// Special commands (handled by the shared HarnessConsole):
//   /todos  — Display the current todo list without invoking the agent.
//   /mode   — Get or set the current agent mode.
//   /exit   — End the session.

#pragma warning disable OPENAI001 // Suppress experimental API warnings for Responses API usage.
#pragma warning disable MAAI001  // Suppress experimental API warnings for Agents AI experiments.

using System.ClientModel.Primitives;
using Azure.AI.Projects;
using Azure.Identity;
using ClawSample;
using Harness.Shared.Console;
using Harness.Shared.Console.OpenAI;
using Harness.Shared.Console.ToolFormatters;
using HyperlightSandbox.Guest.Python;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hyperlight;
using Microsoft.Agents.AI.Tools.Shell;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4";

// The two folders the claw works in: the working folder (portfolio.csv, reports) and the
// trade-confirmation "vault" inside it that the shell will reorganize.
var workingDir = Path.Combine(AppContext.BaseDirectory, "working");
var vaultDir = Path.Combine(workingDir, "confirmations");
var skillsDir = Path.Combine(AppContext.BaseDirectory, "skills");

// <instructions>
var instructions =
    """
    ## Personal Finance Assistant Instructions

    You are a personal finance and investing assistant. You help the user understand their
    portfolio and watchlist, value individual stocks, gauge portfolio risk, research the market,
    and keep their records tidy.

    ### Working style

    - The user's holdings live in a file called portfolio.csv. Read it with the file_access tools
      before answering questions about their portfolio, and never modify it unless asked.
    - You have skills for valuation and risk-scoring. When a question matches a skill, load it and
      follow its instructions (read its references, run its scripts) rather than guessing.
    - When asked to research several tickers, delegate each one to the background research agent so
      they run concurrently, then summarize the findings together.
    - The user's trade confirmations accumulate in the working/confirmations folder. When asked to
      tidy or reorganize them, use the run_shell tool: inspect the folder first, then move files into
      a year/month layout and rename them to YYYY-MM-DD_TICKER_BUY|SELL.txt. Explain your plan before
      running commands that change anything.
    - To buy or sell, use the place_trade tool. This takes a real action, so the user will be asked
      to approve it before it runs — explain what you are about to do first.

    ### Important

    You provide information and analysis only — you are not a licensed financial advisor and you
    must not present your output as personalized investment advice. Remind the user to do their own
    research before making decisions.
    """;
// </instructions>

// <create_client>
// Construct an IChatClient backed by a Microsoft Foundry project (see Post 1 for details).
var credential = new DefaultAzureCredential();
var projectClient = new AIProjectClient(
    new Uri(endpoint),
    // WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
    // In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
    // latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
    credential,
    new AIProjectClientOptions { RetryPolicy = new ClientRetryPolicy(3) });

IChatClient chatClient = projectClient
    .GetProjectOpenAIClient()
    .GetResponsesClient()
    .AsIChatClient(deploymentName);
// </create_client>

// <skills>
// The harness turns a skills provider on by default (it discovers SKILL.md files from the working
// directory). Here we build our own so we can point it at this sample's skills/ folder and, when
// configured, fold in centrally-managed Foundry skills — all behind one provider.
var skillsBuilder = new AgentSkillsProviderBuilder()
    // File-based skills: valuation and risk-scoring. SubprocessScriptRunner runs their Python scripts.
    .UseFileSkills([skillsDir], scriptRunner: new SubprocessScriptRunner().RunAsync);

// Foundry skills (opt-in): discovered live from a Foundry Toolbox MCP endpoint, so they can be
// managed and updated centrally without changing or redeploying this agent.
HttpClient? toolboxHttpClient = null;
ModelContextProtocol.Client.McpClient? toolboxMcpClient = null;
var toolboxUrl = Environment.GetEnvironmentVariable("FOUNDRY_TOOLBOX_MCP_SERVER_URL");
if (!string.IsNullOrWhiteSpace(toolboxUrl))
{
    (toolboxMcpClient, toolboxHttpClient) = await FoundrySkills.ConnectAsync(toolboxUrl, credential);
    skillsBuilder.UseMcpSkills(toolboxMcpClient);
    Console.WriteLine("Foundry skills enabled (Toolbox MCP).");
}
else
{
    Console.WriteLine("Foundry skills disabled. Set FOUNDRY_TOOLBOX_MCP_SERVER_URL to enable them.");
}

AgentSkillsProvider skillsProvider = skillsBuilder.Build();
// </skills>

// <background>
// Background agents: a lean, web-search-only research sub-agent. Passing it to the harness exposes
// the background_agents_* tools so the claw can start several research tasks concurrently and
// collect the results.
AIAgent researchAgent = ResearchAgent.Create(chatClient);
// </background>

// <shell>
// A sandboxed shell, confined to the trade-confirmation vault. ConfineWorkingDirectory re-anchors
// every command to the vault, and the deny-list policy pre-filters obviously destructive commands.
// (Patterns are a UX guardrail, not a security boundary — for hard isolation use DockerShellExecutor.)
await using var shellExecutor = new LocalShellExecutor(new LocalShellExecutorOptions
{
    WorkingDirectory = vaultDir,
    ConfineWorkingDirectory = true,
    Policy = new ShellPolicy(denyList:
    [
        @"\brm\s+-rf\b",
        @"\bsudo\b",
        @":\(\)\s*\{",          // fork-bomb shape
        @"\bmkfs\b",
        @">\s*/dev/sd",
    ]),
    Timeout = TimeSpan.FromSeconds(15),
});
// </shell>

// <codeact>
// CodeAct: a sandboxed Python interpreter the model can write and run code in to crunch numbers.
// It runs on Hyperlight (a micro-VM, so it needs hardware virtualization). The guest module path is
// resolved automatically from the Hyperlight.HyperlightSandbox.Guest.Python NuGet package.
using var codeAct = new HyperlightCodeActProvider(HyperlightCodeActProviderOptions.CreateForWasm(PythonGuestModule.GetModulePath()));
// </codeact>

// <create_agent>
// Turn the chat client into a HarnessAgent. On top of Post 2's file access and approvals we add the
// four "scaling" capabilities: skills (our own provider), background agents, a confined shell, and
// CodeAct.
// The shell is wired up in two parts: the ShellEnvironmentProvider injects OS/shell/CWD info into the
// system prompt, and the shell tool is registered below in ChatOptions.
List<AIContextProvider> contextProviders = [skillsProvider, codeAct, new ShellEnvironmentProvider(shellExecutor)];

AIAgent agent = chatClient.AsHarnessAgent(new HarnessAgentOptions
{
    // File access: portfolio.csv, reports, and the confirmations vault all live under working/.
    FileAccessStore = new FileSystemAgentFileStore(workingDir),
    // We supply our own skills provider (file + optional Foundry), so turn off the default one.
    DisableAgentSkillsProvider = true,
    // Fan-out research is delegated to this background agent.
    BackgroundAgents = [researchAgent],
    // Keep reading the portfolio frictionless while writes, trades, and shell commands still prompt.
    ToolApprovalAgentOptions = new ToolApprovalAgentOptions
    {
        AutoApprovalRules = [FileAccessProvider.ReadOnlyToolsAutoApprovalRule],
    },
    // Start in "execute" mode for quick lookups and actions; switch any time with /mode plan.
    AgentModeProviderOptions = new AgentModeProviderOptions { DefaultMode = "execute" },
    // Our skills provider, CodeAct, and the shell environment provider.
    AIContextProviders = contextProviders,
    ChatOptions = new ChatOptions
    {
        Instructions = instructions,
        Tools =
        [
            StockTools.CreateGetStockPriceTool(),
            TradingTools.CreatePlaceTradeTool(),
            // The confined shell, exposed as the approval-gated run_shell tool.
            shellExecutor.AsAIFunction(requireApproval: true),
        ],
        Reasoning = new() { Effort = ReasoningEffort.Medium },
    },
});
// </create_agent>

try
{
    // <run>
    // Run the interactive console session. The default planning observers already include a tool
    // approval observer, so the place_trade and run_shell approval prompts are surfaced automatically.
    await HarnessConsole.RunAgentAsync(
        agent,
        userPrompt: "Ask me to value a stock, score your portfolio risk, research some tickers, or tidy your trade confirmations.",
        new HarnessConsoleOptions
        {
            Observers = [
                new OpenAIResponsesWebSearchDisplayObserver(),
                new OpenAIResponsesErrorObserver(),
                .. HarnessConsoleOptions.BuildObserversWithPlanning(
                    agent,
                    planModeName: "plan",
                    executionModeName: "execute",
                    toolFormatters: ToolCallFormatter.BuildDefaultToolFormatters())],
            CommandHandlers = HarnessConsoleOptions.BuildDefaultCommandHandlers(agent),
        });
    // </run>
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
