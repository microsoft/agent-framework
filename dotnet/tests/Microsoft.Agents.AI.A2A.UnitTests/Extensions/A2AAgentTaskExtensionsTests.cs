// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using A2A;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.A2A.UnitTests;

/// <summary>
/// Unit tests for the <see cref="A2AAgentTaskExtensions"/> class.
/// </summary>
public sealed class A2AAgentTaskExtensionsTests
{
    [Fact]
    public void ToChatMessages_WithNullAgentTask_ThrowsArgumentNullException()
    {
        // Arrange
        AgentTask agentTask = null!;

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => agentTask.ToChatMessages());
    }

    [Fact]
    public void ToAIContents_WithNullAgentTask_ThrowsArgumentNullException()
    {
        // Arrange
        AgentTask agentTask = null!;

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => agentTask.ToAIContents());
    }

    [Fact]
    public void ToChatMessages_WithEmptyArtifactsAndNoUserInputRequests_ReturnsNull()
    {
        // Arrange
        var agentTask = new AgentTask
        {
            Id = "task1",
            Artifacts = [],
            Status = new AgentTaskStatus { State = TaskState.Completed },
        };

        // Act
        IList<ChatMessage>? result = agentTask.ToChatMessages();

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public void ToChatMessages_WithNullArtifactsAndNoUserInputRequests_ReturnsNull()
    {
        // Arrange
        var agentTask = new AgentTask
        {
            Id = "task1",
            Artifacts = null,
            Status = new AgentTaskStatus { State = TaskState.Completed },
        };

        // Act
        IList<ChatMessage>? result = agentTask.ToChatMessages();

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public void ToAIContents_WithEmptyArtifactsAndNoUserInputRequests_ReturnsNull()
    {
        // Arrange
        var agentTask = new AgentTask
        {
            Id = "task1",
            Artifacts = [],
            Status = new AgentTaskStatus { State = TaskState.Completed },
        };

        // Act
        IList<AIContent>? result = agentTask.ToAIContents();

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public void ToAIContents_WithNullArtifactsAndNoUserInputRequests_ReturnsNull()
    {
        // Arrange
        var agentTask = new AgentTask
        {
            Id = "task1",
            Artifacts = null,
            Status = new AgentTaskStatus { State = TaskState.Completed },
        };

        // Act
        IList<AIContent>? result = agentTask.ToAIContents();

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public void ToChatMessages_WithValidArtifact_ReturnsChatMessages()
    {
        // Arrange
        var artifact = new Artifact
        {
            Parts = [new TextPart { Text = "response" }],
        };

        var agentTask = new AgentTask
        {
            Id = "task1",
            Artifacts = [artifact],
            Status = new AgentTaskStatus { State = TaskState.Completed },
        };

        // Act
        IList<ChatMessage>? result = agentTask.ToChatMessages();

        // Assert
        Assert.NotNull(result);
        Assert.NotEmpty(result);
        Assert.All(result, msg => Assert.Equal(ChatRole.Assistant, msg.Role));
        Assert.Equal("response", result[0].Contents[0].ToString());
    }

    [Fact]
    public void ToAIContents_WithMultipleArtifacts_FlattenAllContents()
    {
        // Arrange
        var artifact1 = new Artifact
        {
            Parts = [new TextPart { Text = "content1" }],
        };

        var artifact2 = new Artifact
        {
            Parts =
            [
                new TextPart { Text = "content2" },
                new TextPart { Text = "content3" }
            ],
        };

        var agentTask = new AgentTask
        {
            Id = "task1",
            Artifacts = [artifact1, artifact2],
            Status = new AgentTaskStatus { State = TaskState.Completed },
        };

        // Act
        IList<AIContent>? result = agentTask.ToAIContents();

        // Assert
        Assert.NotNull(result);
        Assert.NotEmpty(result);
        Assert.Equal(3, result.Count);
        Assert.Equal("content1", result[0].ToString());
        Assert.Equal("content2", result[1].ToString());
        Assert.Equal("content3", result[2].ToString());
    }
}
