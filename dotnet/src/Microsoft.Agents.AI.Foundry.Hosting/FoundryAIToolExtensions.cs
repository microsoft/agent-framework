// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using Azure.AI.Projects.Agents;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Extension methods for <see cref="FoundryAITool"/> that require Azure.AI.Projects 2.1.0-beta.1+
/// types (e.g. <see cref="ToolboxRecord"/>, <see cref="ToolboxVersion"/>).
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public static class FoundryAIToolExtensions
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

    /// <summary>
    /// Creates an <see cref="AITool"/> marker from a <see cref="ToolboxRecord"/> retrieved
    /// from <c>AIProjectClient</c>. Uses <see cref="ToolboxRecord.Name"/> and
    /// <see cref="ToolboxRecord.DefaultVersion"/>.
    /// </summary>
    /// <param name="toolbox">The toolbox record.</param>
    /// <returns>An <see cref="AITool"/> marker backed by <see cref="HostedMcpToolboxAITool"/>.</returns>
    public static AITool CreateHostedMcpToolbox(ToolboxRecord toolbox)
    {
        if (toolbox is null)
        {
            throw new ArgumentNullException(nameof(toolbox));
        }

        return new HostedMcpToolboxAITool(toolbox.Name, toolbox.DefaultVersion);
    }

    /// <summary>
    /// Creates an <see cref="AITool"/> marker from a specific <see cref="ToolboxVersion"/>
    /// retrieved from <c>AIProjectClient</c>. Uses <see cref="ToolboxVersion.Name"/> and
    /// <see cref="ToolboxVersion.Version"/>.
    /// </summary>
    /// <param name="toolboxVersion">The toolbox version.</param>
    /// <returns>An <see cref="AITool"/> marker backed by <see cref="HostedMcpToolboxAITool"/>.</returns>
    public static AITool CreateHostedMcpToolbox(ToolboxVersion toolboxVersion)
    {
        if (toolboxVersion is null)
        {
            throw new ArgumentNullException(nameof(toolboxVersion));
        }

        return new HostedMcpToolboxAITool(toolboxVersion.Name, toolboxVersion.Version);
    }
}
