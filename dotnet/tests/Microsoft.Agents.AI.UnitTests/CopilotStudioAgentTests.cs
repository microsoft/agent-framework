// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Agents.AI.CopilotStudio;
using Microsoft.Agents.Core.Models;
using Microsoft.Agents.CopilotStudio.Client;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging.Abstractions;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="CopilotStudioAgent"/> class.
/// </summary>
public class CopilotStudioAgentTests
{
    private static CopilotClient CreateTestCopilotClient()
    {
        // Create mock dependencies for CopilotClient
        var mockSettings = new Mock<ConnectionSettings>();
        var mockHttpClientFactory = new Mock<IHttpClientFactory>();
        var mockHttpClient = new Mock<HttpClient>();
        mockHttpClientFactory.Setup(f => f.CreateClient(It.IsAny<string>())).Returns(mockHttpClient.Object);

        return new CopilotClient(mockSettings.Object, mockHttpClientFactory.Object, NullLogger.Instance, "test-client");
    }

    #region GetService Method Tests

    /// <summary>
    /// Verify that GetService returns CopilotClient when requested.
    /// </summary>
    [Fact]
    public void GetService_RequestingCopilotClient_ReturnsCopilotClient()
    {
        // Arrange
        var client = CreateTestCopilotClient();
        var agent = new CopilotStudioAgent(client, NullLoggerFactory.Instance);

        // Act
        var result = agent.GetService(typeof(CopilotClient));

        // Assert
        Assert.NotNull(result);
        Assert.Same(client, result);
    }

    /// <summary>
    /// Verify that GetService returns AIAgentMetadata when requested.
    /// </summary>
    [Fact]
    public void GetService_RequestingAIAgentMetadata_ReturnsMetadata()
    {
        // Arrange
        var client = CreateTestCopilotClient();
        var agent = new CopilotStudioAgent(client, NullLoggerFactory.Instance);

        // Act
        var result = agent.GetService(typeof(AIAgentMetadata));

        // Assert
        Assert.NotNull(result);
        Assert.IsType<AIAgentMetadata>(result);
        var metadata = (AIAgentMetadata)result;
        Assert.Equal("copilot-studio", metadata.ProviderName);
    }

    /// <summary>
    /// Verify that GetService returns null for unknown service types.
    /// </summary>
    [Fact]
    public void GetService_RequestingUnknownServiceType_ReturnsNull()
    {
        // Arrange
        var client = CreateTestCopilotClient();
        var agent = new CopilotStudioAgent(client, NullLoggerFactory.Instance);

        // Act
        var result = agent.GetService(typeof(string));

        // Assert
        Assert.Null(result);
    }

    /// <summary>
    /// Verify that GetService with serviceKey parameter returns null for unknown service types.
    /// </summary>
    [Fact]
    public void GetService_WithServiceKey_ReturnsNull()
    {
        // Arrange
        var client = CreateTestCopilotClient();
        var agent = new CopilotStudioAgent(client, NullLoggerFactory.Instance);

        // Act
        var result = agent.GetService(typeof(string), "test-key");

        // Assert
        Assert.Null(result);
    }

    /// <summary>
    /// Verify that GetService calls base.GetService() first and returns the agent itself when requesting CopilotStudioAgent type.
    /// </summary>
    [Fact]
    public void GetService_RequestingCopilotStudioAgentType_ReturnsBaseImplementation()
    {
        // Arrange
        var client = CreateTestCopilotClient();
        var agent = new CopilotStudioAgent(client, NullLoggerFactory.Instance);

        // Act
        var result = agent.GetService(typeof(CopilotStudioAgent));

        // Assert
        Assert.NotNull(result);
        Assert.Same(agent, result);
    }

    /// <summary>
    /// Verify that GetService calls base.GetService() first and returns the agent itself when requesting AIAgent type.
    /// </summary>
    [Fact]
    public void GetService_RequestingAIAgentType_ReturnsBaseImplementation()
    {
        // Arrange
        var client = CreateTestCopilotClient();
        var agent = new CopilotStudioAgent(client, NullLoggerFactory.Instance);

        // Act
        var result = agent.GetService(typeof(AIAgent));

        // Assert
        Assert.NotNull(result);
        Assert.Same(agent, result);
    }

    /// <summary>
    /// Verify that GetService calls base.GetService() first but continues to derived logic when base returns null.
    /// </summary>
    [Fact]
    public void GetService_RequestingCopilotClientWithServiceKey_CallsBaseFirstThenDerivedLogic()
    {
        // Arrange
        var client = CreateTestCopilotClient();
        var agent = new CopilotStudioAgent(client, NullLoggerFactory.Instance);

        // Act - Request CopilotClient with a service key (base.GetService will return null due to serviceKey)
        var result = agent.GetService(typeof(CopilotClient), "some-key");

        // Assert
        Assert.NotNull(result);
        Assert.Same(client, result);
    }

    /// <summary>
    /// Verify that GetService returns consistent AIAgentMetadata across multiple calls.
    /// </summary>
    [Fact]
    public void GetService_RequestingAIAgentMetadata_ReturnsConsistentMetadata()
    {
        // Arrange
        var client = CreateTestCopilotClient();
        var agent = new CopilotStudioAgent(client, NullLoggerFactory.Instance);

        // Act
        var result1 = agent.GetService(typeof(AIAgentMetadata));
        var result2 = agent.GetService(typeof(AIAgentMetadata));

        // Assert
        Assert.NotNull(result1);
        Assert.NotNull(result2);
        Assert.Same(result1, result2); // Should return the same instance
        Assert.IsType<AIAgentMetadata>(result1);
        var metadata = (AIAgentMetadata)result1;
        Assert.Equal("copilot-studio", metadata.ProviderName);
    }

    #endregion

    #region Metadata Mapping Tests

    /// <summary>
    /// Verify that <see cref="ActivityProcessor"/> maps the available <see cref="IActivity"/> fields,
    /// including the timestamp, onto the resulting <see cref="ChatMessage"/> in the non-streaming path.
    /// </summary>
    [Fact]
    public async Task ProcessActivity_NonStreaming_MapsActivityMetadataToChatMessage()
    {
        // Arrange
        var timestamp = new DateTimeOffset(2026, 1, 2, 3, 4, 5, TimeSpan.Zero);
        var properties = new Dictionary<string, JsonElement> { ["channelId"] = JsonDocument.Parse("\"webchat\"").RootElement };
        IActivity activity = CreateActivity("message", "Hello", "activity-1", timestamp, "bot", properties);

        // Act
        var messages = await CollectAsync(ActivityProcessor.ProcessActivityAsync(ToAsyncEnumerableAsync(activity), streaming: false, NullLogger.Instance));

        // Assert
        var message = Assert.Single(messages);
        Assert.Equal("activity-1", message.MessageId);
        Assert.Equal("bot", message.AuthorName);
        Assert.Equal(timestamp, message.CreatedAt);
        Assert.Same(activity, message.RawRepresentation);
        Assert.NotNull(message.AdditionalProperties);
        Assert.True(message.AdditionalProperties.ContainsKey("channelId"));
    }

    /// <summary>
    /// Verify that an activity without extra properties does not allocate an empty additional-properties bag.
    /// </summary>
    [Fact]
    public async Task ProcessActivity_NoActivityProperties_LeavesAdditionalPropertiesNull()
    {
        // Arrange
        var timestamp = new DateTimeOffset(2026, 1, 2, 3, 4, 5, TimeSpan.Zero);
        IActivity activity = CreateActivity("message", "Hello", "activity-1", timestamp, "bot");

        // Act
        var messages = await CollectAsync(ActivityProcessor.ProcessActivityAsync(ToAsyncEnumerableAsync(activity), streaming: false, NullLogger.Instance));

        // Assert
        var message = Assert.Single(messages);
        Assert.Null(message.AdditionalProperties);
    }

    /// <summary>
    /// Verify that the streaming path also maps the activity timestamp onto the <see cref="ChatMessage"/>.
    /// </summary>
    [Fact]
    public async Task ProcessActivity_Streaming_MapsActivityMetadataToChatMessage()
    {
        // Arrange
        var timestamp = new DateTimeOffset(2026, 1, 2, 3, 4, 5, TimeSpan.Zero);
        IActivity activity = CreateActivity("typing", "partial", "activity-2", timestamp, "bot");

        // Act
        var messages = await CollectAsync(ActivityProcessor.ProcessActivityAsync(ToAsyncEnumerableAsync(activity), streaming: true, NullLogger.Instance));

        // Assert
        var message = Assert.Single(messages);
        Assert.Equal("activity-2", message.MessageId);
        Assert.Equal(timestamp, message.CreatedAt);
        Assert.Same(activity, message.RawRepresentation);
    }

    /// <summary>
    /// Verify that the non-streaming response carries the response-level metadata expected by consumers.
    /// </summary>
    [Fact]
    public void CreateAgentResponse_PopulatesResponseMetadata()
    {
        // Arrange
        var timestamp = new DateTimeOffset(2026, 1, 2, 3, 4, 5, TimeSpan.Zero);
        var rawActivity = new object();
        var additionalProperties = new AdditionalPropertiesDictionary { ["key"] = "value" };
        var message = new ChatMessage(ChatRole.Assistant, "Hi")
        {
            MessageId = "msg-1",
            CreatedAt = timestamp,
            RawRepresentation = rawActivity,
            AdditionalProperties = additionalProperties,
        };

        // Act
        var response = CopilotStudioAgent.CreateAgentResponse([message], "agent-1");

        // Assert
        Assert.Equal("agent-1", response.AgentId);
        Assert.Equal("msg-1", response.ResponseId);
        Assert.Equal(timestamp, response.CreatedAt);
        Assert.Equal(ChatFinishReason.Stop, response.FinishReason);
        Assert.Same(rawActivity, response.RawRepresentation);
        Assert.Same(additionalProperties, response.AdditionalProperties);
        Assert.Same(message, Assert.Single(response.Messages));
    }

    /// <summary>
    /// Verify that an empty response still reports a successful completion without throwing.
    /// </summary>
    [Fact]
    public void CreateAgentResponse_NoMessages_ReportsSuccessfulCompletion()
    {
        // Act
        var response = CopilotStudioAgent.CreateAgentResponse([], "agent-1");

        // Assert
        Assert.Equal("agent-1", response.AgentId);
        Assert.Equal(ChatFinishReason.Stop, response.FinishReason);
        Assert.Null(response.ResponseId);
        Assert.Null(response.CreatedAt);
    }

    /// <summary>
    /// Verify that streaming updates carry per-update metadata and that the terminal update alone reports a finish reason.
    /// </summary>
    [Fact]
    public async Task CreateAgentResponseUpdates_SetsFinishReasonOnTerminalUpdateOnly()
    {
        // Arrange
        var firstTimestamp = new DateTimeOffset(2026, 1, 2, 3, 4, 5, TimeSpan.Zero);
        var secondTimestamp = firstTimestamp.AddSeconds(1);
        var rawActivity = new object();
        var additionalProperties = new AdditionalPropertiesDictionary { ["key"] = "value" };
        var first = new ChatMessage(ChatRole.Assistant, "part 1") { MessageId = "m1", CreatedAt = firstTimestamp };
        var second = new ChatMessage(ChatRole.Assistant, "part 2")
        {
            MessageId = "m2",
            CreatedAt = secondTimestamp,
            AuthorName = "bot",
            RawRepresentation = rawActivity,
            AdditionalProperties = additionalProperties,
        };

        // Act
        var updates = await CollectAsync(CopilotStudioAgent.CreateAgentResponseUpdatesAsync(ToAsyncEnumerableAsync(first, second), "agent-1"));

        // Assert
        Assert.Equal(2, updates.Count);
        Assert.Equal("agent-1", updates[0].AgentId);
        Assert.Equal("m1", updates[0].MessageId);
        Assert.Equal(firstTimestamp, updates[0].CreatedAt);
        Assert.Null(updates[0].FinishReason);
        Assert.Equal("m2", updates[1].MessageId);
        Assert.Equal("m2", updates[1].ResponseId);
        Assert.Equal("bot", updates[1].AuthorName);
        Assert.Equal(secondTimestamp, updates[1].CreatedAt);
        Assert.Same(rawActivity, updates[1].RawRepresentation);
        Assert.Same(additionalProperties, updates[1].AdditionalProperties);
        Assert.Equal(ChatFinishReason.Stop, updates[1].FinishReason);
    }

    /// <summary>
    /// Verify that content already received before the source stream faults is still emitted (without a finish
    /// reason) and that the original exception propagates, preserving the pre-existing streaming behavior.
    /// </summary>
    [Fact]
    public async Task CreateAgentResponseUpdates_SourceFaultsMidStream_EmitsReceivedContentThenThrows()
    {
        // Arrange
        var message = new ChatMessage(ChatRole.Assistant, "partial") { MessageId = "m1" };
        var boom = new InvalidOperationException("stream failed");
        var updates = new List<AgentResponseUpdate>();

        // Act
        var thrown = await Assert.ThrowsAsync<InvalidOperationException>(async () =>
        {
            await foreach (var update in CopilotStudioAgent.CreateAgentResponseUpdatesAsync(ThrowAfterAsync(message, boom), "agent-1"))
            {
                updates.Add(update);
            }
        });

        // Assert
        Assert.Same(boom, thrown);
        var emitted = Assert.Single(updates);
        Assert.Equal("m1", emitted.MessageId);
        Assert.Null(emitted.FinishReason);
    }

    /// <summary>
    /// Verify that a single streaming update is treated as the terminal update.
    /// </summary>
    [Fact]
    public async Task CreateAgentResponseUpdates_SingleMessage_SetsFinishReason()
    {
        // Arrange
        var message = new ChatMessage(ChatRole.Assistant, "only") { MessageId = "m1" };

        // Act
        var updates = await CollectAsync(CopilotStudioAgent.CreateAgentResponseUpdatesAsync(ToAsyncEnumerableAsync(message), "agent-1"));

        // Assert
        var update = Assert.Single(updates);
        Assert.Equal(ChatFinishReason.Stop, update.FinishReason);
    }

    private static IActivity CreateActivity(string type, string text, string id, DateTimeOffset timestamp, string authorName, IDictionary<string, JsonElement>? properties = null)
    {
        var activity = new Mock<IActivity>();
        activity.SetupGet(a => a.Type).Returns(type);
        activity.SetupGet(a => a.Text).Returns(text);
        activity.SetupGet(a => a.Id).Returns(id);
        activity.SetupGet(a => a.Timestamp).Returns(timestamp);
        activity.SetupGet(a => a.From).Returns(new ChannelAccount { Name = authorName });
        activity.SetupGet(a => a.Properties).Returns(properties!);
        return activity.Object;
    }

    private static async IAsyncEnumerable<ChatMessage> ThrowAfterAsync(ChatMessage message, Exception exception)
    {
        yield return message;
        await Task.CompletedTask;
        throw exception;
    }

    private static async IAsyncEnumerable<T> ToAsyncEnumerableAsync<T>(params T[] items)
    {
        foreach (var item in items)
        {
            yield return item;
        }

        await Task.CompletedTask;
    }

    private static async Task<List<T>> CollectAsync<T>(IAsyncEnumerable<T> source)
    {
        var items = new List<T>();
        await foreach (var item in source)
        {
            items.Add(item);
        }

        return items;
    }

    #endregion
}
