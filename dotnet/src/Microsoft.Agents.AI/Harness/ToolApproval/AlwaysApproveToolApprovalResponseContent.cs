// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Wraps a <see cref="ToolApprovalResponseContent"/> with additional "always approve" settings,
/// enabling the <see cref="ToolApprovalAgent"/> middleware to record standing approval rules
/// so that future matching tool calls are auto-approved without user interaction.
/// </summary>
/// <remarks>
/// <para>
/// Instances of this class should not be created directly. Instead, use the extension methods
/// <see cref="ToolApprovalRequestContentExtensions.CreateAlwaysApproveToolResponse"/> or
/// <see cref="ToolApprovalRequestContentExtensions.CreateAlwaysApproveToolWithArgumentsResponse"/>
/// on <see cref="ToolApprovalRequestContent"/> to create instances with the appropriate flags set.
/// </para>
/// <para>
/// The <see cref="ToolApprovalAgent"/> middleware will unwrap the <see cref="InnerResponse"/> to forward
/// to the inner agent, while extracting the approval settings to persist as <see cref="ToolApprovalRule"/>
/// entries in the session state.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class AlwaysApproveToolApprovalResponseContent : AIContent
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AlwaysApproveToolApprovalResponseContent"/> class.
    /// </summary>
    /// <param name="innerResponse">The underlying approval response to forward to the agent.</param>
    /// <param name="alwaysApproveTool">
    /// When <see langword="true"/>, all future calls to this tool type will be auto-approved.
    /// </param>
    /// <param name="alwaysApproveToolWithArguments">
    /// When <see langword="true"/>, all future calls to this tool type with the same arguments will be auto-approved.
    /// </param>
    internal AlwaysApproveToolApprovalResponseContent(
        ToolApprovalResponseContent innerResponse,
        bool alwaysApproveTool,
        bool alwaysApproveToolWithArguments)
    {
        this.InnerResponse = Throw.IfNull(innerResponse);
        this.AlwaysApproveTool = alwaysApproveTool;
        this.AlwaysApproveToolWithArguments = alwaysApproveToolWithArguments;
    }

    /// <summary>
    /// Gets the underlying <see cref="ToolApprovalResponseContent"/> that will be forwarded to the inner agent.
    /// </summary>
    public ToolApprovalResponseContent InnerResponse { get; }

    /// <summary>
    /// Gets a value indicating whether all future calls to the same tool should be auto-approved
    /// regardless of the arguments provided.
    /// </summary>
    public bool AlwaysApproveTool { get; }

    /// <summary>
    /// Gets a value indicating whether all future calls to the same tool with the exact same
    /// arguments should be auto-approved.
    /// </summary>
    public bool AlwaysApproveToolWithArguments { get; }
}
