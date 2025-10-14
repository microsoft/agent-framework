// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
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
        Throw.IfNull(tool.Url?.LiteralValue);

        var serverDescription = tool.ExtensionData?.GetString("server_description");
        var allowedTools = tool.ExtensionData?.GetPropertyOrNull<TableDataValue>(InitializablePropertyPath.Create("allowed_tools"))?.Values
            .Select(t => t.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("Value"))?.Value!)
            .Where(t => !string.IsNullOrWhiteSpace(t))
            .ToList();

        return new HostedMcpServerTool(tool.Name.LiteralValue, tool.Url.LiteralValue)
        {
            ServerDescription = serverDescription,
            AllowedTools = allowedTools,
            ApprovalMode = tool.GetHostedMcpServerToolApprovalMode(),
            Headers = tool.GetHeaders(),
        };
    }

    /// <summary>
    /// Retrieves the 'require_approval' property from a <see cref="McpTool"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="McpTool"/></param>
    internal static HostedMcpServerToolApprovalMode GetHostedMcpServerToolApprovalMode(this McpTool tool)
    {
        Throw.IfNull(tool);

        var requireApproval = tool.ExtensionData?.GetString("requireApproval");
        return requireApproval?.ToUpperInvariant() switch
        {
            "ALWAYS" => HostedMcpServerToolApprovalMode.AlwaysRequire,
            "NEVER" => HostedMcpServerToolApprovalMode.NeverRequire,
            "REQUIRESPECIFIC" => tool.GetHostedMcpServerToolRequireSpecificApprovalMode(),
            _ => throw new ArgumentOutOfRangeException(nameof(tool), $"Unknown value for require_approval: {requireApproval}"),
        };
    }

    /// <summary>
    /// Retrieves the 'allowed_tools' property from a <see cref="McpTool"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="McpTool"/></param>
    internal static HostedMcpServerToolApprovalMode GetHostedMcpServerToolRequireSpecificApprovalMode(this McpTool tool)
    {
        Throw.IfNull(tool);

        var allowedTools = tool.ExtensionData?.GetPropertyOrNull<TableDataValue>(InitializablePropertyPath.Create("allowedTools"))?.Values;
        if (allowedTools is null)
        {
            return HostedMcpServerToolApprovalMode.NeverRequire;
        }

        var tools = ((IEnumerable<RecordDataValue>)allowedTools)
            .Select(vsi => vsi.GetString("Value"))
            .Where(vsi => !string.IsNullOrWhiteSpace(vsi))
            .Select(vsi => vsi!)
            .ToList();

        return HostedMcpServerToolApprovalMode.RequireSpecific(null, tools);
    }

    /// <summary>
    /// Retrieves the 'headers' property from a <see cref="McpTool"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="McpTool"/></param>
    internal static IDictionary<string, string>? GetHeaders(this McpTool tool)
    {
        Throw.IfNull(tool);

        var headers = tool.ExtensionData?.GetPropertyOrNull<RecordDataValue>(InitializablePropertyPath.Create("headers"));
        if (headers is null)
        {
            return null;
        }

        return headers.Properties.ToDictionary(
            kvp => kvp.Key,
            kvp => kvp.Value?.ToString() ?? string.Empty
        );
    }
}
