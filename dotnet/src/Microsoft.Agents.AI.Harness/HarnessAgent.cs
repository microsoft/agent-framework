// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// A pre-configured <see cref="DelegatingAIAgent"/> that wraps a <see cref="ChatClientAgent"/> with
/// function invocation, per-service-call chat history persistence, and in-loop compaction.
/// </summary>
/// <remarks>
/// <para>
/// <see cref="HarnessAgent"/> assembles the following pipeline from a caller-supplied <see cref="IChatClient"/>:
/// <list type="number">
/// <item><description><see cref="FunctionInvokingChatClient"/> — automatic function/tool invocation.</description></item>
/// <item><description><see cref="PerServiceCallChatHistoryPersistingChatClient"/> — persists chat history after every individual service call within a function-invocation loop.</description></item>
/// <item><description><see cref="AIContextProviderChatClient"/> with a <see cref="CompactionProvider"/> — applies context-window compaction before each call so long function-invocation loops do not overflow the context window.</description></item>
/// </list>
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
        - Explain your reasoning between tool calls so the user can follow your progress.
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
    /// <exception cref="System.ArgumentNullException">
    /// <paramref name="chatClient"/> is <see langword="null"/>.
    /// </exception>
    /// <exception cref="System.ArgumentOutOfRangeException">
    /// <paramref name="maxContextWindowTokens"/> is not positive, or
    /// <paramref name="maxOutputTokens"/> is negative or greater than or equal to <paramref name="maxContextWindowTokens"/>.
    /// </exception>
    public HarnessAgent(IChatClient chatClient, int maxContextWindowTokens, int maxOutputTokens, HarnessAgentOptions? options = null)
        : base(BuildInnerAgent(
            Throw.IfNull(chatClient),
            maxContextWindowTokens,
            maxOutputTokens,
            options))
    {
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

        string instructions = options?.ChatOptions?.Instructions ?? DefaultInstructions;

        ChatOptions chatOptions = BuildChatOptions(options?.ChatOptions, instructions, maxOutputTokens);

        var compactionProvider = new CompactionProvider(compactionStrategy);

        return chatClient
            .AsBuilder()
            .UseFunctionInvocation()
            .UsePerServiceCallChatHistoryPersistence()
            .UseAIContextProviders(compactionProvider)
            .BuildAIAgent(new ChatClientAgentOptions
            {
                Id = options?.Id,
                Name = options?.Name,
                Description = options?.Description,
                ChatOptions = chatOptions,
                ChatHistoryProvider = chatHistoryProvider,
                AIContextProviders = options?.AIContextProviders,
                UseProvidedChatClientAsIs = true,
                RequirePerServiceCallChatHistoryPersistence = true,
            });
    }

    private static ChatOptions BuildChatOptions(ChatOptions? source, string instructions, int maxOutputTokens)
    {
        ChatOptions result = source?.Clone() ?? new ChatOptions();
        result.Instructions = instructions;
        result.MaxOutputTokens ??= maxOutputTokens;
        return result;
    }
}
