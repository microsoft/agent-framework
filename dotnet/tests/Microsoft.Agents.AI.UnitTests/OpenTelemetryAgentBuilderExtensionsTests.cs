// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.Logging;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="OpenTelemetryAgentBuilderExtensions"/> class.
/// </summary>
public class OpenTelemetryAgentBuilderExtensionsTests
{
    /// <summary>
    /// Verify that UseOpenTelemetry throws ArgumentNullException when builder is null.
    /// </summary>
    [Fact]
    public void UseOpenTelemetry_WithNullBuilder_ThrowsArgumentNullException()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>("builder", () => ((AIAgentBuilder)null!).UseOpenTelemetry());
    }

    /// <summary>
    /// Verify that UseOpenTelemetry returns an OpenTelemetryAgent.
    /// </summary>
    [Fact]
    public void UseOpenTelemetry_WithValidBuilder_ReturnsOpenTelemetryAgent()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var builder = new AIAgentBuilder(mockAgent.Object);

        // Act
        var result = builder.UseOpenTelemetry().Build();

        // Assert
        Assert.IsType<OpenTelemetryAgent>(result);
    }

    /// <summary>
    /// Verify that UseOpenTelemetry with source name works correctly.
    /// </summary>
    [Fact]
    public void UseOpenTelemetry_WithSourceName_WorksCorrectly()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var builder = new AIAgentBuilder(mockAgent.Object);
        const string SourceName = "TestSource";

        // Act
        var result = builder.UseOpenTelemetry(sourceName: SourceName).Build();

        // Assert
        Assert.IsType<OpenTelemetryAgent>(result);
    }

    /// <summary>
    /// Verify that UseOpenTelemetry with configure action works correctly.
    /// </summary>
    [Fact]
    public void UseOpenTelemetry_WithConfigureAction_CallsConfigureAction()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var builder = new AIAgentBuilder(mockAgent.Object);
        var configureWasCalled = false;

        // Act
        var result = builder.UseOpenTelemetry(configure: agent =>
        {
            configureWasCalled = true;
            Assert.NotNull(agent);
            Assert.IsType<OpenTelemetryAgent>(agent);
        }).Build();

        // Assert
        Assert.True(configureWasCalled);
        Assert.IsType<OpenTelemetryAgent>(result);
    }

    /// <summary>
    /// Verify that UseOpenTelemetry returns the same builder instance for chaining.
    /// </summary>
    [Fact]
    public void UseOpenTelemetry_ReturnsBuilderForChaining()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var builder = new AIAgentBuilder(mockAgent.Object);

        // Act
        var result = builder.UseOpenTelemetry();

        // Assert
        Assert.Same(builder, result);
    }

    /// <summary>
    /// Verify that UseOpenTelemetry with all parameters works correctly.
    /// </summary>
    [Fact]
    public void UseOpenTelemetry_WithAllParameters_WorksCorrectly()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        using var loggerFactory = LoggerFactory.Create(builder => { });
        var builder = new AIAgentBuilder(mockAgent.Object);
        const string SourceName = "TestSource";
        var configureWasCalled = false;

        // Act
        var result = builder.UseOpenTelemetry(
            sourceName: SourceName,
            configure: agent =>
            {
                configureWasCalled = true;
                Assert.NotNull(agent);
            }).Build();

        // Assert
        Assert.True(configureWasCalled);
        Assert.IsType<OpenTelemetryAgent>(result);
    }
}
