// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="LoggingAgentBuilderExtensions"/> UseLogging extension method.
/// </summary>
public class LoggingAgentBuilderExtensionsTests
{
    /// <summary>
    /// Verify that UseLogging throws ArgumentNullException when builder is null.
    /// </summary>
    [Fact]
    public void UseLogging_WithNullBuilder_ThrowsArgumentNullException()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>("builder", () => ((AIAgentBuilder)null!).UseLogging());
    }

    /// <summary>
    /// Verify that UseLogging returns a LoggingAgent when logger factory is provided.
    /// </summary>
    [Fact]
    public void UseLogging_WithLoggerFactory_ReturnsLoggingAgent()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var builder = new AIAgentBuilder(mockAgent.Object);
        using var loggerFactory = LoggerFactory.Create(builder => { });

        // Act
        AIAgent result = builder.UseLogging(loggerFactory: loggerFactory).Build();

        // Assert
        Assert.IsType<LoggingAgent>(result);
    }

    /// <summary>
    /// Verify that UseLogging returns the inner agent when NullLoggerFactory is provided.
    /// </summary>
    [Fact]
    public void UseLogging_WithNullLoggerFactory_ReturnsInnerAgent()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var builder = new AIAgentBuilder(mockAgent.Object);

        // Act
        AIAgent result = builder.UseLogging(loggerFactory: NullLoggerFactory.Instance).Build();

        // Assert
        Assert.NotNull(result);
        Assert.IsNotType<LoggingAgent>(result);
    }

    /// <summary>
    /// Verify that UseLogging with configure action works correctly.
    /// </summary>
    [Fact]
    public void UseLogging_WithConfigureAction_CallsConfigureAction()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var builder = new AIAgentBuilder(mockAgent.Object);
        using var loggerFactory = LoggerFactory.Create(builder => { });
        var configureWasCalled = false;

        // Act
        AIAgent result = builder.UseLogging(
            loggerFactory: loggerFactory,
            configure: agent =>
            {
                configureWasCalled = true;
                Assert.NotNull(agent);
                Assert.IsType<LoggingAgent>(agent);
            }).Build();

        // Assert
        Assert.True(configureWasCalled);
        Assert.IsType<LoggingAgent>(result);
    }

    /// <summary>
    /// Verify that UseLogging returns the same builder instance for chaining.
    /// </summary>
    [Fact]
    public void UseLogging_ReturnsBuilderForChaining()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var builder = new AIAgentBuilder(mockAgent.Object);
        using var loggerFactory = LoggerFactory.Create(builder => { });

        // Act
        AIAgentBuilder result = builder.UseLogging(loggerFactory: loggerFactory);

        // Assert
        Assert.Same(builder, result);
    }

    /// <summary>
    /// Verify that UseLogging with all parameters works correctly.
    /// </summary>
    [Fact]
    public void UseLogging_WithAllParameters_WorksCorrectly()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        using var loggerFactory = LoggerFactory.Create(builder => { });
        var builder = new AIAgentBuilder(mockAgent.Object);
        var configureWasCalled = false;

        // Act
        AIAgent result = builder.UseLogging(
            loggerFactory: loggerFactory,
            configure: agent =>
            {
                configureWasCalled = true;
                Assert.NotNull(agent);
            }).Build();

        // Assert
        Assert.True(configureWasCalled);
        Assert.IsType<LoggingAgent>(result);
    }

    /// <summary>
    /// Verify that UseLogging resolves ILoggerFactory from service provider when not provided.
    /// </summary>
    [Fact]
    public void UseLogging_WithoutLoggerFactory_ResolvesFromServiceProvider()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var builder = new AIAgentBuilder(mockAgent.Object);

        var services = new ServiceCollection();
        using var loggerFactory = LoggerFactory.Create(builder => { });
        services.AddSingleton(loggerFactory);

        builder.Use((innerAgent, serviceProvider) =>
        {
            Assert.NotNull(serviceProvider);
            return innerAgent;
        });

        // Act
        AIAgent result = builder.UseLogging().Build(services.BuildServiceProvider());

        // Assert
        Assert.IsType<LoggingAgent>(result);
    }

    /// <summary>
    /// Verify that UseLogging with configure action can customize JsonSerializerOptions.
    /// </summary>
    [Fact]
    public void UseLogging_ConfigureJsonSerializerOptions_WorksCorrectly()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var builder = new AIAgentBuilder(mockAgent.Object);
        using var loggerFactory = LoggerFactory.Create(builder => { });
        var customOptions = new System.Text.Json.JsonSerializerOptions();

        // Act
        AIAgent result = builder.UseLogging(
            loggerFactory: loggerFactory,
            configure: agent => agent.JsonSerializerOptions = customOptions).Build();

        // Assert
        Assert.IsType<LoggingAgent>(result);
        Assert.Same(customOptions, ((LoggingAgent)result).JsonSerializerOptions);
    }
}
