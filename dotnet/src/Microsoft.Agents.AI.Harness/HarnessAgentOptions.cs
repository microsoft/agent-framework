// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents configuration options for a <see cref="HarnessAgent"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class HarnessAgentOptions
{
    /// <summary>
    /// Gets or sets the agent id.
    /// </summary>
    public string? Id { get; set; }

    /// <summary>
    /// Gets or sets the agent name.
    /// </summary>
    public string? Name { get; set; }

    /// <summary>
    /// Gets or sets the agent description.
    /// </summary>
    public string? Description { get; set; }

    /// <summary>
    /// Gets or sets additional chat options such as tools for the agent to use.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Use <see cref="ChatOptions.Tools"/> to supply additional tools the agent can invoke.
    /// </para>
    /// <para>
    /// Use <see cref="ChatOptions.Instructions"/> to override the <see cref="HarnessAgent"/>'s built-in
    /// default instructions. When <see cref="ChatOptions.Instructions"/> is <see langword="null"/> or not set,
    /// the default instructions are used.
    /// </para>
    /// </remarks>
    public ChatOptions? ChatOptions { get; set; }

    /// <summary>
    /// Gets or sets the <see cref="ChatHistoryProvider"/> to use for storing chat history.
    /// </summary>
    /// <remarks>
    /// When <see langword="null"/>, the agent defaults to an <see cref="InMemoryChatHistoryProvider"/>
    /// configured with a compaction-based chat reducer derived from the <c>maxContextWindowTokens</c>
    /// and <c>maxOutputTokens</c> constructor parameters of <see cref="HarnessAgent"/>.
    /// </remarks>
    public ChatHistoryProvider? ChatHistoryProvider { get; set; }

    /// <summary>
    /// Gets or sets additional <see cref="AIContextProvider"/> instances to include in the agent pipeline.
    /// </summary>
    /// <remarks>
    /// These providers are passed to the underlying <see cref="ChatClientAgent"/> via
    /// <see cref="ChatClientAgentOptions.AIContextProviders"/>.
    /// </remarks>
    public IEnumerable<AIContextProvider>? AIContextProviders { get; set; }
}
