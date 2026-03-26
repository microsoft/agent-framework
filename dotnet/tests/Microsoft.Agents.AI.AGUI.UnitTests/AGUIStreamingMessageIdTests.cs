// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.AGUI.Shared;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AGUI.UnitTests;

/// <summary>
/// Tests for AGUI streaming behavior when MessageId is null or missing from
/// ChatResponseUpdate objects (e.g., providers like Google GenAI/Vertex AI
/// that don't supply MessageId on streaming chunks).
/// </summary>
public sealed class AGUIStreamingMessageIdTests
{
    /// <summary>
    /// When ChatResponseUpdate objects with null MessageId are fed directly to
    /// AsAGUIEventStreamAsync, the AGUI layer generates a fallback MessageId so
    /// that events are valid regardless of agent type or provider.
    /// </summary>
    [Fact]
    public async Task TextStreaming_NullMessageId_GeneratesFallbackInAGUILayerAsync()
    {
        // Arrange - Simulate a provider that does NOT set MessageId
        List<ChatResponseUpdate> providerUpdates =
        [
            new ChatResponseUpdate(ChatRole.Assistant, "Hello"),
            new ChatResponseUpdate(ChatRole.Assistant, " world"),
            new ChatResponseUpdate(ChatRole.Assistant, "!")
        ];

        // Act
        List<BaseEvent> aguiEvents = [];
        await foreach (BaseEvent evt in providerUpdates.ToAsyncEnumerableAsync()
            .AsAGUIEventStreamAsync("thread-1", "run-1", AGUIJsonSerializerContext.Default.Options))
        {
            aguiEvents.Add(evt);
        }

        // Assert - AGUI layer should generate a fallback MessageId
        List<TextMessageStartEvent> startEvents = aguiEvents.OfType<TextMessageStartEvent>().ToList();
        List<TextMessageContentEvent> contentEvents = aguiEvents.OfType<TextMessageContentEvent>().ToList();

        Assert.Single(startEvents);
        Assert.False(string.IsNullOrEmpty(startEvents[0].MessageId));

        Assert.Equal(3, contentEvents.Count);
        Assert.All(contentEvents, e => Assert.False(string.IsNullOrEmpty(e.MessageId)));

        // All events should share the same generated MessageId
        string?[] distinctIds = contentEvents.Select(e => e.MessageId).Distinct().ToArray();
        Assert.Single(distinctIds);
        Assert.Equal(startEvents[0].MessageId, distinctIds[0]);
    }

    /// <summary>
    /// Full pipeline: ChatClientAgent → AsChatResponseUpdatesAsync → AsAGUIEventStreamAsync
    /// with a provider that returns null MessageId. Verifies that fallback MessageId
    /// generation ensures valid AGUI events.
    /// </summary>
    [Fact]
    public async Task FullPipeline_NullProviderMessageId_ProducesValidAGUIEventsAsync()
    {
        // Arrange - ChatClientAgent with a mock client that omits MessageId
        IChatClient mockChatClient = new NullMessageIdChatClient();
        ChatClientAgent agent = new(mockChatClient, name: "test-agent");

        ChatMessage userMessage = new(ChatRole.User, "tell me about agents");

        // Act - Run the full pipeline exactly as MapAGUI does
        List<BaseEvent> aguiEvents = [];
        await foreach (BaseEvent evt in agent
            .RunStreamingAsync([userMessage])
            .AsChatResponseUpdatesAsync()
            .AsAGUIEventStreamAsync("thread-1", "run-1", AGUIJsonSerializerContext.Default.Options))
        {
            aguiEvents.Add(evt);
        }

        // Assert — The pipeline should produce AGUI events with valid messageId
        List<TextMessageStartEvent> startEvents = aguiEvents.OfType<TextMessageStartEvent>().ToList();
        List<TextMessageContentEvent> contentEvents = aguiEvents.OfType<TextMessageContentEvent>().ToList();

        Assert.NotEmpty(startEvents);
        Assert.NotEmpty(contentEvents);

        foreach (TextMessageStartEvent startEvent in startEvents)
        {
            Assert.False(
                string.IsNullOrEmpty(startEvent.MessageId),
                "TextMessageStartEvent.MessageId should not be null/empty when provider omits it");
        }

        foreach (TextMessageContentEvent contentEvent in contentEvents)
        {
            Assert.False(
                string.IsNullOrEmpty(contentEvent.MessageId),
                "TextMessageContentEvent.MessageId should not be null/empty when provider omits it");
        }

        // All content events should share the same messageId
        string?[] distinctMessageIds = contentEvents.Select(e => e.MessageId).Distinct().ToArray();
        Assert.Single(distinctMessageIds);
    }

    /// <summary>
    /// When ChatResponseUpdate has empty string MessageId, the AGUI layer generates
    /// a fallback so ToolCallStartEvent.ParentMessageId is valid.
    /// </summary>
    [Fact]
    public async Task ToolCalls_EmptyMessageId_GeneratesFallbackParentMessageIdAsync()
    {
        // Arrange - ChatResponseUpdate with a tool call but empty MessageId
        FunctionCallContent functionCall = new("call_abc123", "GetWeather")
        {
            Arguments = new Dictionary<string, object?> { ["location"] = "San Francisco" }
        };

        List<ChatResponseUpdate> providerUpdates =
        [
            new ChatResponseUpdate
            {
                Role = ChatRole.Assistant,
                MessageId = "",
                Contents = [functionCall]
            }
        ];

        // Act
        List<BaseEvent> aguiEvents = [];
        await foreach (BaseEvent evt in providerUpdates.ToAsyncEnumerableAsync()
            .AsAGUIEventStreamAsync("thread-1", "run-1", AGUIJsonSerializerContext.Default.Options))
        {
            aguiEvents.Add(evt);
        }

        // Assert — ParentMessageId should have a generated fallback
        ToolCallStartEvent? toolCallStart = aguiEvents.OfType<ToolCallStartEvent>().FirstOrDefault();
        Assert.NotNull(toolCallStart);
        Assert.Equal("call_abc123", toolCallStart.ToolCallId);
        Assert.Equal("GetWeather", toolCallStart.ToolCallName);
        Assert.False(
            string.IsNullOrEmpty(toolCallStart.ParentMessageId),
            "ParentMessageId should have a generated fallback for empty provider MessageId");
    }

    /// <summary>
    /// When a provider properly sets MessageId (e.g., OpenAI), the AGUI pipeline
    /// produces valid events with correct messageId values.
    /// </summary>
    [Fact]
    public async Task TextStreaming_WithProviderMessageId_ProducesValidAGUIEventsAsync()
    {
        // Arrange — Provider that properly sets MessageId
        List<ChatResponseUpdate> providerUpdates =
        [
            new ChatResponseUpdate(ChatRole.Assistant, "Hello")
            {
                MessageId = "chatcmpl-abc123"
            },
            new ChatResponseUpdate(ChatRole.Assistant, " world")
            {
                MessageId = "chatcmpl-abc123"
            }
        ];

        // Act
        List<BaseEvent> aguiEvents = [];
        await foreach (BaseEvent evt in providerUpdates.ToAsyncEnumerableAsync()
            .AsAGUIEventStreamAsync("thread-1", "run-1", AGUIJsonSerializerContext.Default.Options))
        {
            aguiEvents.Add(evt);
        }

        // Assert
        List<TextMessageStartEvent> startEvents = aguiEvents.OfType<TextMessageStartEvent>().ToList();
        List<TextMessageContentEvent> contentEvents = aguiEvents.OfType<TextMessageContentEvent>().ToList();

        Assert.Single(startEvents);
        Assert.Equal("chatcmpl-abc123", startEvents[0].MessageId);

        Assert.Equal(2, contentEvents.Count);
        Assert.All(contentEvents, e => Assert.Equal("chatcmpl-abc123", e.MessageId));
    }
}

/// <summary>
/// Mock IChatClient that simulates a provider not setting MessageId on streaming chunks
/// (e.g., Google GenAI / Vertex AI).
/// </summary>
internal sealed class NullMessageIdChatClient : IChatClient
{
    public void Dispose()
    {
    }

    public object? GetService(Type serviceType, object? serviceKey = null) => null;

    public Task<ChatResponse> GetResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        return Task.FromResult(new ChatResponse([new(ChatRole.Assistant, "response")]));
    }

    public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        foreach (string chunk in (string[])["Agents", " are", " autonomous", " programs."])
        {
            yield return new ChatResponseUpdate
            {
                Role = ChatRole.Assistant,
                Contents = [new TextContent(chunk)]
            };

            await Task.Yield();
        }
    }
}
