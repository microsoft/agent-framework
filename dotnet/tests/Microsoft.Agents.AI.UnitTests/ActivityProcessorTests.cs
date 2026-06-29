// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Agents.AI.CopilotStudio;
using Microsoft.Agents.Core.Models;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging.Abstractions;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests for <see cref="ActivityProcessor"/>.
/// </summary>
public class ActivityProcessorTests
{
    [Fact]
    public async Task ProcessActivityAsync_WithTimestamp_SetsCreatedAtAsync()
    {
        // Arrange
        DateTimeOffset timestamp = new(2026, 6, 29, 12, 0, 0, TimeSpan.Zero);
        Activity activity = CreateMessageActivity("activity-1", "Hello", timestamp: timestamp);

        // Act
        ChatMessage message = await GetSingleMessageAsync(
            ActivityProcessor.ProcessActivityAsync(CreateActivitiesAsync(activity), streaming: false, NullLogger.Instance));

        // Assert
        Assert.Equal(timestamp, message.CreatedAt);
    }

    [Fact]
    public async Task ProcessActivityAsync_WithLocalTimestampOnly_SetsCreatedAtAsync()
    {
        // Arrange
        DateTimeOffset localTimestamp = new(2026, 6, 29, 15, 0, 0, TimeSpan.Zero);
        Activity activity = CreateMessageActivity("activity-1", "Hello", localTimestamp: localTimestamp);

        // Act
        ChatMessage message = await GetSingleMessageAsync(
            ActivityProcessor.ProcessActivityAsync(CreateActivitiesAsync(activity), streaming: false, NullLogger.Instance));

        // Assert
        Assert.Equal(localTimestamp, message.CreatedAt);
    }

    [Fact]
    public async Task ProcessActivityAsync_WithProperties_SetsAdditionalPropertiesAsync()
    {
        // Arrange
        Activity activity = CreateMessageActivity("activity-1", "Hello", timestamp: new DateTimeOffset(2026, 6, 29, 12, 0, 0, TimeSpan.Zero));
        activity.Properties = new Dictionary<string, JsonElement>
        {
            ["conversationId"] = JsonSerializer.SerializeToElement("conversation-123", AIJsonUtilities.DefaultOptions),
        };

        // Act
        ChatMessage message = await GetSingleMessageAsync(
            ActivityProcessor.ProcessActivityAsync(CreateActivitiesAsync(activity), streaming: false, NullLogger.Instance));

        // Assert
        Assert.NotNull(message.AdditionalProperties);
        Assert.True(message.AdditionalProperties.TryGetValue("conversationId", out object? value));
        Assert.Equal("conversation-123", Assert.IsType<JsonElement>(value).GetString());
    }

    [Fact]
    public void CreateAgentResponse_WithMessagesAndActivity_SetsResponseMetadata()
    {
        // Arrange
        DateTimeOffset createdAt = new(2026, 6, 29, 12, 0, 0, TimeSpan.Zero);
        Activity activity = CreateMessageActivity("activity-1", "Hello", timestamp: createdAt);
        ChatMessage message = new(ChatRole.Assistant, [new TextContent("Hello")])
        {
            MessageId = activity.Id,
            CreatedAt = createdAt,
            RawRepresentation = activity,
        };

        // Act
        AgentResponse response = ActivityProcessor.CreateAgentResponse("agent-1", [message], activity);

        // Assert
        Assert.Equal("agent-1", response.AgentId);
        Assert.Equal("activity-1", response.ResponseId);
        Assert.Equal(createdAt, response.CreatedAt);
        Assert.Equal(ChatFinishReason.Stop, response.FinishReason);
        Assert.Same(activity, response.RawRepresentation);
    }

    [Fact]
    public void CreateAgentResponse_WithNoMessages_DoesNotSetFinishReason()
    {
        // Arrange & Act
        AgentResponse response = ActivityProcessor.CreateAgentResponse("agent-1", [], lastActivity: null);

        // Assert
        Assert.Null(response.FinishReason);
        Assert.Null(response.ResponseId);
        Assert.Null(response.RawRepresentation);
    }

    [Fact]
    public void CreateAgentResponseUpdate_WithTerminalUpdate_SetsFinishReason()
    {
        // Arrange
        DateTimeOffset createdAt = new(2026, 6, 29, 12, 0, 0, TimeSpan.Zero);
        ChatMessage message = new(ChatRole.Assistant, [new TextContent("Hello")])
        {
            MessageId = "activity-1",
            CreatedAt = createdAt,
        };

        // Act
        AgentResponseUpdate intermediateUpdate = ActivityProcessor.CreateAgentResponseUpdate("agent-1", message, isTerminalUpdate: false);
        AgentResponseUpdate terminalUpdate = ActivityProcessor.CreateAgentResponseUpdate("agent-1", message, isTerminalUpdate: true);

        // Assert
        Assert.Null(intermediateUpdate.FinishReason);
        Assert.Equal(ChatFinishReason.Stop, terminalUpdate.FinishReason);
        Assert.Equal(createdAt, terminalUpdate.CreatedAt);
        Assert.Equal("activity-1", terminalUpdate.MessageId);
        Assert.Equal("activity-1", terminalUpdate.ResponseId);
    }

    [Fact]
    public async Task ProcessActivityAsync_WithTypingActivityWhenStreaming_ReturnsChatMessageAsync()
    {
        // Arrange
        DateTimeOffset timestamp = new(2026, 6, 29, 12, 0, 0, TimeSpan.Zero);
        Activity activity = CreateTypingActivity("activity-1", "Hello", timestamp: timestamp);

        // Act
        ChatMessage message = await GetSingleMessageAsync(
            ActivityProcessor.ProcessActivityAsync(CreateActivitiesAsync(activity), streaming: true, NullLogger.Instance));

        // Assert
        Assert.Equal("Hello", message.Text);
        Assert.Equal(timestamp, message.CreatedAt);
    }

    private static Activity CreateMessageActivity(string id, string text, DateTimeOffset? timestamp = null, DateTimeOffset? localTimestamp = null)
    {
        return new Activity
        {
            Type = "message",
            Id = id,
            Text = text,
            Timestamp = timestamp,
            LocalTimestamp = localTimestamp,
            From = new ChannelAccount { Name = "copilot" },
        };
    }

    private static Activity CreateTypingActivity(string id, string text, DateTimeOffset? timestamp = null)
    {
        return new Activity
        {
            Type = "typing",
            Id = id,
            Text = text,
            Timestamp = timestamp,
            From = new ChannelAccount { Name = "copilot" },
        };
    }

    private static async Task<ChatMessage> GetSingleMessageAsync(IAsyncEnumerable<ChatMessage> messages)
    {
        List<ChatMessage> collectedMessages = [];
        await foreach (ChatMessage message in messages.ConfigureAwait(false))
        {
            collectedMessages.Add(message);
        }

        return Assert.Single(collectedMessages);
    }

    private static async IAsyncEnumerable<IActivity> CreateActivitiesAsync(params IActivity[] activities)
    {
        foreach (IActivity activity in activities)
        {
            yield return activity;
            await Task.Yield();
        }
    }
}
