// Copyright (c) Microsoft. All rights reserved.

using System.Net.Http;
using Azure.Core;
using Azure.Identity;
using Microsoft.Agents.Workflows.Declarative.Execution;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests;

public class DeclarativeWorkflowContextTests
{
    [Fact]
    public void DefaultHasExpectedValues()
    {
        // Assert
        DeclarativeWorkflowContext context = DeclarativeWorkflowContext.Default;
        Assert.Equal(string.Empty, context.ProjectEndpoint);
        Assert.IsType<DefaultAzureCredential>(context.ProjectCredentials);
        Assert.Null(context.MaximumCallDepth);
        Assert.Null(context.MaximumExpressionLength);
        Assert.Null(context.HttpClient);
        Assert.Same(NullLoggerFactory.Instance, context.LoggerFactory);
    }

    [Fact]
    public void InitializeDefaultValues()
    {
        // Act
        DeclarativeWorkflowContext context = new();

        // Assert
        Assert.Equal(string.Empty, context.ProjectEndpoint);
        Assert.IsType<DefaultAzureCredential>(context.ProjectCredentials);
        Assert.Null(context.MaximumCallDepth);
        Assert.Null(context.MaximumExpressionLength);
        Assert.Null(context.HttpClient);
        Assert.Same(NullLoggerFactory.Instance, context.LoggerFactory);
    }

    [Fact]
    public void InitializeExplicitValues()
    {
        // Arrange
        string projectEndpoint = "https://test-endpoint.com";
        TokenCredential credentials = new DefaultAzureCredential();
        int maxCallDepth = 10;
        int maxExpressionLength = 100;
        using HttpClient httpClient = new();
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

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void CreateActionContext(bool useHttpClient)
    {
        // Arrange
        HttpClient? httpClient = useHttpClient ? new() : null;
        try
        {
            DeclarativeWorkflowContext context = new()
            {
                ProjectEndpoint = "https://test.ai.azure.com/myproject",
                HttpClient = httpClient,
            };
            WorkflowScopes scopes = new();

            // Act
            WorkflowExecutionContext executionContext = context.CreateActionContext("workflow-id", scopes);

            // Assert
            Assert.NotNull(executionContext);
            Assert.NotNull(executionContext.Engine);
            Assert.Same(scopes, executionContext.Scopes);
            Assert.NotNull(executionContext.ClientFactory);
            Assert.NotNull(executionContext.Logger);
            Assert.NotNull(executionContext.ClientFactory.Invoke());
        }
        finally
        {
            httpClient?.Dispose();
        }
    }

    [Fact]
    public void CreateActionContextWithCustomLogger()
    {
        // Arrange
        WorkflowScopes scopes = new();
        ILoggerFactory customLoggerFactory = LoggerFactory.Create(builder => { });
        DeclarativeWorkflowContext context = new()
        {
            LoggerFactory = customLoggerFactory
        };

        // Act
        WorkflowExecutionContext executionContext = context.CreateActionContext("workflow-id", scopes);

        // Assert
        Assert.NotNull(executionContext);
        Assert.NotNull(executionContext.Logger);
        Assert.NotSame(NullLogger.Instance, executionContext.Logger);
    }
}
