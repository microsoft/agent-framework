// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Represents a mode where approval behavior is specified for individual tool names.
/// </summary>
public sealed class HostedMcpServerToolRequireSpecificApprovalMode : HostedMcpServerToolApprovalMode
{
    /// <summary>
    /// Initializes a new instance of the <see cref="HostedMcpServerToolRequireSpecificApprovalMode"/> class that specifies approval behavior for individual tool names.
    /// </summary>
    /// <param name="alwaysRequireApprovalToolNames">The list of tools names that always require approval.</param>
    /// <param name="neverRequireApprovalToolNames">The list of tools names that never require approval.</param>
    public HostedMcpServerToolRequireSpecificApprovalMode(IList<string>? alwaysRequireApprovalToolNames, IList<string>? neverRequireApprovalToolNames)
    {
        AlwaysRequireApprovalToolNames = alwaysRequireApprovalToolNames;
        NeverRequireApprovalToolNames = neverRequireApprovalToolNames;
    }

    /// <summary>
    /// Gets or sets the list of tool names that always require approval.
    /// </summary>
    public IList<string>? AlwaysRequireApprovalToolNames { get; set; }

    /// <summary>
    /// Gets or sets the list of tool names that never require approval.
    /// </summary>
    public IList<string>? NeverRequireApprovalToolNames { get; set; }
}
