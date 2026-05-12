// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using A2A;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.A2A.UnitTests;

/// <summary>
/// Unit tests for the <see cref="AgentTaskStatusExtensions"/> class.
/// </summary>
public sealed class AgentTaskStatusExtensionsTests
{
    [Fact]
    public void GetUserInputRequests_WithNullMessage_ReturnsNull()
    {
        // Arrange
        var status = new TaskStatus
        {
            State = TaskState.InputRequired,
            Message = null,
        };

        // Act
        IList<AIContent>? result = status.GetUserInputRequests();

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public void GetUserInputRequests_WithNotInputRequiredState_ReturnsNull()
    {
        // Arrange
        var status = new TaskStatus
        {
            State = TaskState.Completed,
            Message = new Message { Parts = [Part.FromText("Some text")] },
        };

        // Act
        IList<AIContent>? result = status.GetUserInputRequests();

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public void GetUserInputRequests_WithInputRequiredStateAndMultipleRequests_ReturnsAIContentList()
    {
        // Arrange
        var status = new TaskStatus
        {
            State = TaskState.InputRequired,
            Message = new Message
            {
                Parts =
                [
                    Part.FromText("First request"),
                    Part.FromText("Second request"),
                    Part.FromText("Third request")
                ],
            },
        };

        // Act
        IList<AIContent>? result = status.GetUserInputRequests();

        // Assert
        Assert.NotNull(result);
        Assert.Equal(3, result.Count);
        Assert.Equal("First request", Assert.IsType<TextContent>(result[0]).Text);
        Assert.Equal("Second request", Assert.IsType<TextContent>(result[1]).Text);
        Assert.Equal("Third request", Assert.IsType<TextContent>(result[2]).Text);
    }

    [Fact]
    public void GetUserInputRequests_WithTextParts_SetsRawRepresentationAndAdditionalPropertiesCorrectly()
    {
        // Arrange
        var textPart = Part.FromText("Input request");
        textPart.Metadata = new Dictionary<string, System.Text.Json.JsonElement>
        {
            { "key1", System.Text.Json.JsonSerializer.SerializeToElement("value1") },
            { "key2", System.Text.Json.JsonSerializer.SerializeToElement("value2") }
        };
        var status = new TaskStatus
        {
            State = TaskState.InputRequired,
            Message = new Message { Parts = [textPart] },
        };

        // Act
        IList<AIContent>? result = status.GetUserInputRequests();

        // Assert
        Assert.NotNull(result);
        var content = Assert.IsType<TextContent>(result[0]);
        Assert.Equal(textPart, content.RawRepresentation);
        Assert.NotNull(content.AdditionalProperties);
        Assert.True(content.AdditionalProperties.ContainsKey("key1"));
        Assert.True(content.AdditionalProperties.ContainsKey("key2"));
    }

    [Fact]
    public void GetUserInputRequests_WithEmptyMessageParts_ReturnsNull()
    {
        // Arrange
        var status = new TaskStatus
        {
            State = TaskState.InputRequired,
            Message = new Message { Parts = [] },
        };

        // Act
        IList<AIContent>? result = status.GetUserInputRequests();

        // Assert
        Assert.Null(result);
    }
}
