// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.A2A.UnitTests;

/// <summary>
/// Unit tests for the <see cref="A2AInputResponseContent"/> class.
/// </summary>
public sealed class A2AInputResponseContentTests
{
    [Fact]
    public void Constructor_WithValidParameters_InitializesPropertiesCorrectly()
    {
        // Arrange
        const string Id = "response-456";
        var response = new TextContent("User's answer");

        // Act
        var content = new A2AInputResponseContent(Id, response);

        // Assert
        Assert.Equal(Id, content.RequestId);
        Assert.Same(response, content.Response);
    }

    [Fact]
    public void Constructor_WithNullId_ThrowsArgumentNullException()
    {
        // Arrange & Act & Assert
        Assert.Throws<ArgumentNullException>(() => new A2AInputResponseContent(null!, new TextContent("This is my response")));
    }

    [Theory]
    [InlineData("")]
    [InlineData("   ")]
    public void Constructor_WithInvalidId_ThrowsArgumentException(string invalidId)
    {
        // Arrange & Act & Assert
        Assert.Throws<ArgumentException>(() => new A2AInputResponseContent(invalidId, new TextContent("This is my response")));
    }

    [Fact]
    public void Constructor_WithNullResponse_ThrowsArgumentNullException()
    {
        // Arrange & Act & Assert
        Assert.Throws<ArgumentNullException>(() => new A2AInputResponseContent("test-response-123", null!));
    }
}
