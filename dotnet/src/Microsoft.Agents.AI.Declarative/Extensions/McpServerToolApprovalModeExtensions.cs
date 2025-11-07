// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="McpServerToolApprovalMode"/>.
/// </summary>
public static class McpServerToolApprovalModeExtensions
{
    /// <summary>
    /// Converts a <see cref="McpServerToolApprovalMode"/> to a <see cref="HostedMcpServerToolApprovalMode"/>.
    /// </summary>
    /// <param name="mode">Instance of <see cref="McpServerToolApprovalMode"/></param>
    public static HostedMcpServerToolApprovalMode ToHostedMcpServerToolApprovalMode(this McpServerToolApprovalMode mode)
    {
        return mode switch
        {
            McpServerToolNeverRequireApprovalMode => HostedMcpServerToolApprovalMode.NeverRequire,
            McpServerToolAlwaysRequireApprovalMode => HostedMcpServerToolApprovalMode.AlwaysRequire,
            McpServerToolRequireSpecificApprovalMode specificMode =>
                HostedMcpServerToolApprovalMode.RequireSpecific(
                    specificMode?.AlwaysRequireApprovalToolNames?.LiteralValue ?? [],
                    specificMode?.NeverRequireApprovalToolNames?.LiteralValue ?? []
            ),
            _ => HostedMcpServerToolApprovalMode.AlwaysRequire,
        };
    }
}
