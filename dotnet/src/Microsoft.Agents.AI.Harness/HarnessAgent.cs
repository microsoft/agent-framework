// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.IO;
using System.Linq;
using Microsoft.Agents.AI.Compaction;
#if NET
using Microsoft.Agents.AI.Tools.Shell;
#endif
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// A pre-configured <see cref="DelegatingAIAgent"/> that wraps a <see cref="ChatClientAgent"/> with
/// function invocation, per-service-call chat history persistence, optional in-loop compaction, and a rich set
/// of default context providers and agent decorators.
/// </summary>
/// <remarks>
/// <para>
/// <see cref="HarnessAgent"/> provides an opinionated, batteries-included agent suitable for
/// interactive agentic scenarios such as research, coding, data analysis, and general task automation.
/// It assembles a full pipeline from a caller-supplied <see cref="IChatClient"/> so that callers
/// only need to configure the parts they want to customize.
/// </para>
/// <para>
/// <strong>Chat client pipeline (inner to outer):</strong>
/// <list type="number">
/// <item><description><see cref="FunctionInvokingChatClient"/> — automatic function/tool invocation with configurable iteration limits.</description></item>
/// <item><description><see cref="MessageInjectingChatClient"/> — allows external code to inject messages into the conversation mid-stream (e.g., for user interrupts).</description></item>
/// <item><description><see cref="PerServiceCallChatHistoryPersistingChatClient"/> — persists chat history after every individual service call within a function-invocation loop, enabling crash recovery and history inspection.</description></item>
/// <item><description><see cref="AIContextProviderChatClient"/> with a <see cref="CompactionProvider"/> — applies context-window compaction before each call so long function-invocation loops do not overflow the context window. Only included when <see cref="HarnessAgentOptions.MaxContextWindowTokens"/> and <see cref="HarnessAgentOptions.MaxOutputTokens"/> are both provided.</description></item>
/// </list>
/// </para>
/// <para>
/// <strong>Context providers (each enabled by default, individually disableable via <see cref="HarnessAgentOptions"/>):</strong>
/// <list type="bullet">
/// <item><description><see cref="TodoProvider"/> — persistent todo list that the agent uses to track multi-step plans. Disable with <see cref="HarnessAgentOptions.DisableTodoProvider"/>.</description></item>
/// <item><description><see cref="AgentModeProvider"/> — mode tracking (e.g., "plan" vs "execute") that the agent uses to structure its work. Disable with <see cref="HarnessAgentOptions.DisableAgentModeProvider"/>.</description></item>
/// <item><description><see cref="FileMemoryProvider"/> — file-based session memory allowing the agent to persist notes and artifacts across turns. Disable with <see cref="HarnessAgentOptions.DisableFileMemory"/>.</description></item>
/// <item><description><see cref="FileAccessProvider"/> — shared file access providing read/write tools for a working directory. Disable with <see cref="HarnessAgentOptions.DisableFileAccess"/>.</description></item>
/// <item><description><see cref="AgentSkillsProvider"/> — discovers and loads skill definitions from the file system, enabling dynamic tool sets. Disable with <see cref="HarnessAgentOptions.DisableAgentSkillsProvider"/>.</description></item>
/// </list>
/// </para>
/// <para>
/// <strong>Optional context providers (enabled via <see cref="HarnessAgentOptions"/>):</strong>
/// <list type="bullet">
/// <item><description><see cref="BackgroundAgentsProvider"/> — enables delegation to background agents for parallel work. Enable by setting <see cref="HarnessAgentOptions.BackgroundAgents"/>.</description></item>
/// <item><description><c>ShellEnvironmentProvider</c> — injects OS/shell/CWD information and a shell execution tool. Enable by setting <c>HarnessAgentOptions.ShellExecutor</c> (.NET only).</description></item>
/// </list>
/// </para>
/// <para>
/// <strong>Agent decorators (each enabled by default, individually disableable):</strong>
/// <list type="bullet">
/// <item><description><see cref="ToolApprovalAgent"/> — "don't ask again" tool approval rules enabling safe unattended execution. Disable with <see cref="HarnessAgentOptions.DisableToolApproval"/>.</description></item>
/// <item><description><see cref="OpenTelemetryAgent"/> — OpenTelemetry instrumentation following semantic conventions for generative AI. Disable with <see cref="HarnessAgentOptions.DisableOpenTelemetry"/>.</description></item>
/// </list>
/// </para>
/// <para>
/// <strong>Default tools:</strong>
/// <list type="bullet">
/// <item><description><see cref="HostedWebSearchTool"/> — a hosted web search tool added to chat options by default. Disable with <see cref="HarnessAgentOptions.DisableWebSearch"/>.</description></item>
/// </list>
/// </para>
/// <para>
/// <strong>Chat history:</strong> When no <see cref="HarnessAgentOptions.ChatHistoryProvider"/> is supplied,
/// the agent defaults to an <see cref="InMemoryChatHistoryProvider"/>. If compaction is enabled, the provider
/// is configured with a compaction-based chat reducer to keep in-memory history bounded. Otherwise, no reducer
/// is applied.
/// </para>
/// <para>
/// <strong>Default instructions:</strong> The agent includes built-in system instructions (<see cref="DefaultInstructions"/>)
/// that guide general tool usage and reasoning patterns. These can be overridden via <see cref="HarnessAgentOptions.HarnessInstructions"/>
/// and combined with agent-specific instructions via <see cref="ChatOptions.Instructions"/>.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class HarnessAgent : DelegatingAIAgent
{
    /// <summary>
    /// The built-in default system instructions used when <see cref="ChatOptions.Instructions"/> is not set.
    /// </summary>
    public const string DefaultInstructions =
        """
        You are a helpful AI assistant that uses tools to complete tasks.

        ## General guidelines

        - Think through the task before acting. Break complex work into clear steps.
        - Use the tools available to you to gather information, perform actions, and verify results.
        - Explain your reasoning and thought process as you work through tasks.
        - Explain what you learned and what you are going to do next between tool calls, so the user can follow along with your thought process.
        - Avoid making more than 4 tool calls in a row without explaining what you are doing.
        - If a tool call fails or returns unexpected results, adapt your approach rather than repeating the same call.
        - When you have completed the task, present a clear and concise summary of what you did and what you found.
        """;

    /// <summary>
    /// Initializes a new instance of the <see cref="HarnessAgent"/> class.
    /// </summary>
    /// <param name="chatClient">
    /// The <see cref="IChatClient"/> that provides access to the underlying AI model.
    /// The agent wraps this client in a function-invocation and per-service-call persistence pipeline.
    /// When compaction is enabled via <paramref name="options"/>, a compaction decorator is also added.
    /// </param>
    /// <param name="options">
    /// Optional configuration options for the agent, including instructions override, tools,
    /// additional context providers, chat history provider, and compaction settings.
    /// When <see langword="null"/>, the agent uses built-in default settings with compaction disabled.
    /// </param>
    /// <param name="loggerFactory">
    /// Optional logger factory for creating loggers used by the agent and its components.
    /// </param>
    /// <param name="services">
    /// Optional service provider for resolving dependencies required by AI functions and other agent components.
    /// </param>
    /// <exception cref="ArgumentNullException">
    /// <paramref name="chatClient"/> is <see langword="null"/>.
    /// </exception>
    /// <exception cref="ArgumentOutOfRangeException">
    /// <see cref="HarnessAgentOptions.MaxContextWindowTokens"/> is not positive, or
    /// <see cref="HarnessAgentOptions.MaxOutputTokens"/> is negative or greater than or equal to
    /// <see cref="HarnessAgentOptions.MaxContextWindowTokens"/> (when both are provided).
    /// </exception>
    public HarnessAgent(IChatClient chatClient, HarnessAgentOptions? options = null, ILoggerFactory? loggerFactory = null, IServiceProvider? services = null)
        : base(BuildAgent(
            Throw.IfNull(chatClient),
            options,
            loggerFactory,
            services))
    {
    }

    private static AIAgent BuildAgent(IChatClient chatClient, HarnessAgentOptions? options, ILoggerFactory? loggerFactory, IServiceProvider? services)
    {
        ChatClientAgent innerAgent = BuildInnerAgent(chatClient, options, loggerFactory, services);

        AIAgentBuilder builder = innerAgent.AsBuilder();

        if (options?.DisableToolApproval is not true)
        {
            builder.UseToolApproval(options?.ToolApprovalAgentOptions);
        }

        if (options?.DisableOpenTelemetry is not true)
        {
            builder.UseOpenTelemetry(sourceName: options?.OpenTelemetrySourceName);
        }

        return builder.Build(services);
    }

    private static ChatClientAgent BuildInnerAgent(IChatClient chatClient, HarnessAgentOptions? options, ILoggerFactory? loggerFactory, IServiceProvider? services)
    {
        // Determine compaction strategy:
        // 1. DisableCompaction = true → no compaction
        // 2. Custom CompactionStrategy provided → use it (ignore token params)
        // 3. Both token params provided → build default ContextWindowCompactionStrategy
        // 4. Otherwise → no compaction
        CompactionStrategy? compactionStrategy = null;
        if (options?.DisableCompaction is not true)
        {
            if (options?.CompactionStrategy is CompactionStrategy customStrategy)
            {
                compactionStrategy = customStrategy;
            }
            else if (options?.MaxContextWindowTokens is int maxCtx && options?.MaxOutputTokens is int maxOut)
            {
                compactionStrategy = new ContextWindowCompactionStrategy(
                    maxContextWindowTokens: maxCtx,
                    maxOutputTokens: maxOut);
            }
        }

        ChatHistoryProvider chatHistoryProvider = options?.ChatHistoryProvider
            ?? (compactionStrategy is not null
                ? new InMemoryChatHistoryProvider(new InMemoryChatHistoryProviderOptions
                {
                    ChatReducer = compactionStrategy.AsChatReducer(),
                })
                : new InMemoryChatHistoryProvider());

        string harnessInstructions = options?.HarnessInstructions ?? DefaultInstructions;
        string? agentInstructions = options?.ChatOptions?.Instructions;

        string instructions = (string.IsNullOrWhiteSpace(harnessInstructions), string.IsNullOrWhiteSpace(agentInstructions)) switch
        {
            (true, true) => harnessInstructions,
            (true, false) => agentInstructions!,
            (false, true) => harnessInstructions,
            (false, false) => $"{harnessInstructions}\n\n{agentInstructions}",
        };

        ChatOptions chatOptions = BuildChatOptions(options, instructions, options?.MaxOutputTokens);

        CompactionProvider? compactionProvider = compactionStrategy is not null
            ? new CompactionProvider(compactionStrategy, loggerFactory: loggerFactory)
            : null;

        IEnumerable<AIContextProvider> contextProviders = BuildContextProviders(options, loggerFactory);

        ChatClientBuilder chatClientBuilder = chatClient.AsBuilder();

        if (options?.DisableNonApprovalRequiredFunctionBypassing is not true)
        {
            chatClientBuilder.UseNonApprovalRequiredFunctionBypassing();
        }

        ChatClientBuilder pipeline = chatClientBuilder
            .UseFunctionInvocation(loggerFactory, configure: options?.MaximumIterationsPerRequest is int maxIterations
                ? ficc => ficc.MaximumIterationsPerRequest = maxIterations
                : null)
            .UseMessageInjection()
            .UsePerServiceCallChatHistoryPersistence();

        if (compactionProvider is not null)
        {
            pipeline = pipeline.UseAIContextProviders(compactionProvider);
        }

        return pipeline
            .BuildAIAgent(new ChatClientAgentOptions
            {
                Id = options?.Id,
                Name = options?.Name,
                Description = options?.Description,
                ChatOptions = chatOptions,
                ChatHistoryProvider = chatHistoryProvider,
                AIContextProviders = contextProviders,
                UseProvidedChatClientAsIs = true,
                RequirePerServiceCallChatHistoryPersistence = true,
                WarnOnChatHistoryProviderConflict = false,
                ThrowOnChatHistoryProviderConflict = false,
            },
            loggerFactory,
            services);
    }

    private static ChatOptions BuildChatOptions(HarnessAgentOptions? options, string instructions, int? maxOutputTokens)
    {
        ChatOptions result = options?.ChatOptions?.Clone() ?? new ChatOptions();
        result.Instructions = instructions;

        if (maxOutputTokens.HasValue)
        {
            result.MaxOutputTokens ??= maxOutputTokens.Value;
        }

        if (options?.DisableWebSearch is not true)
        {
            result.Tools ??= [];
            result.Tools.Add(new HostedWebSearchTool());
        }

#if NET
        if (options?.ShellExecutor is ShellExecutor shellExecutor)
        {
            result.Tools ??= [];
            result.Tools.Add(shellExecutor.AsAIFunction());
        }
#endif

        return result;
    }

    private static List<AIContextProvider> BuildContextProviders(HarnessAgentOptions? options, ILoggerFactory? loggerFactory)
    {
        var providers = new List<AIContextProvider>();

        if (options?.DisableTodoProvider is not true)
        {
            providers.Add(new TodoProvider());
        }

        if (options?.DisableAgentModeProvider is not true)
        {
            providers.Add(new AgentModeProvider(options?.AgentModeProviderOptions));
        }

        if (options?.DisableFileMemory is not true)
        {
            AgentFileStore fileMemoryStore = options?.FileMemoryStore
                ?? new FileSystemAgentFileStore(
                    Path.Combine(Directory.GetCurrentDirectory(), "agent-file-memory"));

            providers.Add(new FileMemoryProvider(
                fileMemoryStore,
                _ => new FileMemoryState
                {
                    WorkingFolder = DateTime.UtcNow.ToString("yyyyMMdd_HHmmss") + "_" + Guid.NewGuid().ToString(),
                }));
        }

        if (options?.DisableFileAccess is not true)
        {
            AgentFileStore fileAccessStore = options?.FileAccessStore
                ?? new FileSystemAgentFileStore(
                    Path.Combine(Directory.GetCurrentDirectory(), "working"));

            providers.Add(new FileAccessProvider(fileAccessStore));
        }

        if (options?.DisableAgentSkillsProvider is not true)
        {
            AgentSkillsProvider skillsProvider = options?.AgentSkillsSource is AgentSkillsSource source
                ? new AgentSkillsProvider(source, loggerFactory: loggerFactory)
                : new AgentSkillsProvider(Directory.GetCurrentDirectory(), loggerFactory: loggerFactory);

            providers.Add(skillsProvider);
        }

        if (options?.BackgroundAgents is IEnumerable<AIAgent> backgroundAgents)
        {
            var materializedAgents = backgroundAgents.ToList();
            if (materializedAgents.Count > 0)
            {
                providers.Add(new BackgroundAgentsProvider(materializedAgents, options.BackgroundAgentsProviderOptions));
            }
        }

#if NET
        if (options?.ShellExecutor is ShellExecutor shellExecutor)
        {
            providers.Add(new ShellEnvironmentProvider(shellExecutor, options.ShellEnvironmentProviderOptions));
        }
#endif

        if (options?.AIContextProviders is IEnumerable<AIContextProvider> userProviders)
        {
            providers.AddRange(userProviders);
        }

        return providers;
    }
}
