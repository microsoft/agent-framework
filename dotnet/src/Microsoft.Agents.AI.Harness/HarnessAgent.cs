// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.IO;
using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// A pre-configured <see cref="DelegatingAIAgent"/> that wraps a <see cref="ChatClientAgent"/> with
/// function invocation, per-service-call chat history persistence, in-loop compaction, and a rich set
/// of default context providers and agent decorators.
/// </summary>
/// <remarks>
/// <para>
/// <see cref="HarnessAgent"/> assembles the following pipeline from a caller-supplied <see cref="IChatClient"/>:
/// <list type="number">
/// <item><description><see cref="FunctionInvokingChatClient"/> — automatic function/tool invocation.</description></item>
/// <item><description><see cref="MessageInjectingChatClient"/> — allows external code to inject messages into the conversation mid-stream.</description></item>
/// <item><description><see cref="PerServiceCallChatHistoryPersistingChatClient"/> — persists chat history after every individual service call within a function-invocation loop.</description></item>
/// <item><description><see cref="AIContextProviderChatClient"/> with a <see cref="CompactionProvider"/> — applies context-window compaction before each call so long function-invocation loops do not overflow the context window.</description></item>
/// </list>
/// </para>
/// <para>
/// By default, the following context providers are included (each can be disabled via <see cref="HarnessAgentOptions"/>):
/// <list type="bullet">
/// <item><description><see cref="TodoProvider"/> — todo list management.</description></item>
/// <item><description><see cref="AgentModeProvider"/> — agent mode tracking (plan/execute).</description></item>
/// <item><description><see cref="FileMemoryProvider"/> — file-based session memory.</description></item>
/// <item><description><see cref="FileAccessProvider"/> — shared file access.</description></item>
/// <item><description><see cref="AgentSkillsProvider"/> — skill discovery and loading.</description></item>
/// </list>
/// </para>
/// <para>
/// The agent is also wrapped with the following decorators by default (each can be disabled):
/// <list type="bullet">
/// <item><description><see cref="ToolApprovalAgent"/> — "don't ask again" tool approval rules.</description></item>
/// <item><description><see cref="OpenTelemetryAgent"/> — OpenTelemetry instrumentation.</description></item>
/// </list>
/// </para>
/// <para>
/// A <see cref="HostedWebSearchTool"/> is added to the chat options by default (can be disabled via
/// <see cref="HarnessAgentOptions.DisableWebSearch"/>).
/// </para>
/// <para>
/// The underlying <see cref="ChatClientAgent"/> is configured with
/// <see cref="ChatClientAgentOptions.UseProvidedChatClientAsIs"/> and
/// <see cref="ChatClientAgentOptions.RequirePerServiceCallChatHistoryPersistence"/> set to <see langword="true"/>
/// to match the manually-assembled pipeline.
/// </para>
/// <para>
/// When no <see cref="HarnessAgentOptions.ChatHistoryProvider"/> is supplied, the agent defaults to an
/// <see cref="InMemoryChatHistoryProvider"/> whose chat reducer applies the same compaction strategy,
/// keeping in-memory history from growing unboundedly across sessions.
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
    /// The agent wraps this client in a function-invocation, per-service-call persistence,
    /// and compaction pipeline automatically.
    /// </param>
    /// <param name="maxContextWindowTokens">
    /// The maximum number of tokens the model's context window supports (e.g., 1,050,000 for gpt-5.4).
    /// Used to configure the compaction strategy.
    /// </param>
    /// <param name="maxOutputTokens">
    /// The maximum number of output tokens the model can generate per response (e.g., 128,000 for gpt-5.4).
    /// Used to configure the compaction strategy and to limit the model's output.
    /// </param>
    /// <param name="options">
    /// Optional configuration options for the agent, including instructions override, tools,
    /// additional context providers, and chat history provider.
    /// When <see langword="null"/>, the agent uses built-in default settings.
    /// </param>
    /// <exception cref="ArgumentNullException">
    /// <paramref name="chatClient"/> is <see langword="null"/>.
    /// </exception>
    /// <exception cref="ArgumentOutOfRangeException">
    /// <paramref name="maxContextWindowTokens"/> is not positive, or
    /// <paramref name="maxOutputTokens"/> is negative or greater than or equal to <paramref name="maxContextWindowTokens"/>.
    /// </exception>
    public HarnessAgent(IChatClient chatClient, int maxContextWindowTokens, int maxOutputTokens, HarnessAgentOptions? options = null)
        : base(BuildAgent(
            Throw.IfNull(chatClient),
            maxContextWindowTokens,
            maxOutputTokens,
            options))
    {
    }

    private static AIAgent BuildAgent(IChatClient chatClient, int maxContextWindowTokens, int maxOutputTokens, HarnessAgentOptions? options)
    {
        ChatClientAgent innerAgent = BuildInnerAgent(chatClient, maxContextWindowTokens, maxOutputTokens, options);

        AIAgentBuilder builder = innerAgent.AsBuilder();

        if (options?.DisableToolApproval is not true)
        {
            builder.UseToolApproval();
        }

        if (options?.DisableOpenTelemetry is not true)
        {
            builder.UseOpenTelemetry(sourceName: options?.OpenTelemetrySourceName);
        }

        return builder.Build();
    }

    private static ChatClientAgent BuildInnerAgent(IChatClient chatClient, int maxContextWindowTokens, int maxOutputTokens, HarnessAgentOptions? options)
    {
        var compactionStrategy = new ContextWindowCompactionStrategy(
            maxContextWindowTokens: maxContextWindowTokens,
            maxOutputTokens: maxOutputTokens);

        ChatHistoryProvider chatHistoryProvider = options?.ChatHistoryProvider
            ?? new InMemoryChatHistoryProvider(new InMemoryChatHistoryProviderOptions
            {
                ChatReducer = compactionStrategy.AsChatReducer(),
            });

        string harnessInstructions = options?.HarnessInstructions ?? DefaultInstructions;
        string? agentInstructions = options?.ChatOptions?.Instructions;

        string instructions = (string.IsNullOrWhiteSpace(harnessInstructions), string.IsNullOrWhiteSpace(agentInstructions)) switch
        {
            (true, true) => harnessInstructions,
            (true, false) => agentInstructions!,
            (false, true) => harnessInstructions,
            (false, false) => $"{harnessInstructions}\n\n{agentInstructions}",
        };

        ChatOptions chatOptions = BuildChatOptions(options, instructions, maxOutputTokens);

        var compactionProvider = new CompactionProvider(compactionStrategy);

        IEnumerable<AIContextProvider> contextProviders = BuildContextProviders(options);

        return chatClient
            .AsBuilder()
            .UseFunctionInvocation(configure: options?.MaximumIterationsPerRequest is int maxIterations
                ? ficc => ficc.MaximumIterationsPerRequest = maxIterations
                : null)
            .UseMessageInjection()
            .UsePerServiceCallChatHistoryPersistence()
            .UseAIContextProviders(compactionProvider)
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
            });
    }

    private static ChatOptions BuildChatOptions(HarnessAgentOptions? options, string instructions, int maxOutputTokens)
    {
        ChatOptions result = options?.ChatOptions?.Clone() ?? new ChatOptions();
        result.Instructions = instructions;
        result.MaxOutputTokens ??= maxOutputTokens;

        if (options?.DisableWebSearch is not true)
        {
            result.Tools ??= [];
            result.Tools.Add(new HostedWebSearchTool());
        }

        return result;
    }

    private static List<AIContextProvider> BuildContextProviders(HarnessAgentOptions? options)
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
                ? new AgentSkillsProvider(source)
                : new AgentSkillsProvider(Directory.GetCurrentDirectory());

            providers.Add(skillsProvider);
        }

        if (options?.AIContextProviders is IEnumerable<AIContextProvider> userProviders)
        {
            providers.AddRange(userProviders);
        }

        return providers;
    }
}
