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
    /// When ChatResponseUpdate has empty string MessageId, the AGUI layer passes
    /// through the raw provider value for ToolCallStartEvent.ParentMessageId.
    /// Tool-call chunks should NOT receive the text-event fallback GUID — that
    /// would collapse parallel tool calls into one assistant message in the FE.
    /// </summary>
    [Fact]
    public async Task ToolCalls_EmptyMessageId_DoesNotGenerateFallbackParentMessageIdAsync()
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

        // Assert — ParentMessageId should be empty (raw provider value, no synthetic fallback)
        ToolCallStartEvent? toolCallStart = aguiEvents.OfType<ToolCallStartEvent>().FirstOrDefault();
        Assert.NotNull(toolCallStart);
        Assert.Equal("call_abc123", toolCallStart.ToolCallId);
        Assert.Equal("GetWeather", toolCallStart.ToolCallName);
        Assert.True(
            string.IsNullOrEmpty(toolCallStart.ParentMessageId),
            "ParentMessageId should be empty when provider omits MessageId (raw pass-through)");
    }

    /// <summary>
    /// Tool results are separate tool-role messages, so their fallback IDs must not
    /// collide with the assistant message that requested the tool call.
    /// </summary>
    [Fact]
    public async Task ToolResults_NullMessageId_GeneratesDistinctMessageIdAsync()
    {
        FunctionCallContent functionCall = new("call_abc123", "GetWeather")
        {
            Arguments = new Dictionary<string, object?> { ["location"] = "San Francisco" }
        };

        List<ChatResponseUpdate> providerUpdates =
        [
            new ChatResponseUpdate(ChatRole.Assistant, "Checking the weather"),
            new ChatResponseUpdate
            {
                Role = ChatRole.Assistant,
                Contents = [functionCall]
            },
            new ChatResponseUpdate(ChatRole.Tool, [new FunctionResultContent("call_abc123", "72F and sunny")])
        ];

        List<BaseEvent> aguiEvents = [];
        await foreach (BaseEvent evt in providerUpdates.ToAsyncEnumerableAsync()
            .AsAGUIEventStreamAsync("thread-1", "run-1", AGUIJsonSerializerContext.Default.Options))
        {
            aguiEvents.Add(evt);
        }

        TextMessageStartEvent textStart = Assert.Single(aguiEvents.OfType<TextMessageStartEvent>());
        ToolCallStartEvent toolCallStart = Assert.Single(aguiEvents.OfType<ToolCallStartEvent>());
        ToolCallResultEvent toolCallResult = Assert.Single(aguiEvents.OfType<ToolCallResultEvent>());

        // Tool-call ParentMessageId should NOT leak the text fallback GUID
        Assert.NotEqual(textStart.MessageId, toolCallStart.ParentMessageId);
        Assert.Equal("call_abc123", toolCallResult.ToolCallId);
        Assert.False(string.IsNullOrEmpty(toolCallResult.MessageId));
        Assert.NotEqual(textStart.MessageId, toolCallResult.MessageId);
        // Result MessageId should be deterministic based on CallId
        Assert.Equal("result-call_abc123", toolCallResult.MessageId);
    }

    [Fact]
    public async Task ToolResults_WithTextContent_GeneratesDistinctMessageIdAsync()
    {
        FunctionCallContent functionCall = new("call_abc123", "GetWeather")
        {
            Arguments = new Dictionary<string, object?> { ["location"] = "San Francisco" }
        };

        List<ChatResponseUpdate> providerUpdates =
        [
            new ChatResponseUpdate(ChatRole.Assistant, "Checking the weather"),
            new ChatResponseUpdate
            {
                Role = ChatRole.Assistant,
                Contents = [functionCall]
            },
            new ChatResponseUpdate
            {
                Role = ChatRole.Tool,
                Contents =
                [
                    new TextContent("Tool says: "),
                    new FunctionResultContent("call_abc123", "72F and sunny")
                ]
            }
        ];

        List<BaseEvent> aguiEvents = [];
        await foreach (BaseEvent evt in providerUpdates.ToAsyncEnumerableAsync()
            .AsAGUIEventStreamAsync("thread-1", "run-1", AGUIJsonSerializerContext.Default.Options))
        {
            aguiEvents.Add(evt);
        }

        TextMessageStartEvent[] textStarts = aguiEvents.OfType<TextMessageStartEvent>().ToArray();
        TextMessageContentEvent toolText = Assert.Single(
            aguiEvents.OfType<TextMessageContentEvent>(),
            content => content.Delta == "Tool says: ");
        ToolCallStartEvent toolCallStart = Assert.Single(aguiEvents.OfType<ToolCallStartEvent>());
        ToolCallResultEvent toolCallResult = Assert.Single(aguiEvents.OfType<ToolCallResultEvent>());

        // Tool-call ParentMessageId should NOT leak the text fallback GUID
        Assert.NotEqual(textStarts[0].MessageId, toolCallStart.ParentMessageId);
        Assert.NotEqual(textStarts[0].MessageId, toolCallResult.MessageId);
        // Result MessageId should be deterministic based on CallId
        Assert.Equal("result-call_abc123", toolCallResult.MessageId);
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

    /// <summary>
    /// Bug #1 reproduction: parallel tool calls with empty MessageId should NOT all
    /// share the same synthetic ParentMessageId. Each should pass through the raw
    /// provider value (empty), allowing the FE to render them as distinct cards.
    /// </summary>
    [Fact]
    public async Task ParallelToolCalls_EmptyMessageId_DoNotShareParentMessageIdAsync()
    {
        // Arrange — 3 parallel tool calls with empty MessageId (real OpenAI behavior)
        List<ChatResponseUpdate> providerUpdates =
        [
            new ChatResponseUpdate(ChatRole.Assistant, "Let me run those queries.") { MessageId = "chatcmpl-real" },
            new ChatResponseUpdate { Role = ChatRole.Assistant, MessageId = "", Contents = [new FunctionCallContent("call_A", "query") { Arguments = new Dictionary<string, object?> { ["q"] = "1" } }] },
            new ChatResponseUpdate { Role = ChatRole.Assistant, MessageId = "", Contents = [new FunctionCallContent("call_B", "query") { Arguments = new Dictionary<string, object?> { ["q"] = "2" } }] },
            new ChatResponseUpdate { Role = ChatRole.Assistant, MessageId = "", Contents = [new FunctionCallContent("call_C", "query") { Arguments = new Dictionary<string, object?> { ["q"] = "3" } }] },
        ];

        // Act
        List<BaseEvent> aguiEvents = [];
        await foreach (BaseEvent evt in providerUpdates.ToAsyncEnumerableAsync()
            .AsAGUIEventStreamAsync("thread-1", "run-1", AGUIJsonSerializerContext.Default.Options))
        {
            aguiEvents.Add(evt);
        }

        // Assert — all 3 tool calls should have empty ParentMessageId (raw provider value),
        // NOT the text fallback GUID
        List<ToolCallStartEvent> toolCallStarts = aguiEvents.OfType<ToolCallStartEvent>().ToList();
        Assert.Equal(3, toolCallStarts.Count);
        Assert.All(toolCallStarts, tc => Assert.True(string.IsNullOrEmpty(tc.ParentMessageId)));

        // Text events should still have a valid fallback MessageId
        TextMessageStartEvent textStart = Assert.Single(aguiEvents.OfType<TextMessageStartEvent>());
        Assert.False(string.IsNullOrEmpty(textStart.MessageId));
    }

    /// <summary>
    /// Bug #2 reproduction: tool results batched into one ChatResponseUpdate with a
    /// shared MEAI MessageId should each get a unique deterministic MessageId.
    /// </summary>
    [Fact]
    public async Task ToolCallResults_SharedMeaiMessageId_HaveUniqueMessageIdsPerCallAsync()
    {
        // Arrange — MEAI batches all FunctionResultContent into one update with shared id
        List<ChatResponseUpdate> providerUpdates =
        [
            new ChatResponseUpdate
            {
                Role = ChatRole.Tool,
                MessageId = "meai-shared-id",
                Contents =
                [
                    new FunctionResultContent("call_A", "result1"),
                    new FunctionResultContent("call_B", "result2"),
                    new FunctionResultContent("call_C", "result3"),
                ]
            },
        ];

        // Act
        List<BaseEvent> aguiEvents = [];
        await foreach (BaseEvent evt in providerUpdates.ToAsyncEnumerableAsync()
            .AsAGUIEventStreamAsync("thread-1", "run-1", AGUIJsonSerializerContext.Default.Options))
        {
            aguiEvents.Add(evt);
        }

        // Assert — each result should have a unique MessageId
        List<ToolCallResultEvent> toolResults = aguiEvents.OfType<ToolCallResultEvent>().ToList();
        Assert.Equal(3, toolResults.Count);

        string?[] distinctIds = toolResults.Select(r => r.MessageId).Distinct().ToArray();
        Assert.Equal(3, distinctIds.Length);

        // Verify deterministic format
        Assert.Equal("result-call_A", toolResults[0].MessageId);
        Assert.Equal("result-call_B", toolResults[1].MessageId);
        Assert.Equal("result-call_C", toolResults[2].MessageId);
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
