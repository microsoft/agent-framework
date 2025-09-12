// Copyright (c) Microsoft. All rights reserved.

using System;
using Moq;

namespace Microsoft.Extensions.AI.Agents.UnitTests;

/// <summary>
/// Unit tests for the <see cref="CallbackEnabledAIAgentBuilderExtensions"/> class.
/// </summary>
public class CallbackEnabledAIAgentBuilderExtensionsTests
{
    /// <summary>
    /// Verify that UseCallbacks throws ArgumentNullException when builder is null.
    /// </summary>
    [Fact]
    public void UseCallbacks_WithNullBuilder_ThrowsArgumentNullException()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>("builder", () =>
            CallbackEnabledAIAgentBuilderExtensions.UseCallbacks(null!));
    }

    /// <summary>
    /// Verify that UseCallbacks returns a CallbackEnabledAgent.
    /// </summary>
    [Fact]
    public void UseCallbacks_WithValidBuilder_ReturnsCallbackEnabledAgent()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var builder = new AIAgentBuilder(mockAgent.Object);

        // Act
        var result = builder.UseCallbacks().Build();

        // Assert
        Assert.IsType<CallbackEnabledAgent>(result);
    }

    /// <summary>
    /// Verify that UseCallbacks with configure action works correctly.
    /// </summary>
    [Fact]
    public void UseCallbacks_WithConfigureAction_CallsConfigureAction()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var builder = new AIAgentBuilder(mockAgent.Object);
        var configureWasCalled = false;

        // Act
        var result = builder.UseCallbacks(processor =>
        {
            configureWasCalled = true;
            Assert.NotNull(processor);
        }).Build();

        // Assert
        Assert.True(configureWasCalled);
        Assert.IsType<CallbackEnabledAgent>(result);
    }

    /// <summary>
    /// Verify that UseCallbacks works without configure action.
    /// </summary>
    [Fact]
    public void UseCallbacks_WithoutConfigureAction_WorksCorrectly()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var builder = new AIAgentBuilder(mockAgent.Object);

        // Act
        var result = builder.UseCallbacks(null).Build();

        // Assert
        Assert.IsType<CallbackEnabledAgent>(result);
    }

    /// <summary>
    /// Verify that UseCallbacks returns the same builder instance for chaining.
    /// </summary>
    [Fact]
    public void UseCallbacks_ReturnsBuilderForChaining()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var builder = new AIAgentBuilder(mockAgent.Object);

        // Act
        var result = builder.UseCallbacks();

        // Assert
        Assert.Same(builder, result);
    }
}
