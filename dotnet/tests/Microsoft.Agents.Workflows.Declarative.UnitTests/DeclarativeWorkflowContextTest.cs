// Copyright (c) Microsoft. All rights reserved.

using System.Net.Http;
using Azure.Core;
using Azure.Identity;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests;

public class DeclarativeWorkflowContextTests
{
    [Fact]
    public void DefaultHasExpectedValues()
    {
        // Assert
        DeclarativeWorkflowOptions context = DeclarativeWorkflowOptions.Default;
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
        DeclarativeWorkflowOptions context = new();

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
        DeclarativeWorkflowOptions context = new()
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
}
