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
public sealed class DeclarativeWorkflowOptions(WorkflowAgentProvider agentProvider)
{
    /// <summary>
    /// Defines the agent provider.
    /// </summary>
    public WorkflowAgentProvider AgentProvider { get; } = Throw.IfNull(agentProvider);

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
    /// Gets the telemetry source name for OpenTelemetry instrumentation.
    /// If <see langword="null"/>, telemetry is disabled unless <see cref="TelemetryActivitySource"/> is provided.
    /// </summary>
    public string? TelemetrySourceName { get; init; }

    /// <summary>
    /// Gets the callback to configure telemetry options.
    /// </summary>
    public Action<WorkflowTelemetryOptions>? ConfigureTelemetry { get; init; }

    /// <summary>
    /// Gets an optional <see cref="ActivitySource"/> for telemetry.
    /// If provided, the caller retains ownership and is responsible for disposal.
    /// </summary>
    public ActivitySource? TelemetryActivitySource { get; init; }
}
