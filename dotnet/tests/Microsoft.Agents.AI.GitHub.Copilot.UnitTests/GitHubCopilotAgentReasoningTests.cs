// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Reflection;
using GitHub.Copilot.SDK;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.GitHub.Copilot.UnitTests;

/// <summary>
/// Unit tests for the <see cref="GitHubCopilotAgent"/> reasoning event handling.
/// </summary>
public sealed class GitHubCopilotAgentReasoningTests
{
    /// <summary>
    /// Tests that ConvertToAgentResponseUpdate correctly handles AssistantReasoningDeltaEvent.
    /// </summary>
    [Fact]
    public void ConvertToAgentResponseUpdate_WithReasoningDeltaEvent_CreatesTextReasoningContent()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });
        GitHubCopilotAgent agent = new(copilotClient, sessionConfig: null, ownsClient: false);

        // Create an AssistantReasoningDeltaEvent using reflection
        AssistantReasoningDeltaEvent reasoningDeltaEvent = new()
        {
            Data = new AssistantReasoningDeltaData
            {
                ReasoningId = "reasoning-123",
                DeltaContent = "Thinking step "
            },
            Timestamp = DateTimeOffset.UtcNow
        };

        // Act - Use reflection to call the private method
        MethodInfo? method = typeof(GitHubCopilotAgent).GetMethod(
            "ConvertToAgentResponseUpdate",
            BindingFlags.NonPublic | BindingFlags.Instance,
            null,
            [typeof(AssistantReasoningDeltaEvent)],
            null);

        Assert.NotNull(method);

        AgentResponseUpdate? result = method.Invoke(agent, [reasoningDeltaEvent]) as AgentResponseUpdate;

        // Assert
        Assert.NotNull(result);
        Assert.Equal(ChatRole.Assistant, result.Role);
        Assert.NotEmpty(result.Contents);

        AIContent content = result.Contents[0];
        Assert.IsType<TextReasoningContent>(content);

        TextReasoningContent reasoningContent = (TextReasoningContent)content;
        Assert.Equal("Thinking step ", reasoningContent.Text);
        Assert.Equal(reasoningDeltaEvent, reasoningContent.RawRepresentation);
        Assert.Equal(agent.Id, result.AgentId);
        Assert.Equal(reasoningDeltaEvent.Timestamp, result.CreatedAt);
    }

    /// <summary>
    /// Tests that ConvertToAgentResponseUpdate correctly handles AssistantReasoningEvent.
    /// </summary>
    [Fact]
    public void ConvertToAgentResponseUpdate_WithReasoningEvent_CreatesTextReasoningContent()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });
        GitHubCopilotAgent agent = new(copilotClient, sessionConfig: null, ownsClient: false);

        // Create an AssistantReasoningEvent using reflection
        AssistantReasoningEvent reasoningEvent = new()
        {
            Data = new AssistantReasoningData
            {
                ReasoningId = "reasoning-456",
                Content = "Complete reasoning content"
            },
            Timestamp = DateTimeOffset.UtcNow
        };

        // Act - Use reflection to call the private method
        MethodInfo? method = typeof(GitHubCopilotAgent).GetMethod(
            "ConvertToAgentResponseUpdate",
            BindingFlags.NonPublic | BindingFlags.Instance,
            null,
            [typeof(AssistantReasoningEvent)],
            null);

        Assert.NotNull(method);

        AgentResponseUpdate? result = method.Invoke(agent, [reasoningEvent]) as AgentResponseUpdate;

        // Assert
        Assert.NotNull(result);
        Assert.Equal(ChatRole.Assistant, result.Role);
        Assert.NotEmpty(result.Contents);

        AIContent content = result.Contents[0];
        Assert.IsType<TextReasoningContent>(content);

        TextReasoningContent reasoningContent = (TextReasoningContent)content;
        Assert.Equal("Complete reasoning content", reasoningContent.Text);
        Assert.Equal(reasoningEvent, reasoningContent.RawRepresentation);
        Assert.Equal(agent.Id, result.AgentId);
        Assert.Equal(reasoningEvent.Timestamp, result.CreatedAt);
    }

    /// <summary>
    /// Tests that ConvertToAgentResponseUpdate handles null data in AssistantReasoningDeltaEvent.
    /// </summary>
    [Fact]
    public void ConvertToAgentResponseUpdate_WithNullDataInReasoningDeltaEvent_CreatesEmptyTextReasoningContent()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });
        GitHubCopilotAgent agent = new(copilotClient, sessionConfig: null, ownsClient: false);

        // Create an AssistantReasoningDeltaEvent with null data
        AssistantReasoningDeltaEvent reasoningDeltaEvent = new()
        {
            Data = null!,
            Timestamp = DateTimeOffset.UtcNow
        };

        // Act - Use reflection to call the private method
        MethodInfo? method = typeof(GitHubCopilotAgent).GetMethod(
            "ConvertToAgentResponseUpdate",
            BindingFlags.NonPublic | BindingFlags.Instance,
            null,
            [typeof(AssistantReasoningDeltaEvent)],
            null);

        Assert.NotNull(method);

        AgentResponseUpdate? result = method.Invoke(agent, [reasoningDeltaEvent]) as AgentResponseUpdate;

        // Assert
        Assert.NotNull(result);
        Assert.Equal(ChatRole.Assistant, result.Role);
        Assert.NotEmpty(result.Contents);

        AIContent content = result.Contents[0];
        Assert.IsType<TextReasoningContent>(content);

        TextReasoningContent reasoningContent = (TextReasoningContent)content;
        Assert.Equal(string.Empty, reasoningContent.Text);
    }

    /// <summary>
    /// Tests that ConvertToAgentResponseUpdate handles null content in AssistantReasoningEvent.
    /// </summary>
    [Fact]
    public void ConvertToAgentResponseUpdate_WithNullDataInReasoningEvent_CreatesEmptyTextReasoningContent()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });
        GitHubCopilotAgent agent = new(copilotClient, sessionConfig: null, ownsClient: false);

        // Create an AssistantReasoningEvent with null data
        AssistantReasoningEvent reasoningEvent = new()
        {
            Data = null!,
            Timestamp = DateTimeOffset.UtcNow
        };

        // Act - Use reflection to call the private method
        MethodInfo? method = typeof(GitHubCopilotAgent).GetMethod(
            "ConvertToAgentResponseUpdate",
            BindingFlags.NonPublic | BindingFlags.Instance,
            null,
            [typeof(AssistantReasoningEvent)],
            null);

        Assert.NotNull(method);

        AgentResponseUpdate? result = method.Invoke(agent, [reasoningEvent]) as AgentResponseUpdate;

        // Assert
        Assert.NotNull(result);
        Assert.Equal(ChatRole.Assistant, result.Role);
        Assert.NotEmpty(result.Contents);

        AIContent content = result.Contents[0];
        Assert.IsType<TextReasoningContent>(content);

        TextReasoningContent reasoningContent = (TextReasoningContent)content;
        Assert.Equal(string.Empty, reasoningContent.Text);
    }

    /// <summary>
    /// Tests that ConvertToAgentResponseUpdate handles null DeltaContent in AssistantReasoningDeltaEvent.
    /// </summary>
    [Fact]
    public void ConvertToAgentResponseUpdate_WithNullDeltaContent_CreatesEmptyTextReasoningContent()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });
        GitHubCopilotAgent agent = new(copilotClient, sessionConfig: null, ownsClient: false);

        // Create an AssistantReasoningDeltaEvent with null DeltaContent
        AssistantReasoningDeltaEvent reasoningDeltaEvent = new()
        {
            Data = new AssistantReasoningDeltaData
            {
                ReasoningId = "reasoning-789",
                DeltaContent = null!
            },
            Timestamp = DateTimeOffset.UtcNow
        };

        // Act - Use reflection to call the private method
        MethodInfo? method = typeof(GitHubCopilotAgent).GetMethod(
            "ConvertToAgentResponseUpdate",
            BindingFlags.NonPublic | BindingFlags.Instance,
            null,
            [typeof(AssistantReasoningDeltaEvent)],
            null);

        Assert.NotNull(method);

        AgentResponseUpdate? result = method.Invoke(agent, [reasoningDeltaEvent]) as AgentResponseUpdate;

        // Assert
        Assert.NotNull(result);
        AIContent content = result.Contents[0];
        TextReasoningContent reasoningContent = Assert.IsType<TextReasoningContent>(content);
        Assert.Equal(string.Empty, reasoningContent.Text);
    }

    /// <summary>
    /// Tests that ConvertToAgentResponseUpdate handles null Content in AssistantReasoningEvent.
    /// </summary>
    [Fact]
    public void ConvertToAgentResponseUpdate_WithNullContent_CreatesEmptyTextReasoningContent()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });
        GitHubCopilotAgent agent = new(copilotClient, sessionConfig: null, ownsClient: false);

        // Create an AssistantReasoningEvent with null Content
        AssistantReasoningEvent reasoningEvent = new()
        {
            Data = new AssistantReasoningData
            {
                ReasoningId = "reasoning-999",
                Content = null!
            },
            Timestamp = DateTimeOffset.UtcNow
        };

        // Act - Use reflection to call the private method
        MethodInfo? method = typeof(GitHubCopilotAgent).GetMethod(
            "ConvertToAgentResponseUpdate",
            BindingFlags.NonPublic | BindingFlags.Instance,
            null,
            [typeof(AssistantReasoningEvent)],
            null);

        Assert.NotNull(method);

        AgentResponseUpdate? result = method.Invoke(agent, [reasoningEvent]) as AgentResponseUpdate;

        // Assert
        Assert.NotNull(result);
        AIContent content = result.Contents[0];
        TextReasoningContent reasoningContent = Assert.IsType<TextReasoningContent>(content);
        Assert.Equal(string.Empty, reasoningContent.Text);
    }
}
