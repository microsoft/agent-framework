// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Extension methods for locally executed MCP functions.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public static class LocalMcpAIFunctionExtensions
{
    /// <summary>
    /// Marks a locally executed MCP function so Foundry hosting exposes its execution as a caller-facing
    /// <c>mcp_call</c> item instead of a function-call pair.
    /// </summary>
    /// <param name="function">The locally executed MCP function.</param>
    /// <param name="serverLabel">The MCP server label exposed to Responses callers.</param>
    /// <param name="toolName">
    /// The remote MCP tool name. When omitted, <see cref="AITool.Name"/> is used.
    /// </param>
    /// <returns>A function retaining the original invocation behavior with local MCP execution metadata.</returns>
    public static AIFunction AsLocalMcpTool(
        this AIFunction function,
        string serverLabel,
        string? toolName = null)
    {
        ArgumentNullException.ThrowIfNull(function);
        ArgumentException.ThrowIfNullOrWhiteSpace(serverLabel);

        toolName ??= function.Name;
        ArgumentException.ThrowIfNullOrWhiteSpace(toolName);

        return new LocalMcpAIFunction(function, serverLabel, toolName);
    }
}
