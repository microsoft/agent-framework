// Copyright (c) Microsoft. All rights reserved.

using System.Net;
using Microsoft.Agents.AI.Agentforce;

namespace Microsoft.Agents.AI.Agentforce.UnitTests;

public class AgentforceApiExceptionTests
{
    [Fact]
    public void Constructor_WithMessage_SetsMessage()
    {
        // Arrange & Act
        var exception = new AgentforceApiException("test error");

        // Assert
        Assert.Equal("test error", exception.Message);
        Assert.Null(exception.StatusCode);
        Assert.Null(exception.ErrorCode);
    }

    [Fact]
    public void Constructor_WithStatusCode_SetsProperties()
    {
        // Arrange & Act
        var exception = new AgentforceApiException("unauthorized", HttpStatusCode.Unauthorized, "invalid_token");

        // Assert
        Assert.Equal("unauthorized", exception.Message);
        Assert.Equal(HttpStatusCode.Unauthorized, exception.StatusCode);
        Assert.Equal("invalid_token", exception.ErrorCode);
    }

    [Fact]
    public void Constructor_WithInnerException_SetsInnerException()
    {
        // Arrange
        var inner = new System.InvalidOperationException("inner");

        // Act
        var exception = new AgentforceApiException("outer", inner);

        // Assert
        Assert.Equal("outer", exception.Message);
        Assert.Same(inner, exception.InnerException);
    }
}
