// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="ToolApprovalAgentBuilderExtensions"/> class.
/// </summary>
public class ToolApprovalAgentBuilderExtensionsTests
{
    /// <summary>
    /// Verify that UseToolApproval throws ArgumentNullException when builder is null.
    /// </summary>
    [Fact]
    public void UseToolApproval_WithNullBuilder_ThrowsArgumentNullException()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>("builder", () => ((AIAgentBuilder)null!).UseToolApproval());
    }

    /// <summary>
    /// Verify that UseToolApproval returns a ToolApprovalAgent.
    /// </summary>
    [Fact]
    public void UseToolApproval_WithValidBuilder_ReturnsToolApprovalAgent()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var builder = new AIAgentBuilder(mockAgent.Object);

        // Act
        var result = builder.UseToolApproval().Build();

        // Assert
        Assert.IsType<ToolApprovalAgent>(result);
    }

    /// <summary>
    /// Verify that UseToolApproval returns the same builder instance for chaining.
    /// </summary>
    [Fact]
    public void UseToolApproval_ReturnsBuilderForChaining()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var builder = new AIAgentBuilder(mockAgent.Object);

        // Act
        var result = builder.UseToolApproval();

        // Assert
        Assert.Same(builder, result);
    }

    /// <summary>
    /// Verify that UseToolApproval with custom JsonSerializerOptions works correctly.
    /// </summary>
    [Fact]
    public void UseToolApproval_WithCustomJsonSerializerOptions_ReturnsToolApprovalAgent()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var builder = new AIAgentBuilder(mockAgent.Object);
        var options = new JsonSerializerOptions();

        // Act
        var result = builder.UseToolApproval(jsonSerializerOptions: options).Build();

        // Assert
        Assert.IsType<ToolApprovalAgent>(result);
    }
}
