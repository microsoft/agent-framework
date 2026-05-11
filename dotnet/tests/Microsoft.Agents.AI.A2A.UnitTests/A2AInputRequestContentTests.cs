// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.A2A.UnitTests;

/// <summary>
/// Unit tests for the <see cref="A2AInputRequestContent"/> class.
/// </summary>
public sealed class A2AInputRequestContentTests
{
    [Fact]
    public void Constructor_WithValidParameters_InitializesPropertiesCorrectly()
    {
        // Arrange
        const string Id = "input-456";
        var request = new TextContent("What is your name?");

        // Act
        var content = new A2AInputRequestContent(Id, request);

        // Assert
        Assert.Equal(Id, content.RequestId);
        Assert.Same(request, content.Request);
    }

    [Fact]
    public void Constructor_WithNullId_ThrowsArgumentNullException()
    {
        // Arrange & Act & Assert
        Assert.Throws<ArgumentNullException>(() => new A2AInputRequestContent(null!, new TextContent("Please provide your feedback")));
    }

    [Theory]
    [InlineData("")]
    [InlineData("   ")]
    public void Constructor_WithInvalidId_ThrowsArgumentException(string invalidId)
    {
        // Arrange & Act & Assert
        Assert.Throws<ArgumentException>(() => new A2AInputRequestContent(invalidId, new TextContent("Please provide your feedback")));
    }

    [Fact]
    public void Constructor_WithNullRequest_ThrowsArgumentNullException()
    {
        // Arrange & Act & Assert
        Assert.Throws<ArgumentNullException>(() => new A2AInputRequestContent("test-input-123", null!));
    }

    [Fact]
    public void CreateResponse_WithValidContent_PreservesIdAndIncludesResponse()
    {
        // Arrange
        const string Id = "input-101";
        var content = new A2AInputRequestContent(Id, new TextContent("Please provide your feedback"));
        var responseContent = new TextContent("My response");

        // Act
        var response = content.CreateResponse(responseContent);

        // Assert
        Assert.Equal(Id, response.RequestId);
        Assert.Same(responseContent, response.Response);
    }

    [Fact]
    public void CreateResponse_WithNullContent_ThrowsArgumentNullException()
    {
        // Arrange
        var content = new A2AInputRequestContent("test-input-123", new TextContent("Please provide your feedback"));

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => content.CreateResponse((AIContent)null!));
    }

    [Fact]
    public void CreateResponse_WithValidText_PreservesIdAndIncludesResponse()
    {
        // Arrange
        const string Id = "input-201";
        var content = new A2AInputRequestContent(Id, new TextContent("Please provide your feedback"));
        const string ResponseText = "My text response";

        // Act
        var response = content.CreateResponse(ResponseText);

        // Assert
        Assert.Equal(Id, response.RequestId);
        var textContent = Assert.IsType<TextContent>(response.Response);
        Assert.Equal(ResponseText, textContent.Text);
    }

    [Fact]
    public void CreateResponse_WithNullText_ThrowsArgumentNullException()
    {
        // Arrange
        var content = new A2AInputRequestContent("test-input-123", new TextContent("Please provide your feedback"));

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => content.CreateResponse((string)null!));
    }
}
