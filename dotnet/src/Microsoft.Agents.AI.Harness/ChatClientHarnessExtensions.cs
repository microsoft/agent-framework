// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Agents.AI;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Provides extension methods for creating a <see cref="HarnessAgent"/> from an <see cref="IChatClient"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public static class ChatClientHarnessExtensions
{
    /// <summary>
    /// Creates a new <see cref="HarnessAgent"/> that wraps this <see cref="IChatClient"/> with a pre-configured
    /// pipeline including function invocation, per-service-call chat history persistence, and in-loop compaction.
    /// </summary>
    /// <param name="chatClient">
    /// The <see cref="IChatClient"/> that provides access to the underlying AI model.
    /// </param>
    /// <param name="maxContextWindowTokens">
    /// The maximum number of tokens the model's context window supports (e.g., 1,050,000 for gpt-5.4).
    /// Used to configure the compaction strategy.
    /// </param>
    /// <param name="maxOutputTokens">
    /// The maximum number of output tokens the model can generate per response (e.g., 128,000 for gpt-5.4).
    /// Used to configure the compaction strategy.
    /// </param>
    /// <param name="options">
    /// Optional configuration options for the agent, including instructions override, tools,
    /// additional context providers, and chat history provider.
    /// When <see langword="null"/>, the agent uses built-in default settings.
    /// </param>
    /// <returns>A new <see cref="HarnessAgent"/> instance.</returns>
    public static HarnessAgent AsHarnessAgent(
        this IChatClient chatClient,
        int maxContextWindowTokens,
        int maxOutputTokens,
        HarnessAgentOptions? options = null) =>
        new(chatClient, maxContextWindowTokens, maxOutputTokens, options);
}
