// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Net.Http;
using Azure.Core;
using Azure.Identity;
using Microsoft.Agents.Workflows.Declarative.Execution;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Microsoft.Agents.Workflows.Declarative.Tests;

public class DeclarativeWorkflowContextTests
{
    [Fact]
    public void Default_ShouldHaveExpectedValues()
    {
        // Assert
        DeclarativeWorkflowContext defaultContext = DeclarativeWorkflowContext.Default;
        Assert.Equal(string.Empty, defaultContext.ProjectEndpoint);
        Assert.IsAssignableFrom<DefaultAzureCredential>(defaultContext.ProjectCredentials);
        Assert.Null(defaultContext.MaximumCallDepth);
        Assert.Null(defaultContext.MaximumExpressionLength);
        Assert.Null(defaultContext.HttpClient);
        Assert.Same(NullLoggerFactory.Instance, defaultContext.LoggerFactory);
    }

    [Fact]
    public void Constructor_WithNoParameters_ShouldInitializeDefaultValues()
    {
        // Act
        DeclarativeWorkflowContext context = new();

        // Assert
        Assert.Equal(string.Empty, context.ProjectEndpoint);
        Assert.IsAssignableFrom<DefaultAzureCredential>(context.ProjectCredentials);
        Assert.Null(context.MaximumCallDepth);
        Assert.Null(context.MaximumExpressionLength);
        Assert.Null(context.HttpClient);
        Assert.Same(NullLoggerFactory.Instance, context.LoggerFactory);
    }

    [Fact]
    public void Constructor_WithInitializers_ShouldSetProperties()
    {
        // Arrange
        string projectEndpoint = "https://test-endpoint.com";
        TokenCredential credentials = new DefaultAzureCredential();
        int maxCallDepth = 10;
        int maxExpressionLength = 100;
        HttpClient httpClient = new();
        ILoggerFactory loggerFactory = LoggerFactory.Create(builder => { });

        // Act
        DeclarativeWorkflowContext context = new()
        {
            ProjectEndpoint = projectEndpoint,
            ProjectCredentials = credentials,
            MaximumCallDepth = maxCallDepth,
            MaximumExpressionLength = maxExpressionLength,
            HttpClient = httpClient,
            LoggerFactory = loggerFactory
        };

        // Assert
        Assert.Equal(projectEndpoint, context.ProjectEndpoint);
        Assert.Same(credentials, context.ProjectCredentials);
        Assert.Equal(maxCallDepth, context.MaximumCallDepth);
        Assert.Equal(maxExpressionLength, context.MaximumExpressionLength);
        Assert.Same(httpClient, context.HttpClient);
        Assert.Same(loggerFactory, context.LoggerFactory);
    }

    [Fact]
    public void CreateActionContext_ShouldCreateContextWithExpectedProperties()
    {
        // Arrange
        DeclarativeWorkflowContext context = new()
        {
            MaximumExpressionLength = 200
        };
        string rootId = "test-root-id";
        WorkflowScopes scopes = new();

        // Act
        WorkflowExecutionContext executionContext = context.CreateActionContext(rootId, scopes);

        // Assert
        Assert.NotNull(executionContext);
        Assert.NotNull(executionContext.Engine);
        Assert.Same(scopes, executionContext.Scopes);
        Assert.NotNull(executionContext.ClientFactory);
        Assert.NotNull(executionContext.Logger);
        Assert.Equal(rootId, executionContext.Logger.ToString());
    }

    [Fact]
    public void CreateActionContext_WithCustomLoggerFactory_ShouldUseCustomLogger()
    {
        // Arrange
        ILoggerFactory customLoggerFactory = LoggerFactory.Create(builder => { });
        DeclarativeWorkflowContext context = new()
        {
            LoggerFactory = customLoggerFactory
        };
        string rootId = "test-root-id";
        WorkflowScopes scopes = new();

        // Act
        WorkflowExecutionContext executionContext = context.CreateActionContext(rootId, scopes);

        // Assert
        Assert.NotNull(executionContext);
        Assert.NotNull(executionContext.Logger);
        Assert.NotSame(NullLogger.Instance, executionContext.Logger);
    }
}
