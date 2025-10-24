// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Agents.Persistent;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="McpTool"/>.
/// </summary>
internal static class McpToolExtensions
{
    /// <summary>
    /// Creates a <see cref="MCPToolDefinition"/> from a <see cref="McpTool"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="McpTool"/></param>
    internal static MCPToolDefinition CreateMcpToolDefinition(this McpTool tool)
    {
        Throw.IfNull(tool);
        Throw.IfNull(tool.Name?.LiteralValue);
        Throw.IfNull(tool.Url);

        return new MCPToolDefinition(tool.Name?.LiteralValue, tool.Url.ToString());
    }
}
