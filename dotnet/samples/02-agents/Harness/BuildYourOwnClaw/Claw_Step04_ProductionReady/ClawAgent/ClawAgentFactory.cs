// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel.Primitives;
using Azure.AI.Projects;
using Azure.Core;
using Azure.Identity;
using HyperlightSandbox.Guest.Python;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hyperlight;
using Microsoft.Agents.AI.Purview;
using Microsoft.Agents.AI.Tools.Shell;
using Microsoft.Extensions.AI;

namespace ClawAgent;

/// <summary>
/// Builds the shared production-ready claw agent used by all hosts.
/// </summary>
public static class ClawAgentFactory
{
    /// <summary>
    /// The OpenTelemetry source and meter name used by the claw harness agent.
    /// </summary>
    public const string OpenTelemetrySourceName = "BuildYourOwnClaw.ProductionReady.Claw";

    private const string DefaultDeploymentName = "gpt-5.4";

    private const string Instructions =
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

    /// <summary>
    /// Creates the full claw agent and returns it with the resources that must be disposed by the host.
    /// </summary>
    /// <param name="options">Optional host-specific build settings.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>The built agent and disposable resources.</returns>
    public static async Task<ClawAgentBuild> CreateAsync(ClawAgentFactoryOptions? options = null, CancellationToken cancellationToken = default)
    {
        options ??= new ClawAgentFactoryOptions();
        Action<string> log = options.Log ?? Console.WriteLine;

        string endpoint = options.ProjectEndpoint
            ?? Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
            ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
        string deploymentName = options.DeploymentName
            ?? Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME")
            ?? DefaultDeploymentName;

        string workingDir = options.WorkingDirectory ?? Path.Combine(AppContext.BaseDirectory, "working");
        string vaultDir = Path.Combine(workingDir, "confirmations");
        string skillsDir = options.SkillsDirectory ?? Path.Combine(AppContext.BaseDirectory, "skills");

        TokenCredential credential = options.Credential ?? new DefaultAzureCredential();
        AIProjectClient projectClient = new(
            new Uri(endpoint),
            credential,
            new AIProjectClientOptions { RetryPolicy = new ClientRetryPolicy(3) });

        IChatClient chatClient = projectClient
            .GetProjectOpenAIClient()
            .GetResponsesClient()
            .AsIChatClient(deploymentName);

        bool purviewEnabled = false;
        string? purviewClientAppId = Environment.GetEnvironmentVariable("PURVIEW_CLIENT_APP_ID");
        TokenCredential? purviewCredential = options.PurviewCredential;
        if (purviewCredential is null && !string.IsNullOrWhiteSpace(purviewClientAppId))
        {
            purviewCredential = new InteractiveBrowserCredential(
                new InteractiveBrowserCredentialOptions { ClientId = purviewClientAppId });
        }

        if (purviewCredential is not null)
        {
            chatClient = chatClient
                .AsBuilder()
                .WithPurview(purviewCredential, new PurviewSettings("Claw"))
                .Build();
            purviewEnabled = true;
            log(options.PurviewCredential is not null
                ? "Purview enabled (host-provided credential). "
                : "Purview enabled (interactive browser credential). ");
        }
        else
        {
            log("Purview disabled. Set PURVIEW_CLIENT_APP_ID to enable governance checks.");
        }

        var skillsBuilder = new AgentSkillsProviderBuilder()
            .UseFileSkills([skillsDir], scriptRunner: new SubprocessScriptRunner().RunAsync);

        HttpClient? toolboxHttpClient = null;
        ModelContextProtocol.Client.McpClient? toolboxMcpClient = null;
        string? toolboxUrl = Environment.GetEnvironmentVariable("TOOLBOX_MCP_SERVER_URL");
        bool foundrySkillsEnabled = false;
        if (!string.IsNullOrWhiteSpace(toolboxUrl))
        {
            (toolboxMcpClient, toolboxHttpClient) = await FoundrySkills.ConnectAsync(
                toolboxUrl,
                credential,
                options.FoundryCallIdProvider,
                cancellationToken).ConfigureAwait(false);
            skillsBuilder.UseMcpSkills(toolboxMcpClient);
            foundrySkillsEnabled = true;
            log("Foundry skills enabled (Toolbox MCP). ");
        }
        else
        {
            log("Foundry skills disabled. Set TOOLBOX_MCP_SERVER_URL to enable them.");
        }

        skillsBuilder.UseOptions((options) =>
        {
            options.DisableLoadSkillApproval = true;
            options.DisableReadSkillResourceApproval = true;
        });

        AgentSkillsProvider skillsProvider = skillsBuilder.Build();
        AIAgent researchAgent = ResearchAgent.Create(chatClient);

        // Shell access is a powerful capability. It is confined to the local vault directory with a
        // deny-list here, but on shared/hosted deployments it is disabled entirely (see hosted host).
        LocalShellExecutor? shell = null;
        if (options.EnableShell)
        {
            shell = new LocalShellExecutor(new LocalShellExecutorOptions
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
            log("Shell enabled (confined to the confirmations vault). ");
        }
        else
        {
            log("Shell disabled. ");
        }

        // File access is enabled by default via a filesystem-backed store. Hosts may disable it or
        // supply an external store (for example, backed by blob storage) instead of the container disk.
        AgentFileStore? fileStore = null;
        if (options.EnableFileAccess)
        {
            fileStore = options.FileStore ?? new FileSystemAgentFileStore(workingDir);
            log(options.FileStore is not null
                ? "File access enabled (custom AgentFileStore). "
                : "File access enabled (local filesystem). ");
        }
        else
        {
            log("File access disabled. ");
        }

        // CodeAct gives the model a sandboxed code interpreter. By default we use the Hyperlight
        // provider, which runs guest code in a VM-isolated micro-sandbox — great for local hosts, but
        // it needs a hypervisor (KVM) and FUSE, which an unprivileged Foundry hosted container does not
        // expose. Hosts running in such an environment supply their own provider via
        // options.CodeActProvider (for example a LocalCodeActProvider that relies on the container
        // itself as the isolation boundary) or disable CodeAct entirely with EnableCodeAct = false.
        AIContextProvider? codeAct = null;
        if (options.EnableCodeAct)
        {
            codeAct = options.CodeActProvider
                ?? new HyperlightCodeActProvider(HyperlightCodeActProviderOptions.CreateForWasm(PythonGuestModule.GetModulePath()));
            log(options.CodeActProvider is not null
                ? "CodeAct enabled (custom provider). "
                : "CodeAct enabled (Hyperlight VM-isolated sandbox). ");
        }
        else
        {
            log("CodeAct disabled. ");
        }

        List<AIContextProvider> contextProviders = [skillsProvider];
        if (codeAct is not null)
        {
            contextProviders.Add(codeAct);
        }

        List<AITool> tools =
        [
            StockTools.CreateGetStockPriceTool(),
            TradingTools.CreatePlaceTradeTool(),
        ];

        // Shell support is composed explicitly: the context provider tells the model about the
        // environment, while the approval-gated function exposes command execution.
        if (shell is not null)
        {
            contextProviders.Add(new ShellEnvironmentProvider(shell));
            tools.Add(shell.AsAIFunction(requireApproval: true));
        }

        List<Func<ToolAutoApprovalRuleContext, ValueTask<bool>>> autoApprovalRules =
        [
            FileAccessProvider.ReadOnlyToolsAutoApprovalRule,
        ];
        if (options.AdditionalToolAutoApprovalRules is not null)
        {
            autoApprovalRules.AddRange(options.AdditionalToolAutoApprovalRules);
        }

        AIAgent agent = chatClient.AsHarnessAgent(new HarnessAgentOptions
        {
            Name = options.AgentName,
            Description = options.AgentDescription,
            FileAccessStore = fileStore,
            DisableAgentSkillsProvider = true,
            BackgroundAgents = [researchAgent],
            OpenTelemetrySourceName = OpenTelemetrySourceName,
            ToolApprovalAgentOptions = new ToolApprovalAgentOptions
            {
                AutoApprovalRules = autoApprovalRules,
            },
            AgentModeProviderOptions = new AgentModeProviderOptions { DefaultMode = "execute" },
            AIContextProviders = contextProviders,
            ChatOptions = new ChatOptions
            {
                Instructions = Instructions,
                Tools = tools,
                Reasoning = new() { Effort = ReasoningEffort.Medium },
            },
        });

        List<IDisposable> disposables = [];
        if (codeAct is IDisposable disposableCodeAct)
        {
            disposables.Add(disposableCodeAct);
        }

        if (toolboxHttpClient is not null)
        {
            disposables.Add(toolboxHttpClient);
        }

        if (chatClient is IDisposable disposableChatClient)
        {
            disposables.Add(disposableChatClient);
        }

        List<IAsyncDisposable> asyncDisposables = [];
        if (shell is not null)
        {
            asyncDisposables.Add(shell);
        }

        if (toolboxMcpClient is not null)
        {
            asyncDisposables.Add(toolboxMcpClient);
        }

        return new ClawAgentBuild(agent, foundrySkillsEnabled, purviewEnabled, disposables, asyncDisposables);
    }
}
