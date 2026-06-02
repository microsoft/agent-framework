// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Tests for <see cref="ToolApprovalRequestPropagator"/>.
/// </summary>
public sealed class ToolApprovalRequestPropagatorTests
{
    [Fact]
    public void AttachAndGetApprovals_RoundTripsApprovals()
    {
        // Arrange
        var functionCall = new FunctionCallContent("call-1", "SpecialistAgent");
        var approvalRequest = new ToolApprovalRequestContent("approval-1", functionCall);

        // Act
        ToolApprovalRequestPropagator.Attach(functionCall, [approvalRequest]);
        var approvals = ToolApprovalRequestPropagator.GetApprovals(functionCall);

        // Assert
        Assert.NotNull(approvals);
        var approval = Assert.Single(approvals);
        Assert.Same(approvalRequest, approval);

        _ = ToolApprovalRequestPropagator.TakeApprovals(functionCall);
    }

    [Fact]
    public void TakeApprovals_RemovesApprovals()
    {
        // Arrange
        var functionCall = new FunctionCallContent("call-1", "SpecialistAgent");
        var approvalRequest = new ToolApprovalRequestContent("approval-1", functionCall);
        ToolApprovalRequestPropagator.Attach(functionCall, [approvalRequest]);

        // Act
        var approvals = ToolApprovalRequestPropagator.TakeApprovals(functionCall);
        var approvalsAfterTake = ToolApprovalRequestPropagator.GetApprovals(functionCall);

        // Assert
        Assert.NotNull(approvals);
        Assert.Single(approvals);
        Assert.Null(approvalsAfterTake);
    }

    [Fact]
    public void Attach_WithEmptyApprovals_RemovesExistingApprovals()
    {
        // Arrange
        var functionCall = new FunctionCallContent("call-1", "SpecialistAgent");
        var approvalRequest = new ToolApprovalRequestContent("approval-1", functionCall);
        ToolApprovalRequestPropagator.Attach(functionCall, [approvalRequest]);

        // Act
        ToolApprovalRequestPropagator.Attach(functionCall, []);
        var approvals = ToolApprovalRequestPropagator.GetApprovals(functionCall);

        // Assert
        Assert.Null(approvals);
    }
}
