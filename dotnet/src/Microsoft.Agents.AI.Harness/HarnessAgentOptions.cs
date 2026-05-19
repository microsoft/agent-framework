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
    /// Use <see cref="ChatOptions.Instructions"/> to provide agent-specific instructions (e.g., research methodology,
    /// data analysis workflow). These are combined with <see cref="HarnessInstructions"/> to form the final instructions
    /// sent to the model: harness instructions appear first, followed by agent-specific instructions.
    /// When <see cref="ChatOptions.Instructions"/> is <see langword="null"/>, only <see cref="HarnessInstructions"/>
    /// (or the default) is used.
    /// </para>
    /// </remarks>
    public ChatOptions? ChatOptions { get; set; }

    /// <summary>
    /// Gets or sets the harness-level instructions that control general tool usage and behavior patterns.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Harness instructions provide guidance on how to use tools, explain reasoning, and structure work.
    /// They are combined with <see cref="ChatOptions"/>.<see cref="ChatOptions.Instructions"/> (agent-specific instructions)
    /// to produce the final instructions sent to the model: harness instructions first, then agent-specific instructions.
    /// </para>
    /// <para>
    /// When <see langword="null"/> (the default), <see cref="HarnessAgent.DefaultInstructions"/> is used.
    /// Set to <see cref="string.Empty"/> to omit harness instructions entirely.
    /// </para>
    /// </remarks>
    public string? HarnessInstructions { get; set; }

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

    /// <summary>
    /// Gets or sets the maximum number of function-invocation loop iterations per request.
    /// </summary>
    /// <remarks>
    /// When set, this value is passed to <see cref="FunctionInvokingChatClient.MaximumIterationsPerRequest"/>.
    /// When <see langword="null"/>, the <see cref="FunctionInvokingChatClient"/> default is used.
    /// </remarks>
    public int? MaximumIterationsPerRequest { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether the <see cref="ToolApprovalAgent"/> wrapper is disabled.
    /// </summary>
    /// <remarks>
    /// When <see langword="false"/> (the default), the agent is wrapped with tool approval middleware
    /// that supports "don't ask again" auto-approval rules.
    /// </remarks>
    public bool DisableToolApproval { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether the <see cref="FileMemoryProvider"/> is disabled.
    /// </summary>
    /// <remarks>
    /// When <see langword="false"/> (the default), a <see cref="FileMemoryProvider"/> is included in the
    /// agent's context providers, using either <see cref="FileMemoryStore"/> or a default
    /// <see cref="FileSystemAgentFileStore"/> rooted at <c>{cwd}/agent-file-memory/{timestamp}_{guid}</c>.
    /// </remarks>
    public bool DisableFileMemory { get; set; }

    /// <summary>
    /// Gets or sets a custom <see cref="AgentFileStore"/> for the <see cref="FileMemoryProvider"/>.
    /// </summary>
    /// <remarks>
    /// When <see langword="null"/> and <see cref="DisableFileMemory"/> is <see langword="false"/>,
    /// a default <see cref="FileSystemAgentFileStore"/> is created.
    /// This property is ignored when <see cref="DisableFileMemory"/> is <see langword="true"/>.
    /// </remarks>
    public AgentFileStore? FileMemoryStore { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether the <see cref="FileAccessProvider"/> is disabled.
    /// </summary>
    /// <remarks>
    /// When <see langword="false"/> (the default), a <see cref="FileAccessProvider"/> is included in the
    /// agent's context providers, using either <see cref="FileAccessStore"/> or a default
    /// <see cref="FileSystemAgentFileStore"/> rooted at <c>{cwd}/working</c>.
    /// </remarks>
    public bool DisableFileAccess { get; set; }

    /// <summary>
    /// Gets or sets a custom <see cref="AgentFileStore"/> for the <see cref="FileAccessProvider"/>.
    /// </summary>
    /// <remarks>
    /// When <see langword="null"/> and <see cref="DisableFileAccess"/> is <see langword="false"/>,
    /// a default <see cref="FileSystemAgentFileStore"/> is created.
    /// This property is ignored when <see cref="DisableFileAccess"/> is <see langword="true"/>.
    /// </remarks>
    public AgentFileStore? FileAccessStore { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether the <see cref="HostedWebSearchTool"/> is disabled.
    /// </summary>
    /// <remarks>
    /// When <see langword="false"/> (the default), a <see cref="HostedWebSearchTool"/> is added
    /// to <see cref="ChatOptions"/>.<see cref="ChatOptions.Tools"/>.
    /// </remarks>
    public bool DisableWebSearch { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether the <see cref="TodoProvider"/> is disabled.
    /// </summary>
    /// <remarks>
    /// When <see langword="false"/> (the default), a <see cref="TodoProvider"/> is included
    /// in the agent's context providers for tracking work items.
    /// </remarks>
    public bool DisableTodoProvider { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether the <see cref="AgentModeProvider"/> is disabled.
    /// </summary>
    /// <remarks>
    /// When <see langword="false"/> (the default), an <see cref="AgentModeProvider"/> is included
    /// in the agent's context providers. Use <see cref="AgentModeProviderOptions"/> to configure
    /// custom modes.
    /// </remarks>
    public bool DisableAgentModeProvider { get; set; }

    /// <summary>
    /// Gets or sets custom options for the <see cref="AgentModeProvider"/>.
    /// </summary>
    /// <remarks>
    /// When <see langword="null"/>, the <see cref="AgentModeProvider"/> uses its built-in default
    /// modes ("plan" and "execute"). This property is ignored when
    /// <see cref="DisableAgentModeProvider"/> is <see langword="true"/>.
    /// </remarks>
    public AgentModeProviderOptions? AgentModeProviderOptions { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether the <see cref="AgentSkillsProvider"/> is disabled.
    /// </summary>
    /// <remarks>
    /// When <see langword="false"/> (the default), an <see cref="AgentSkillsProvider"/> is included
    /// in the agent's context providers. Use <see cref="AgentSkillsSource"/> to provide a custom
    /// skills source; otherwise, the provider defaults to file-based skill discovery from the current
    /// working directory.
    /// </remarks>
    public bool DisableAgentSkillsProvider { get; set; }

    /// <summary>
    /// Gets or sets a custom <see cref="AI.AgentSkillsSource"/> for the <see cref="AgentSkillsProvider"/>.
    /// </summary>
    /// <remarks>
    /// When <see langword="null"/> and <see cref="DisableAgentSkillsProvider"/> is <see langword="false"/>,
    /// the provider defaults to file-based skill discovery from the current working directory.
    /// This property is ignored when <see cref="DisableAgentSkillsProvider"/> is <see langword="true"/>.
    /// </remarks>
    public AgentSkillsSource? AgentSkillsSource { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether the <see cref="OpenTelemetryAgent"/> wrapper is disabled.
    /// </summary>
    /// <remarks>
    /// When <see langword="false"/> (the default), the agent is wrapped with an
    /// <see cref="OpenTelemetryAgent"/> that provides OpenTelemetry instrumentation
    /// following the Semantic Conventions for Generative AI systems.
    /// </remarks>
    public bool DisableOpenTelemetry { get; set; }

    /// <summary>
    /// Gets or sets the OpenTelemetry source name used by the <see cref="OpenTelemetryAgent"/> wrapper.
    /// </summary>
    /// <remarks>
    /// When <see langword="null"/> (the default), the framework's default source name
    /// (<c>"Experimental.Microsoft.Agents.AI"</c>) is used.
    /// Set this to a custom value to enable filtering spans from a specific <see cref="System.Diagnostics.ActivitySource"/>
    /// in your <c>TracerProvider</c> configuration.
    /// This property is ignored when <see cref="DisableOpenTelemetry"/> is <see langword="true"/>.
    /// </remarks>
    public string? OpenTelemetrySourceName { get; set; }
}
