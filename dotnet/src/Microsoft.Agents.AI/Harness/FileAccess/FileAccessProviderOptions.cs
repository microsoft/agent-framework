// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Options controlling the behavior of <see cref="FileAccessProvider"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class FileAccessProviderOptions
{
    /// <summary>
    /// Gets or sets custom instructions provided to the agent for using the file access tools.
    /// </summary>
    /// <value>
    /// When <see langword="null"/> (the default), the provider uses built-in instructions
    /// that guide the agent on how to use file storage effectively.
    /// </value>
    public string? Instructions { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether the tools that modify the file store are disabled.
    /// </summary>
    /// <value>
    /// When <see langword="false"/> (the default), all tools are exposed. When <see langword="true"/>,
    /// only the read-only tools (<c>file_access_read</c>, <c>file_access_ls</c>, and <c>file_access_grep</c>)
    /// are exposed; the tools that modify the store (<c>file_access_write</c>, <c>file_access_delete</c>,
    /// <c>file_access_replace</c>, and <c>file_access_replace_lines</c>) are hidden.
    /// </value>
    public bool DisableWriteTools { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether approval is disabled for the read-only file access tools
    /// (<see cref="FileAccessProvider.ReadFileToolName"/>, <see cref="FileAccessProvider.LsToolName"/>,
    /// and <see cref="FileAccessProvider.GrepToolName"/>).
    /// </summary>
    /// <remarks>
    /// When <see langword="false"/> (the default), these tools require approval before invocation.
    /// When <see langword="true"/>, they can be invoked without approval.
    /// If any other tool in the same response still requires approval, set
    /// <see cref="ChatClientAgentOptions.EnableNonApprovalRequiredFunctionBypassing"/>
    /// to <see langword="true"/> so these tools are not surfaced as approval requests.
    /// When approval is required, auto-approval rules (e.g. <see cref="FileAccessProvider.ReadOnlyToolsAutoApprovalRule"/>
    /// or <see cref="FileAccessProvider.AllToolsAutoApprovalRule"/>) can be used to automatically approve calls.
    /// </remarks>
    public bool DisableReadOnlyToolApproval { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether approval is disabled for the tools that modify the file store
    /// (<see cref="FileAccessProvider.WriteToolName"/>, <see cref="FileAccessProvider.DeleteFileToolName"/>,
    /// <see cref="FileAccessProvider.ReplaceToolName"/>, and <see cref="FileAccessProvider.ReplaceLinesToolName"/>).
    /// </summary>
    /// <remarks>
    /// When <see langword="false"/> (the default), these tools require approval before invocation.
    /// When <see langword="true"/>, they can be invoked without approval.
    /// If any other tool in the same response still requires approval, set
    /// <see cref="ChatClientAgentOptions.EnableNonApprovalRequiredFunctionBypassing"/>
    /// to <see langword="true"/> so these tools are not surfaced as approval requests.
    /// When approval is required, the <see cref="FileAccessProvider.AllToolsAutoApprovalRule"/> can be used
    /// to automatically approve calls.
    /// This setting has no effect when <see cref="DisableWriteTools"/> is <see langword="true"/>, since the
    /// tools that modify the store are not exposed in that case.
    /// </remarks>
    public bool DisableWriteToolApproval { get; set; }
}
