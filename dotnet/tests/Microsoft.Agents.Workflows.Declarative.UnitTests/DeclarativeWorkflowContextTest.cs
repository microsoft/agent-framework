// Copyright (c) Microsoft. All rights reserved.

using System.Net.Http;
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
        Assert.Null(context.HttpClient);
        Assert.Same(NullLoggerFactory.Instance, context.LoggerFactory);
    }

    [Fact]
    public void InitializeExplicitValues()
    {
        // Arrange
        TokenCredential credentials = new DefaultAzureCredential();
        int maxCallDepth = 10;
        int maxExpressionLength = 100;
        using HttpClient httpClient = new();
        ILoggerFactory loggerFactory = LoggerFactory.Create(builder => { });

        // Act
        Mock<WorkflowAgentProvider> mockProvider = new(MockBehavior.Strict);
        DeclarativeWorkflowOptions context = new(mockProvider.Object)
        {
            MaximumCallDepth = maxCallDepth,
            MaximumExpressionLength = maxExpressionLength,
            HttpClient = httpClient,
            LoggerFactory = loggerFactory
        };

        // Assert
        Assert.Equal(mockProvider.Object, context.AgentProvider);
        Assert.Equal(maxCallDepth, context.MaximumCallDepth);
        Assert.Equal(maxExpressionLength, context.MaximumExpressionLength);
        Assert.Same(httpClient, context.HttpClient);
        Assert.Same(loggerFactory, context.LoggerFactory);
    }
}
