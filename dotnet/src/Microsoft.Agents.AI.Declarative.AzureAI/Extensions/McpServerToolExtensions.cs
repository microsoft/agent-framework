// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Agents.Persistent;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="McpServerTool"/>.
/// </summary>
internal static class McpServerToolExtensions
{
    /// <summary>
    /// Creates a <see cref="MCPToolDefinition"/> from a <see cref="McpServerTool"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="McpServerTool"/></param>
    internal static MCPToolDefinition CreateMcpToolDefinition(this McpServerTool tool)
    {
        Throw.IfNull(tool);
        Throw.IfNull(tool.ServerName?.LiteralValue);
        Throw.IfNull(tool.Connection);

        // TODO: Add support for additional properties

        var connection = tool.Connection as AnonymousConnection;
        Throw.IfNull(connection);

        var serverUrl = connection.Endpoint?.LiteralValue;
        Throw.IfNullOrEmpty(serverUrl, nameof(connection.Endpoint));

        return new MCPToolDefinition(tool.ServerName?.LiteralValue, serverUrl);
    }
}
