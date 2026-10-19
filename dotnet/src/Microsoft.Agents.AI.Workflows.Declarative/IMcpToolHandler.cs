// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Declarative;

/// <summary>
/// Defines the contract for invoking MCP tools within declarative workflows.
/// </summary>
/// <remarks>
/// This interface allows the MCP tool invocation to be abstracted, enabling
/// different implementations for local development, hosted workflows, and testing scenarios.
/// </remarks>
public interface IMcpToolHandler
{
    /// <summary>
    /// Invokes an MCP tool on the specified server.
    /// </summary>
    /// <param name="serverUrl">The URL of the MCP server.</param>
    /// <param name="serverLabel">An optional label identifying the server connection.</param>
    /// <param name="toolName">The name of the tool to invoke.</param>
    /// <param name="arguments">Optional arguments to pass to the tool.</param>
    /// <param name="headers">Optional headers to include in the request.</param>
    /// <param name="connectionName">An optional connection name for managed connections.</param>
    /// <param name="cancellationToken">A token to observe cancellation.</param>
    /// <returns>
    /// A task representing the asynchronous operation. The result contains a <see cref="McpServerToolResultContent"/>
    /// with the tool invocation output.
    /// </returns>
    Task<McpServerToolResultContent> InvokeToolAsync(
        string serverUrl,
        string? serverLabel,
        string toolName,
        IDictionary<string, object?>? arguments,
        IDictionary<string, string>? headers,
        string? connectionName,
        CancellationToken cancellationToken = default);
}
