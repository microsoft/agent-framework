// Copyright (c) Microsoft. All rights reserved.

using System.Net.Http;
using Azure.Core;
using Azure.Identity;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative;

/// <summary>
/// Configuration options for workflow execution.
/// </summary>
public sealed class DeclarativeWorkflowOptions(string projectEndpoint)
{
    /// <summary>
    /// Optionally identifies a continued workflow conversation.
    /// </summary>
    public string? ConversationId { get; init; }

    /// <summary>
    /// Defines the endpoint for the Foundry project.
    /// </summary>
    public string ProjectEndpoint { get; } = projectEndpoint;

    /// <summary>
    /// Defines the credentials that authorize access to the Foundry project.
    /// </summary>
    public TokenCredential ProjectCredentials { get; init; } = new DefaultAzureCredential();

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
