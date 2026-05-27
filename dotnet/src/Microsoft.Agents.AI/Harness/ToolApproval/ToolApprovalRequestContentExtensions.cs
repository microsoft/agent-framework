// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides extension methods on <see cref="ToolApprovalRequestContent"/> for creating
/// <see cref="AlwaysApproveToolApprovalResponseContent"/> instances that instruct the
/// <see cref="ToolApprovalAgent"/> middleware to record standing approval rules.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public static class ToolApprovalRequestContentExtensions
{
    /// <summary>
    /// Creates an approved <see cref="AlwaysApproveToolApprovalResponseContent"/> that also
    /// instructs the middleware to always approve future calls to the same tool,
    /// regardless of the arguments provided.
    /// </summary>
    /// <param name="request">The tool approval request to respond to.</param>
    /// <param name="reason">An optional reason for the approval.</param>
    /// <returns>
    /// An <see cref="AlwaysApproveToolApprovalResponseContent"/> wrapping an approved
    /// <see cref="ToolApprovalResponseContent"/> with the <see cref="AlwaysApproveToolApprovalResponseContent.AlwaysApproveTool"/>
    /// flag set to <see langword="true"/>.
    /// </returns>
    public static AlwaysApproveToolApprovalResponseContent CreateAlwaysApproveToolResponse(
        this ToolApprovalRequestContent request,
        string? reason = null)
    {
        _ = Throw.IfNull(request);

        return new AlwaysApproveToolApprovalResponseContent(
            request.CreateResponse(approved: true, reason),
            alwaysApproveTool: true,
            alwaysApproveToolWithArguments: false);
    }

    /// <summary>
    /// Creates an approved <see cref="AlwaysApproveToolApprovalResponseContent"/> that also
    /// instructs the middleware to always approve future calls to the same tool
    /// with the exact same arguments.
    /// </summary>
    /// <param name="request">The tool approval request to respond to.</param>
    /// <param name="reason">An optional reason for the approval.</param>
    /// <returns>
    /// An <see cref="AlwaysApproveToolApprovalResponseContent"/> wrapping an approved
    /// <see cref="ToolApprovalResponseContent"/> with the <see cref="AlwaysApproveToolApprovalResponseContent.AlwaysApproveToolWithArguments"/>
    /// flag set to <see langword="true"/>.
    /// </returns>
    public static AlwaysApproveToolApprovalResponseContent CreateAlwaysApproveToolWithArgumentsResponse(
        this ToolApprovalRequestContent request,
        string? reason = null)
    {
        _ = Throw.IfNull(request);

        return new AlwaysApproveToolApprovalResponseContent(
            request.CreateResponse(approved: true, reason),
            alwaysApproveTool: false,
            alwaysApproveToolWithArguments: true);
    }
}
