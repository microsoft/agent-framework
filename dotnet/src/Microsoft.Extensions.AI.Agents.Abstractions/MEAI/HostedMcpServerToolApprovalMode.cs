// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Describes how approval is required for tool calls to a hosted MCP server.
/// </summary>
/// <remarks>
/// The predefined values <see cref="AlwaysRequire" />, and <see cref="NeverRequire"/> are provided to specify handling for all tools.
/// To specify approval behavior for individual tool names, use <see cref="RequireSpecific(IList{string}, IList{string})"/>.
/// </remarks>
#pragma warning disable CA1052 // Static holder types should be Static or NotInheritable
public class HostedMcpServerToolApprovalMode
#pragma warning restore CA1052
{
    /// <summary>
    /// Gets a predefined <see cref="HostedMcpServerToolApprovalMode"/> indicating that all tool calls to a hosted MCP server always require approval.
    /// </summary>
    public static HostedMcpServerToolAlwaysRequireApprovalMode AlwaysRequire { get; } = new();

    /// <summary>
    /// Gets a predefined <see cref="HostedMcpServerToolApprovalMode"/> indicating that all tool calls to a hosted MCP server never require approval.
    /// </summary>
    public static HostedMcpServerToolNeverRequireApprovalMode NeverRequire { get; } = new();

    private protected HostedMcpServerToolApprovalMode()
    {
    }

    /// <summary>
    /// Instantiates a <see cref="HostedMcpServerToolApprovalMode"/> that specifies approval behavior for individual tool names.
    /// </summary>
    /// <param name="alwaysRequireApprovalToolNames">The list of tools names that always require approval.</param>
    /// <param name="neverRequireApprovalToolNames">The list of tools names that never require approval.</param>
    /// <returns>An instance of <see cref="HostedMcpServerToolRequireSpecificApprovalMode"/> for the specified tool names.</returns>
    public static HostedMcpServerToolRequireSpecificApprovalMode RequireSpecific(IList<string>? alwaysRequireApprovalToolNames, IList<string>? neverRequireApprovalToolNames)
        => new(alwaysRequireApprovalToolNames, neverRequireApprovalToolNames);
}
