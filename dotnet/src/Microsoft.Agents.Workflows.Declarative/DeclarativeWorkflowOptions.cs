// Copyright (c) Microsoft. All rights reserved.

using System.Net.Http;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative;

/// <summary>
/// Configuration options for workflow execution.
/// </summary>
public sealed class DeclarativeWorkflowOptions(WorkflowAgentProvider agentProvider)
{
    /// <summary>
    /// Optionally identifies a continued workflow conversation.
    /// </summary>
    public string? ConversationId { get; init; }

    /// <summary>
    /// Defines the agent provider.
    /// </summary>
    public WorkflowAgentProvider AgentProvider { get; } = agentProvider;

    /// <summary>
    /// Defines the maximum number of nested calls allowed in a PowerFx formula.
    /// </summary>
    public int? MaximumCallDepth { get; init; }

    /// <summary>
    /// Defines the maximum allowed length for expressions evaluated in the workflow.
    /// </summary>
    public int? MaximumExpressionLength { get; init; }

    /// <summary>
    /// Gets the <see cref="System.Net.Http.HttpClient"/> instance used to send HTTP requests.
    /// </summary>
    public HttpClient? HttpClient { get; init; }

    /// <summary>
    /// Gets the <see cref="ILoggerFactory"/> used to create loggers for workflow components.
    /// </summary>
    public ILoggerFactory LoggerFactory { get; init; } = NullLoggerFactory.Instance;
}
