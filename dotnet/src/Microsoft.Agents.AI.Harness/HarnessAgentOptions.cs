// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Agents.AI.Compaction;
#if NET
using Microsoft.Agents.AI.Tools.Shell;
#endif
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
    /// Gets or sets the maximum number of tokens the model's context window supports (e.g., 1,050,000 for gpt-5.4).
    /// </summary>
    /// <remarks>
    /// <para>
    /// When both <see cref="MaxContextWindowTokens"/> and <see cref="MaxOutputTokens"/> are provided (and no
    /// custom <see cref="CompactionStrategy"/> is set), a default <see cref="ContextWindowCompactionStrategy"/>
    /// is constructed from these values to prevent function-invocation loops from overflowing the context window.
    /// </para>
    /// <para>
    /// Ignored when <see cref="CompactionStrategy"/> is provided or when <see cref="DisableCompaction"/> is
    /// <see langword="true"/>.
    /// </para>
    /// </remarks>
    public int? MaxContextWindowTokens { get; set; }

    /// <summary>
    /// Gets or sets the maximum number of output tokens the model can generate per response (e.g., 128,000 for gpt-5.4).
    /// </summary>
    /// <remarks>
    /// <para>
    /// When set, this value is used as the default for <see cref="ChatOptions"/>.<see cref="ChatOptions.MaxOutputTokens"/>
    /// when not explicitly configured.
    /// </para>
    /// <para>
    /// For compaction purposes, this value is used together with <see cref="MaxContextWindowTokens"/> to construct a
    /// default <see cref="ContextWindowCompactionStrategy"/> — but only when no custom <see cref="CompactionStrategy"/>
    /// is provided and <see cref="DisableCompaction"/> is <see langword="false"/>.
    /// </para>
    /// </remarks>
    public int? MaxOutputTokens { get; set; }

    /// <summary>
    /// Gets or sets a custom <see cref="Compaction.CompactionStrategy"/> to use for in-loop context-window compaction.
    /// </summary>
    /// <remarks>
    /// <para>
    /// When provided, this strategy is used directly and <see cref="MaxContextWindowTokens"/> and
    /// <see cref="MaxOutputTokens"/> are ignored for compaction purposes (<see cref="MaxOutputTokens"/> is still
    /// used as the default for <see cref="ChatOptions"/>.<see cref="ChatOptions.MaxOutputTokens"/> if set).
    /// </para>
    /// <para>
    /// When <see langword="null"/> and both <see cref="MaxContextWindowTokens"/> and <see cref="MaxOutputTokens"/>
    /// are provided, a default <see cref="ContextWindowCompactionStrategy"/> is constructed from those values.
    /// </para>
    /// <para>
    /// This property is ignored when <see cref="DisableCompaction"/> is <see langword="true"/>.
    /// </para>
    /// </remarks>
    public CompactionStrategy? CompactionStrategy { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether in-loop compaction is disabled.
    /// </summary>
    /// <remarks>
    /// When <see langword="true"/>, compaction is disabled regardless of <see cref="CompactionStrategy"/>,
    /// <see cref="MaxContextWindowTokens"/>, or <see cref="MaxOutputTokens"/> settings. No
    /// <see cref="CompactionProvider"/> is added to the chat client pipeline, and the default
    /// <see cref="InMemoryChatHistoryProvider"/> is configured without a chat reducer.
    /// </remarks>
    public bool DisableCompaction { get; set; }

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
    /// When <see langword="null"/>, the agent defaults to an <see cref="InMemoryChatHistoryProvider"/>.
    /// If <see cref="MaxContextWindowTokens"/> and <see cref="MaxOutputTokens"/> are both provided,
    /// the default provider is configured with a compaction-based chat reducer; otherwise, no reducer is applied.
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
    /// Gets or sets the ordered collection of <see cref="LoopEvaluator"/> instances that, when supplied, cause the
    /// <see cref="HarnessAgent"/> to be wrapped in a <see cref="LoopAgent"/> decorator.
    /// </summary>
    /// <remarks>
    /// <para>
    /// When this collection is non-<see langword="null"/> and contains at least one evaluator, the harness agent is
    /// wrapped in a <see cref="LoopAgent"/> that re-invokes the agent until the evaluators are satisfied. The loop is
    /// applied as the outermost decorator, so each iteration is a complete agent run (including tool approval and
    /// OpenTelemetry instrumentation).
    /// </para>
    /// <para>
    /// When <see langword="null"/> or empty (the default), no <see cref="LoopAgent"/> is added and the agent behaves
    /// as a single-shot agent.
    /// </para>
    /// </remarks>
    public IEnumerable<LoopEvaluator>? LoopEvaluators { get; set; }

    /// <summary>
    /// Gets or sets optional configuration for the <see cref="LoopAgent"/> created from <see cref="LoopEvaluators"/>.
    /// </summary>
    /// <remarks>
    /// When <see langword="null"/>, the <see cref="LoopAgent"/> uses its default settings. This property is ignored
    /// when <see cref="LoopEvaluators"/> is <see langword="null"/> or empty.
    /// </remarks>
    public LoopAgentOptions? LoopAgentOptions { get; set; }

    /// <summary>
    /// Gets or sets the maximum number of function-invocation loop iterations per request.
    /// </summary>
    /// <remarks>
    /// When set, this value is passed to <see cref="FunctionInvokingChatClient.MaximumIterationsPerRequest"/>.
    /// When <see langword="null"/>, the <see cref="FunctionInvokingChatClient"/> default is used.
    /// </remarks>
    public int? MaximumIterationsPerRequest { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether the <see cref="ToolApprovalAgent"/> auto-approval middleware is disabled.
    /// </summary>
    /// <remarks>
    /// This disables the tool auto-approval functionality only, keeping the tool approval flow requiring approval (for example,
    /// <see cref="ApprovalRequiredAIFunction"/> tools). This setting controls whether the agent is wrapped with the
    /// <see cref="ToolApprovalAgent"/> middleware that supports "don't ask again" and auto-approval rules.
    /// When <see langword="false"/> (the default), the middleware is added.
    /// </remarks>
    public bool DisableToolAutoApproval { get; set; }

    /// <summary>
    /// Gets or sets the options for the <see cref="ToolApprovalAgent"/> middleware.
    /// </summary>
    /// <remarks>
    /// When <see langword="null"/>, the <see cref="ToolApprovalAgent"/> uses default settings.
    /// This property has no effect when <see cref="DisableToolAutoApproval"/> is <see langword="true"/>.
    /// </remarks>
    public ToolApprovalAgentOptions? ToolApprovalAgentOptions { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether bypassing of approval requests for tools that do not
    /// require approval is disabled.
    /// </summary>
    /// <remarks>
    /// When <see langword="false"/> (the default), the underlying chat client pipeline includes the decorator
    /// added by <see cref="ChatClientBuilderExtensions.UseNonApprovalRequiredFunctionBypassing"/> above the
    /// function invocation middleware.
    /// This stores automatically approved function calls for tools that do not require approval in the session
    /// state when they are returned alongside tools that do, so that only tools that truly require human
    /// approval are surfaced to the caller.
    /// </remarks>
    public bool DisableNonApprovalRequiredFunctionBypassing { get; set; }

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

    /// <summary>
    /// Gets or sets the collection of background agents available for delegation via <see cref="BackgroundAgentsProvider"/>.
    /// </summary>
    /// <remarks>
    /// When non-null and non-empty, a <see cref="BackgroundAgentsProvider"/> is automatically included in the
    /// agent's context providers, enabling the agent to start, monitor, and retrieve results from background tasks.
    /// When <see langword="null"/> or empty, no <see cref="BackgroundAgentsProvider"/> is configured.
    /// Each agent in the collection must have a non-empty <see cref="AIAgent.Name"/> and names must be unique
    /// (case-insensitive). If these requirements are not met, <see cref="BackgroundAgentsProvider"/> will throw
    /// an <see cref="System.ArgumentException"/> during construction.
    /// </remarks>
    public IEnumerable<AIAgent>? BackgroundAgents { get; set; }

    /// <summary>
    /// Gets or sets optional configuration for the <see cref="BackgroundAgentsProvider"/>.
    /// </summary>
    /// <remarks>
    /// Use this to customize instructions or agent list formatting for the background agents feature.
    /// This property is ignored when <see cref="BackgroundAgents"/> is <see langword="null"/> or empty.
    /// </remarks>
    public BackgroundAgentsProviderOptions? BackgroundAgentsProviderOptions { get; set; }

#if NET
    /// <summary>
    /// Gets or sets the shell executor used to enable shell tool and environment probing via <see cref="ShellEnvironmentProvider"/>.
    /// </summary>
    /// <remarks>
    /// When non-null, a <see cref="ShellEnvironmentProvider"/> is automatically included in the agent's context
    /// providers (injecting OS/shell/CWD information into the system prompt), and the executor's
    /// <see cref="ShellExecutor.AsAIFunction"/> is registered as a callable tool.
    /// When <see langword="null"/> (the default), no shell features are enabled.
    /// </remarks>
    public ShellExecutor? ShellExecutor { get; set; }

    /// <summary>
    /// Gets or sets the name of the shell execution tool exposed to the model.
    /// </summary>
    /// <remarks>
    /// When <see langword="null"/> (the default), the shell executor's default tool name (<c>run_shell</c>) is used.
    /// This property is ignored when <see cref="ShellExecutor"/> is <see langword="null"/>.
    /// </remarks>
    public string? ShellToolName { get; set; }

    /// <summary>
    /// Gets or sets the description of the shell execution tool shown to the model.
    /// </summary>
    /// <remarks>
    /// When <see langword="null"/> (the default), the shell executor's built-in description is used.
    /// This property is ignored when <see cref="ShellExecutor"/> is <see langword="null"/>.
    /// </remarks>
    public string? ShellToolDescription { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether approval is disabled for the shell execution tool.
    /// </summary>
    /// <remarks>
    /// <para>
    /// When <see langword="false"/> (the default), the shell tool is wrapped in an <see cref="ApprovalRequiredAIFunction"/>
    /// so every command requires explicit approval before executing. When <see langword="true"/>, the tool can be invoked
    /// without approval. This property is ignored when <see cref="ShellExecutor"/> is <see langword="null"/>.
    /// </para>
    /// <para>
    /// Setting this to <see langword="true"/> also requires the underlying <see cref="ShellExecutor"/> to permit
    /// unapproved use. The inverse of this value is forwarded as the <c>requireApproval</c> argument to
    /// <see cref="ShellExecutor.AsAIFunction"/>, and some executors enforce their own security boundary:
    /// <see cref="LocalShellExecutor"/> throws an <see cref="System.InvalidOperationException"/> unless it was
    /// constructed with <see cref="LocalShellExecutorOptions.AcknowledgeUnsafe"/> set to <see langword="true"/>,
    /// because running unapproved commands directly on the host is inherently unsafe. Sandboxed executors such as
    /// <see cref="DockerShellExecutor"/> impose no such requirement.
    /// </para>
    /// </remarks>
    public bool DisableShellToolApproval { get; set; }

    /// <summary>
    /// Gets or sets optional configuration for the <see cref="ShellEnvironmentProvider"/>.
    /// </summary>
    /// <remarks>
    /// Use this to customize which tools are probed, the probe timeout, shell family override,
    /// or the instructions formatter.
    /// This property is ignored when <see cref="ShellExecutor"/> is <see langword="null"/>.
    /// </remarks>
    public ShellEnvironmentProviderOptions? ShellEnvironmentProviderOptions { get; set; }
#endif
}
