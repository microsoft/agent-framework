// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Foundry.UnitTests.Hosting;

public sealed class SourceGeneratedLoggingTests
{
    [Fact]
    public void AgentExecutionFailed_PreservesLevelTemplatePropertyAndException()
    {
        // Arrange
        var logs = new RecordingLoggerFactory();
        var logger = logs.CreateLogger(nameof(AgentFrameworkResponseHandler));
        var exception = new InvalidOperationException("failure");

        // Act
        logger.LogAgentExecutionFailed("response-1", exception);

        // Assert
        var entry = Assert.Single(logs.Entries);
        Assert.Equal(LogLevel.Error, entry.Level);
        Assert.Equal("Agent execution failed for response response-1.", entry.Message);
        Assert.Same(exception, entry.Exception);
        AssertProperty(entry.Properties, "ResponseId", "response-1");
        AssertProperty(
            entry.Properties,
            "{OriginalFormat}",
            "Agent execution failed for response {ResponseId}.");
    }

    [Fact]
    public void ToolboxResourceDisposalFailed_PreservesStructuredProperties()
    {
        // Arrange
        var logs = new RecordingLoggerFactory();
        var logger = logs.CreateLogger(nameof(FoundryToolboxService));
        var exception = new InvalidOperationException("failure");

        // Act
        logger.LogToolboxResourceDisposalFailed(
            "HTTP client",
            "search",
            "request scope",
            exception);

        // Assert
        var entry = Assert.Single(logs.Entries);
        Assert.Equal(LogLevel.Warning, entry.Level);
        Assert.Equal(
            "Failed to dispose HTTP client for toolbox search owned by request scope.",
            entry.Message);
        Assert.Same(exception, entry.Exception);
        AssertProperty(entry.Properties, "Resource", "HTTP client");
        AssertProperty(entry.Properties, "ToolboxName", "search");
        AssertProperty(entry.Properties, "Owner", "request scope");
        AssertProperty(
            entry.Properties,
            "{OriginalFormat}",
            "Failed to dispose {Resource} for toolbox {ToolboxName} owned by {Owner}.");
    }

    private static void AssertProperty(
        IReadOnlyList<KeyValuePair<string, object?>> properties,
        string name,
        object expectedValue)
    {
        var property = Assert.Single(properties, property => property.Key == name);
        Assert.Equal(expectedValue, property.Value);
    }
}
