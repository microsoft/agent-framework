// Copyright (c) Microsoft. All rights reserved.

using System;
using Azure.AI.Projects.Agents;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Extension methods for <see cref="FoundryAITool"/> that require Azure.AI.Projects 2.1.0-beta.1+
/// types (e.g. <see cref="ToolboxRecord"/>, <see cref="ToolboxVersion"/>).
/// </summary>
public static class FoundryAIToolExtensions
{
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
