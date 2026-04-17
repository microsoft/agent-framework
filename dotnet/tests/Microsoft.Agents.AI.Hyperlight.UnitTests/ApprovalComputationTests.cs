// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hyperlight.UnitTests;

public sealed class ApprovalComputationTests
{
    [Fact]
    public void AlwaysRequire_ReturnsTrueWithNoTools()
    {
        // Act / Assert
        Assert.True(HyperlightCodeActProvider.ComputeApprovalRequired(
            CodeActApprovalMode.AlwaysRequire,
            tools: []));
    }

    [Fact]
    public void AlwaysRequire_ReturnsTrueEvenWithoutApprovalTool()
    {
        // Arrange
        var tool = AIFunctionFactory.Create(() => "ok", name: "t");

        // Act / Assert
        Assert.True(HyperlightCodeActProvider.ComputeApprovalRequired(
            CodeActApprovalMode.AlwaysRequire,
            tools: [tool]));
    }

    [Fact]
    public void NeverRequire_NoTools_ReturnsFalse()
    {
        Assert.False(HyperlightCodeActProvider.ComputeApprovalRequired(
            CodeActApprovalMode.NeverRequire,
            tools: []));
    }

    [Fact]
    public void NeverRequire_NoApprovalRequiredTool_ReturnsFalse()
    {
        // Arrange
        var tool = AIFunctionFactory.Create(() => "ok", name: "t");

        // Act / Assert
        Assert.False(HyperlightCodeActProvider.ComputeApprovalRequired(
            CodeActApprovalMode.NeverRequire,
            tools: [tool]));
    }

    [Fact]
    public void NeverRequire_WithApprovalRequiredTool_ReturnsTrue()
    {
        // Arrange
        var tool = AIFunctionFactory.Create(() => "ok", name: "t");
        var wrapped = new ApprovalRequiredAIFunction(tool);

        // Act / Assert
        Assert.True(HyperlightCodeActProvider.ComputeApprovalRequired(
            CodeActApprovalMode.NeverRequire,
            tools: [wrapped]));
    }
}
