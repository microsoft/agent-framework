// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="McpServerTool"/>.
/// </summary>
internal static class McpServerToolExtensions
{
    /// <summary>
    /// Creates a <see cref="HostedMcpServerTool"/> from a <see cref="McpServerTool"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="McpServerTool"/></param>
    internal static HostedMcpServerTool CreateHostedMcpTool(this McpServerTool tool)
    {
        Throw.IfNull(tool);
        Throw.IfNull(tool.ServerName?.LiteralValue);
        Throw.IfNull(tool.Connection);

        var connection = tool.Connection as AnonymousConnection ?? throw new ArgumentException("Only AnonymousConnection is supported for MCP Server Tool connections.", nameof(tool));
        var serverUrl = connection.Endpoint?.LiteralValue;
        Throw.IfNullOrEmpty(serverUrl, nameof(connection.Endpoint));

        return new HostedMcpServerTool(tool.ServerName.LiteralValue, serverUrl)
        {
            ServerDescription = tool.ServerDescription?.LiteralValue,
            AllowedTools = tool.AllowedTools?.LiteralValue,
            ApprovalMode = tool.ApprovalMode?.AsHostedMcpServerToolApprovalMode(),
        };
    }
}
