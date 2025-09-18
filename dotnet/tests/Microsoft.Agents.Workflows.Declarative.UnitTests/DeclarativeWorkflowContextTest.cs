// Copyright (c) Microsoft. All rights reserved.

using Azure.Core;
using Azure.Identity;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Moq;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests;

public class DeclarativeWorkflowContextTests
{
    [Fact]
    public void InitializeDefaultValues()
    {
        // Act
        Mock<WorkflowAgentProvider> mockProvider = new(MockBehavior.Strict);
        DeclarativeWorkflowOptions context = new(mockProvider.Object);

        // Assert
        Assert.Equal(mockProvider.Object, context.AgentProvider);
        Assert.Null(context.MaximumCallDepth);
        Assert.Null(context.MaximumExpressionLength);
        Assert.Same(NullLoggerFactory.Instance, context.LoggerFactory);
    }

    [Fact]
    public void InitializeExplicitValues()
    {
        // Arrange
        TokenCredential credentials = new DefaultAzureCredential();
        const int MaxCallDepth = 10;
        const int MaxExpressionLength = 100;
        ILoggerFactory loggerFactory = LoggerFactory.Create(builder => { });

        // Act
        Mock<WorkflowAgentProvider> mockProvider = new(MockBehavior.Strict);
        DeclarativeWorkflowOptions context = new(mockProvider.Object)
        {
            MaximumCallDepth = MaxCallDepth,
            MaximumExpressionLength = MaxExpressionLength,
            LoggerFactory = loggerFactory
        };

        // Assert
        Assert.Equal(mockProvider.Object, context.AgentProvider);
        Assert.Equal(MaxCallDepth, context.MaximumCallDepth);
        Assert.Equal(MaxExpressionLength, context.MaximumExpressionLength);
        Assert.Same(loggerFactory, context.LoggerFactory);
    }
}
