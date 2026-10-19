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
    [Theory]
    [InlineData(TaskState.InputRequired)]
    [InlineData(TaskState.AuthRequired)]
    [InlineData(TaskState.Unspecified)]
    [InlineData(TaskState.Failed)]
    [InlineData(TaskState.Canceled)]
    [InlineData(TaskState.Rejected)]
    public void ToAIContents_WithNullMessage_ReturnsNull(TaskState state)
    {
        // Arrange
        var status = new TaskStatus
        {
            State = state,
            Message = null,
        };

        // Act
        IList<AIContent>? result = status.ToAIContents();

        // Assert
        Assert.Null(result);
    }

    [Theory]
    [InlineData(TaskState.Submitted)]
    [InlineData(TaskState.Working)]
    [InlineData(TaskState.Completed)]
    public void ToAIContents_WithOtherStates_ReturnsNull(TaskState state)
    {
        // Arrange
        var status = new TaskStatus
        {
            State = state,
            Message = new Message { Parts = [Part.FromText("Some text")] },
        };

        // Act
        IList<AIContent>? result = status.ToAIContents();

        // Assert
        Assert.Null(result);
    }

    [Theory]
    [InlineData(TaskState.InputRequired)]
    [InlineData(TaskState.AuthRequired)]
    [InlineData(TaskState.Unspecified)]
    [InlineData(TaskState.Failed)]
    [InlineData(TaskState.Canceled)]
    [InlineData(TaskState.Rejected)]
    public void ToAIContents_WithStatusMessage_ReturnsAIContentList(TaskState state)
    {
        // Arrange
        var status = new TaskStatus
        {
            State = state,
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
        IList<AIContent>? result = status.ToAIContents();

        // Assert
        Assert.NotNull(result);
        Assert.Equal(3, result.Count);
        Assert.Equal("First request", Assert.IsType<TextContent>(result[0]).Text);
        Assert.Equal("Second request", Assert.IsType<TextContent>(result[1]).Text);
        Assert.Equal("Third request", Assert.IsType<TextContent>(result[2]).Text);
    }

    [Theory]
    [InlineData(TaskState.InputRequired)]
    [InlineData(TaskState.AuthRequired)]
    [InlineData(TaskState.Unspecified)]
    [InlineData(TaskState.Failed)]
    [InlineData(TaskState.Canceled)]
    [InlineData(TaskState.Rejected)]
    public void ToAIContents_WithTextParts_SetsRawRepresentationAndAdditionalPropertiesCorrectly(TaskState state)
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
            State = state,
            Message = new Message { Parts = [textPart] },
        };

        // Act
        IList<AIContent>? result = status.ToAIContents();

        // Assert
        Assert.NotNull(result);
        var content = Assert.IsType<TextContent>(result[0]);
        Assert.Equal(textPart, content.RawRepresentation);
        Assert.NotNull(content.AdditionalProperties);
        Assert.True(content.AdditionalProperties.ContainsKey("key1"));
        Assert.True(content.AdditionalProperties.ContainsKey("key2"));
    }

    [Theory]
    [InlineData(TaskState.InputRequired)]
    [InlineData(TaskState.AuthRequired)]
    [InlineData(TaskState.Unspecified)]
    [InlineData(TaskState.Failed)]
    [InlineData(TaskState.Canceled)]
    [InlineData(TaskState.Rejected)]
    public void ToAIContents_WithEmptyMessageParts_ReturnsNull(TaskState state)
    {
        // Arrange
        var status = new TaskStatus
        {
            State = state,
            Message = new Message { Parts = [] },
        };

        // Act
        IList<AIContent>? result = status.ToAIContents();

        // Assert
        Assert.Null(result);
    }
}
