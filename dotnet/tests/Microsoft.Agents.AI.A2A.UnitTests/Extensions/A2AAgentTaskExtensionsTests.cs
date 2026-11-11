// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
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
            Status = new TaskStatus { State = TaskState.Completed },
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
            Status = new TaskStatus { State = TaskState.Completed },
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
            Status = new TaskStatus { State = TaskState.Completed },
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
            Status = new TaskStatus { State = TaskState.Completed },
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
            Parts = [Part.FromText("response")],
        };

        var agentTask = new AgentTask
        {
            Id = "task1",
            Artifacts = [artifact],
            Status = new TaskStatus { State = TaskState.Completed },
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
            Parts = [Part.FromText("content1")],
        };

        var artifact2 = new Artifact
        {
            Parts =
            [
                Part.FromText("content2"),
                Part.FromText("content3")
            ],
        };

        var agentTask = new AgentTask
        {
            Id = "task1",
            Artifacts = [artifact1, artifact2],
            Status = new TaskStatus { State = TaskState.Completed },
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

    [Theory]
    [InlineData(TaskState.InputRequired, Role.Agent)]
    [InlineData(TaskState.InputRequired, Role.User)]
    [InlineData(TaskState.AuthRequired, Role.Agent)]
    [InlineData(TaskState.AuthRequired, Role.User)]
    [InlineData(TaskState.Unspecified, Role.Agent)]
    [InlineData(TaskState.Unspecified, Role.User)]
    [InlineData(TaskState.Failed, Role.Agent)]
    [InlineData(TaskState.Failed, Role.User)]
    [InlineData(TaskState.Canceled, Role.Agent)]
    [InlineData(TaskState.Canceled, Role.User)]
    [InlineData(TaskState.Rejected, Role.Agent)]
    [InlineData(TaskState.Rejected, Role.User)]
    public void ToChatMessages_WithStatusMessage_IncludesStatusContents(TaskState state, Role role)
    {
        // Arrange
        var agentTask = new AgentTask
        {
            Id = "task1",
            Artifacts = null,
            Status = new TaskStatus
            {
                State = state,
                Message = new Message
                {
                    Role = role,
                    MessageId = "status-message",
                    Metadata = new() { ["reason"] = JsonSerializer.SerializeToElement(new { code = "needs-attention" }) },
                    Parts = [Part.FromText("What is your destination?")]
                },
            },
        };

        // Act
        IList<ChatMessage>? result = agentTask.ToChatMessages();

        // Assert
        Assert.NotNull(result);
        var message = Assert.Single(result);
        Assert.Equal(role == Role.Agent ? ChatRole.Assistant : ChatRole.User, message.Role);
        Assert.Equal("status-message", message.MessageId);
        Assert.Same(agentTask.Status.Message, message.RawRepresentation);
        Assert.NotNull(message.AdditionalProperties);
        Assert.Equal("needs-attention", Assert.IsType<JsonElement>(message.AdditionalProperties["reason"]).GetProperty("code").GetString());
        var textContent = Assert.Single(message.Contents.OfType<TextContent>());
        Assert.Equal("What is your destination?", textContent.Text);
        Assert.Same(agentTask.Status.Message.Parts[0], textContent.RawRepresentation);
    }

    [Theory]
    [InlineData(TaskState.InputRequired)]
    [InlineData(TaskState.AuthRequired)]
    [InlineData(TaskState.Unspecified)]
    [InlineData(TaskState.Failed)]
    [InlineData(TaskState.Canceled)]
    [InlineData(TaskState.Rejected)]
    public void ToAIContents_WithStatusMessage_IncludesStatusContents(TaskState state)
    {
        // Arrange
        var agentTask = new AgentTask
        {
            Id = "task1",
            Artifacts = null,
            Status = new TaskStatus
            {
                State = state,
                Message = new Message { Parts = [Part.FromText("What is your destination?")] },
            },
        };

        // Act
        IList<AIContent>? result = agentTask.ToAIContents();

        // Assert
        Assert.NotNull(result);
        var textContent = Assert.Single(result.OfType<TextContent>());
        Assert.Equal("What is your destination?", textContent.Text);
    }

    [Theory]
    [InlineData(TaskState.InputRequired)]
    [InlineData(TaskState.AuthRequired)]
    [InlineData(TaskState.Unspecified)]
    [InlineData(TaskState.Failed)]
    [InlineData(TaskState.Canceled)]
    [InlineData(TaskState.Rejected)]
    public void ToChatMessages_WithArtifactsAndStatusMessage_IncludesBoth(TaskState state)
    {
        // Arrange
        var agentTask = new AgentTask
        {
            Id = "task1",
            Artifacts = [new Artifact { Parts = [Part.FromText("partial result")] }],
            Status = new TaskStatus
            {
                State = state,
                Message = new Message { Parts = [Part.FromText("Need more info")] },
            },
        };

        // Act
        IList<ChatMessage>? result = agentTask.ToChatMessages();

        // Assert
        Assert.NotNull(result);
        Assert.Equal(2, result.Count);
        Assert.Equal("partial result", result[0].Text);
        Assert.Equal("Need more info", Assert.Single(result[1].Contents.OfType<TextContent>()).Text);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void WithNullOrEmptyStatusMessage_PreservesArtifacts(bool emptyMessage)
    {
        // Arrange
        var part = Part.FromText("Partial result");
        part.Metadata = new() { ["part-key"] = JsonSerializer.SerializeToElement("part-value") };
        var artifact = new Artifact
        {
            Metadata = new() { ["artifact-key"] = JsonSerializer.SerializeToElement("artifact-value") },
            Parts = [part]
        };
        var task = new AgentTask
        {
            Id = "task1",
            Artifacts = [artifact],
            Status = new TaskStatus
            {
                State = TaskState.Failed,
                Message = emptyMessage
                    ? new Message
                    {
                        Role = Role.User,
                        MessageId = "empty-status",
                        Metadata = new() { ["reason"] = JsonSerializer.SerializeToElement("failure") },
                        Parts = []
                    }
                    : null
            }
        };

        // Act
        var messages = task.ToChatMessages();
        var contents = task.ToAIContents();

        // Assert
        Assert.NotNull(messages);
        var message = Assert.Single(messages);
        Assert.Equal("Partial result", message.Text);
        Assert.Equal(ChatRole.Assistant, message.Role);
        Assert.Null(message.MessageId);
        Assert.Same(artifact, message.RawRepresentation);
        Assert.NotNull(message.AdditionalProperties);
        Assert.Single(message.AdditionalProperties);
        Assert.Equal("artifact-value", Assert.IsType<JsonElement>(message.AdditionalProperties["artifact-key"]).GetString());
        Assert.NotNull(contents);
        var content = Assert.IsType<TextContent>(Assert.Single(contents));
        Assert.Equal("Partial result", content.Text);
        Assert.Same(part, content.RawRepresentation);
        Assert.NotNull(content.AdditionalProperties);
        Assert.Single(content.AdditionalProperties);
        Assert.Equal("part-value", Assert.IsType<JsonElement>(content.AdditionalProperties["part-key"]).GetString());
    }
}
