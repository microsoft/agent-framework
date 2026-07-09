// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Agents.AI;
using Microsoft.Extensions.Logging;
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
    /// pipeline including function invocation, per-service-call chat history persistence, optional in-loop compaction, and a rich set
    /// of default context providers and agent decorators.
    /// </summary>
    /// <param name="chatClient">
    /// The <see cref="IChatClient"/> that provides access to the underlying AI model.
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
    /// <returns>A new <see cref="HarnessAgent"/> instance.</returns>
    public static HarnessAgent AsHarnessAgent(
        this IChatClient chatClient,
        HarnessAgentOptions? options = null,
        ILoggerFactory? loggerFactory = null,
        IServiceProvider? services = null) =>
        new(chatClient, options, loggerFactory, services);
}
