// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using Microsoft.Agents.AI.Workflows.Observability;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Declarative;

/// <summary>
/// Configuration options for workflow execution.
/// </summary>
public sealed class DeclarativeWorkflowOptions(ResponseAgentProvider agentProvider)
{
    /// <summary>
    /// Defines the agent provider.
    /// </summary>
    public ResponseAgentProvider AgentProvider { get; } = Throw.IfNull(agentProvider);

    /// <summary>
    /// Gets or sets the MCP tool handler for invoking MCP tools within workflows.
    /// If not set, MCP tool invocations will fail with an appropriate error message.
    /// </summary>
    public IMcpToolHandler? McpToolHandler { get; init; }

    /// <summary>
    /// Defines the configuration settings for the workflow.
    /// </summary>
    public IConfiguration? Configuration { get; init; }

    /// <summary>
    /// Optionally identifies a continued workflow conversation.
    /// </summary>
    public string? ConversationId { get; init; }

    /// <summary>
    /// Defines the maximum number of nested calls allowed in a PowerFx formula.
    /// </summary>
    public int? MaximumCallDepth { get; init; }

    /// <summary>
    /// Defines the maximum allowed length for expressions evaluated in the workflow.
    /// </summary>
    public int? MaximumExpressionLength { get; init; }

    /// <summary>
    /// Gets the <see cref="ILoggerFactory"/> used to create loggers for workflow components.
    /// </summary>
    public ILoggerFactory LoggerFactory { get; init; } = NullLoggerFactory.Instance;

    /// <summary>
    /// Gets the callback to configure telemetry options.
    /// </summary>
    public Action<WorkflowTelemetryOptions>? ConfigureTelemetry { get; init; }

    /// <summary>
    /// Gets an optional <see cref="ActivitySource"/> for telemetry.
    /// If provided, the caller retains ownership and is responsible for disposal.
    /// If <see langword="null"/> but <see cref="ConfigureTelemetry"/> is set, a shared default
    /// activity source named "Microsoft.Agents.AI.Workflows" will be used.
    /// </summary>
    public ActivitySource? TelemetryActivitySource { get; init; }

    /// <summary>
    /// Gets a value indicating whether telemetry is enabled.
    /// Telemetry is enabled when either <see cref="ConfigureTelemetry"/> or <see cref="TelemetryActivitySource"/> is set.
    /// </summary>
    internal bool IsTelemetryEnabled => this.ConfigureTelemetry is not null || this.TelemetryActivitySource is not null;
}
