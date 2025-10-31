// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="McpTool"/>.
/// </summary>
public static class McpToolExtensions
{
    /// <summary>
    /// Creates a <see cref="HostedMcpServerTool"/> from a <see cref="McpTool"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="McpTool"/></param>
    internal static HostedMcpServerTool CreateMcpTool(this McpTool tool)
    {
        Throw.IfNull(tool);
        Throw.IfNull(tool.Name?.LiteralValue);
        Throw.IfNull(tool.Connection);

        // TODO: Add support for ServerDescription, AllowedTools, ApprovalMode, and Headers.

        var connection = tool.Connection as AnonymousConnection;
        Throw.IfNull(connection);

        var serverUrl = connection.Endpoint?.LiteralValue;
        Throw.IfNullOrEmpty(serverUrl, nameof(connection.Endpoint));

        return new HostedMcpServerTool(tool.Name.LiteralValue, serverUrl);
    }
}
