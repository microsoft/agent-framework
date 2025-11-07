// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="McpServerTool"/>.
/// </summary>
public static class McpServerToolExtensions
{
    /// <summary>
    /// Creates a <see cref="HostedMcpServerTool"/> from a <see cref="McpServerTool"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="McpServerTool"/></param>
    internal static HostedMcpServerTool CreateMcpTool(this McpServerTool tool)
    {
        Throw.IfNull(tool);
        Throw.IfNull(tool.ServerName?.LiteralValue);
        Throw.IfNull(tool.Connection);

        // TODO: Add support for ServerDescription, AllowedTools, ApprovalMode, and Headers.

        var connection = tool.Connection as AnonymousConnection;
        Throw.IfNull(connection);

        var serverUrl = connection.Endpoint?.LiteralValue;
        Throw.IfNullOrEmpty(serverUrl, nameof(connection.Endpoint));

        return new HostedMcpServerTool(tool.ServerName.LiteralValue, serverUrl)
        {
            ServerDescription = tool.ServerDescription?.LiteralValue,
            AllowedTools = tool.AllowedTools?.LiteralValue,
            ApprovalMode = tool.ApprovalMode?.ToHostedMcpServerToolApprovalMode(),
        };
    }
}
