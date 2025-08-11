// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Net.Http;
using Azure.AI.Agents.Persistent;
using Azure.Core;
using Azure.Core.Pipeline;
using Azure.Identity;
using Microsoft.Agents.Workflows.Declarative.Execution;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative;

/// <summary>
/// Provides configuration and context for workflow execution.
/// </summary>
public sealed class DeclarativeWorkflowContext
{
    internal static DeclarativeWorkflowContext Default { get; } = new();

    /// <summary>
    /// Defines the endpoint for the Foundry project.
    /// </summary>
    public string ProjectEndpoint { get; init; } = string.Empty;

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

    /// <summary>
    /// Gets the <see cref="TextWriter"/> used for activity output and diagnostics.
    /// </summary>
    public TextWriter ActivityChannel { get; init; } = Console.Out; // %%% REMOVE: For POC only

    internal WorkflowExecutionContext CreateActionContext(string rootId, WorkflowScopes scopes) =>
        new(RecalcEngineFactory.Create(scopes, this.MaximumExpressionLength),
            scopes,
            this.CreateClient,
            this.LoggerFactory.CreateLogger(rootId));

    private PersistentAgentsClient CreateClient()
    {
        PersistentAgentsAdministrationClientOptions clientOptions = new();

        if (this.HttpClient is not null)
        {
            clientOptions.Transport = new HttpClientTransport(this.HttpClient);
            //clientOptions.RetryPolicy = new RetryPolicy(maxRetries: 0);
        }

        return new PersistentAgentsClient(this.ProjectEndpoint, this.ProjectCredentials, clientOptions);
    }
}
