// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.UnitTests;

/// <summary>
/// Tests verifying that Usage (token consumption) and Annotations (citations, file references)
/// are properly preserved when converting ChatResponseUpdates to AG-UI SSE events.
/// Regression tests for https://github.com/microsoft/agent-framework/issues/3752.
/// </summary>
public sealed class UsageAndAnnotationsTests
{
    private const string ThreadId = "thread1";
    private const string RunId = "run1";

    #region Usage Tests

    [Fact]
    public async Task AsAGUIEventStreamAsync_WithUsageContent_DoesNotThrowAsync()
    {
        // Arrange — ChatResponseUpdate containing UsageContent alongside text
        List<ChatResponseUpdate> updates =
        [
            new ChatResponseUpdate(ChatRole.Assistant, "Hello") { MessageId = "msg1" },
            new ChatResponseUpdate
            {
                Role = ChatRole.Assistant,
                Contents = [new UsageContent(new UsageDetails
                {
                    InputTokenCount = 100,
                    OutputTokenCount = 50,
                    TotalTokenCount = 150
                })],
                MessageId = "msg1"
            }
        ];

        // Act — Should not throw when handling UsageContent mapped to a CustomEvent
        List<BaseEvent> events = [];
        await foreach (BaseEvent evt in updates.ToAsyncEnumerableAsync()
            .AsAGUIEventStreamAsync(ThreadId, RunId, AGUIJsonSerializerContext.Default.Options, CancellationToken.None))
        {
            events.Add(evt);
        }

        // Assert — Stream should at least contain lifecycle events
        Assert.Contains(events, e => e is RunStartedEvent);
        Assert.Contains(events, e => e is RunFinishedEvent);
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_WithUsageContentOnly_UsageDataIsNotSilentlyDroppedAsync()
    {
        // Arrange — Baseline: empty stream produces only RunStarted + RunFinished
        List<ChatResponseUpdate> baselineUpdates = [];
        List<BaseEvent> baselineEvents = await CollectEventsAsync(baselineUpdates);
        int baselineCount = baselineEvents.Count;

        // Test: stream with UsageContent only (no text, no tool calls)
        List<ChatResponseUpdate> usageUpdates =
        [
            new ChatResponseUpdate
            {
                Role = ChatRole.Assistant,
                Contents = [new UsageContent(new UsageDetails
                {
                    InputTokenCount = 250,
                    OutputTokenCount = 120,
                    TotalTokenCount = 370
                })],
                MessageId = "msg1"
            }
        ];
        List<BaseEvent> usageEvents = await CollectEventsAsync(usageUpdates);

        // Assert — Usage data should produce at least one additional event beyond lifecycle events.
        // Currently (before fix), UsageContent is silently dropped and usageEvents.Count == baselineCount.
        Assert.True(
            usageEvents.Count > baselineCount,
            "UsageContent should produce additional events beyond lifecycle events. " +
            "Got " + usageEvents.Count + " events, same as baseline (" + baselineCount + "). " +
            "Usage data (InputTokenCount=250, OutputTokenCount=120) is being silently dropped. " +
            "See https://github.com/microsoft/agent-framework/issues/3752");
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_WithUsageContentAndText_BothContentTypesPreservedAsync()
    {
        // Arrange — A realistic scenario: agent returns text + usage in the same response
        List<ChatResponseUpdate> updates =
        [
            new ChatResponseUpdate(ChatRole.Assistant, "Here is the answer.") { MessageId = "msg1" },
            new ChatResponseUpdate
            {
                Role = ChatRole.Assistant,
                Contents = [new UsageContent(new UsageDetails
                {
                    InputTokenCount = 45,
                    OutputTokenCount = 12,
                    TotalTokenCount = 57
                })],
                MessageId = "msg1"
            }
        ];

        List<BaseEvent> events = await CollectEventsAsync(updates);

        // Assert — Text content should produce text events
        Assert.Contains(events, e => e is TextMessageStartEvent);
        Assert.Contains(events, e => e is TextMessageContentEvent tce && tce.Delta == "Here is the answer.");
        Assert.Contains(events, e => e is TextMessageEndEvent);

        // Assert — Usage data should ALSO be present somewhere in the event stream
        // Excluding lifecycle events and text events, there should be at least one event for usage
        int textAndLifecycleCount = events.Count(e =>
            e is RunStartedEvent or RunFinishedEvent or
            TextMessageStartEvent or TextMessageContentEvent or TextMessageEndEvent);

        Assert.True(
            events.Count > textAndLifecycleCount,
            "When both text and usage content are present, usage data should produce additional events. " +
            $"Total events: {events.Count}, text+lifecycle events: {textAndLifecycleCount}. " +
            "Usage data is being silently dropped. " +
            "See https://github.com/microsoft/agent-framework/issues/3752");
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_WithUsageContent_UsageTokenCountsAccessibleInEventsAsync()
    {
        // Arrange
        List<ChatResponseUpdate> updates =
        [
            new ChatResponseUpdate(ChatRole.Assistant, "Response text") { MessageId = "msg1" },
            new ChatResponseUpdate
            {
                Role = ChatRole.Assistant,
                Contents = [new UsageContent(new UsageDetails
                {
                    InputTokenCount = 500,
                    OutputTokenCount = 200,
                    TotalTokenCount = 700
                })],
                MessageId = "msg1"
            }
        ];

        List<BaseEvent> events = await CollectEventsAsync(updates);

        // Assert — Serialize all events to JSON and check that token counts appear
        string allEventsJson = SerializeAllEvents(events);

        // The token counts should be present in the serialized event stream
        Assert.True(
            allEventsJson.Contains("500") || allEventsJson.Contains("input"),
            "InputTokenCount (500) should be present in the serialized AGUI events. " +
            "See https://github.com/microsoft/agent-framework/issues/3752");
        Assert.True(
            allEventsJson.Contains("200") || allEventsJson.Contains("output"),
            "OutputTokenCount (200) should be present in the serialized AGUI events. " +
            "See https://github.com/microsoft/agent-framework/issues/3752");
    }

    #endregion

    #region Annotations Tests

    [Fact]
    public async Task AsAGUIEventStreamAsync_WithAnnotatedTextContent_DoesNotThrowAsync()
    {
        // Arrange — TextContent with annotations (citations)
        TextContent textContent = new("According to research, the answer is 42.");
        textContent.Annotations =
        [
            new CitationAnnotation
            {
                Url = new System.Uri("https://example.com/source"),
                Title = "Source Document"
            }
        ];

        List<ChatResponseUpdate> updates =
        [
            new ChatResponseUpdate
            {
                Role = ChatRole.Assistant,
                Contents = [textContent],
                MessageId = "msg1"
            }
        ];

        // Act — Should not throw even if annotations are not mapped
        List<BaseEvent> events = await CollectEventsAsync(updates);

        // Assert — Text content should still be emitted
        Assert.Contains(events, e => e is TextMessageContentEvent tce && tce.Delta.Contains("42"));
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_WithAnnotatedTextContent_AnnotationDataNotSilentlyDroppedAsync()
    {
        // Arrange — TextContent with citation annotations
        TextContent textContent = new("The earth orbits the sun.");
        textContent.Annotations =
        [
            new CitationAnnotation
            {
                Url = new System.Uri("https://example.com/astronomy-source"),
                Title = "Astronomy 101"
            }
        ];

        List<ChatResponseUpdate> updates =
        [
            new ChatResponseUpdate
            {
                Role = ChatRole.Assistant,
                Contents = [textContent],
                MessageId = "msg1"
            }
        ];

        List<BaseEvent> events = await CollectEventsAsync(updates);

        // Assert — Annotation data (URL, title) should be present somewhere in the event stream
        string allEventsJson = SerializeAllEvents(events);

        Assert.True(
            allEventsJson.Contains("example.com/astronomy-source") ||
            allEventsJson.Contains("Astronomy 101") ||
            allEventsJson.Contains("annotation"),
            "Annotation data (URL: 'https://example.com/astronomy-source', Title: 'Astronomy 101') " +
            "should be present in AGUI events. Annotations are being silently dropped. " +
            "See https://github.com/microsoft/agent-framework/issues/3752");
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_WithMultipleAnnotations_AllAnnotationsPreservedAsync()
    {
        // Arrange — TextContent with multiple citation annotations
        TextContent textContent = new("Summary based on multiple sources.");
        textContent.Annotations =
        [
            new CitationAnnotation
            {
                Url = new System.Uri("https://source-a.com/doc"),
                Title = "Source A"
            },
            new CitationAnnotation
            {
                Url = new System.Uri("https://source-b.com/paper"),
                Title = "Source B"
            }
        ];

        List<ChatResponseUpdate> updates =
        [
            new ChatResponseUpdate
            {
                Role = ChatRole.Assistant,
                Contents = [textContent],
                MessageId = "msg1"
            }
        ];

        List<BaseEvent> events = await CollectEventsAsync(updates);
        string allEventsJson = SerializeAllEvents(events);

        // Assert — Both annotations should be present
        Assert.True(
            allEventsJson.Contains("source-a.com") || allEventsJson.Contains("Source A"),
            "First annotation (Source A) should be present in AGUI events. " +
            "See https://github.com/microsoft/agent-framework/issues/3752");
        Assert.True(
            allEventsJson.Contains("source-b.com") || allEventsJson.Contains("Source B"),
            "Second annotation (Source B) should be present in AGUI events. " +
            "See https://github.com/microsoft/agent-framework/issues/3752");
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_WithAnnotationsOnStreamingText_AnnotationsPreservedAsync()
    {
        // Arrange — Streaming scenario: multiple text deltas, last one carries annotations
        TextContent delta1 = new("Hello ");
        TextContent delta2 = new("world.");
        delta2.Annotations =
        [
            new CitationAnnotation
            {
                Url = new System.Uri("https://reference.com/greeting"),
                Title = "Greeting Reference"
            }
        ];

        List<ChatResponseUpdate> updates =
        [
            new ChatResponseUpdate
            {
                Role = ChatRole.Assistant,
                Contents = [delta1],
                MessageId = "msg1"
            },
            new ChatResponseUpdate
            {
                Role = ChatRole.Assistant,
                Contents = [delta2],
                MessageId = "msg1"
            }
        ];

        List<BaseEvent> events = await CollectEventsAsync(updates);
        string allEventsJson = SerializeAllEvents(events);

        // Assert — Annotation on the last delta should not be lost
        Assert.True(
            allEventsJson.Contains("reference.com/greeting") ||
            allEventsJson.Contains("Greeting Reference"),
            "Annotations on streaming text deltas should be preserved in AGUI events. " +
            "See https://github.com/microsoft/agent-framework/issues/3752");
    }

    #endregion

    #region Combined Tests

    [Fact]
    public async Task AsAGUIEventStreamAsync_WithTextAnnotationsAndUsage_AllDataPreservedAsync()
    {
        // Arrange — Realistic scenario: text with annotations + usage data
        TextContent textContent = new("The answer is documented here.");
        textContent.Annotations =
        [
            new CitationAnnotation
            {
                Url = new System.Uri("https://docs.example.com/answer"),
                Title = "Answer Documentation"
            }
        ];

        List<ChatResponseUpdate> updates =
        [
            new ChatResponseUpdate
            {
                Role = ChatRole.Assistant,
                Contents = [textContent],
                MessageId = "msg1"
            },
            new ChatResponseUpdate
            {
                Role = ChatRole.Assistant,
                Contents = [new UsageContent(new UsageDetails
                {
                    InputTokenCount = 80,
                    OutputTokenCount = 25,
                    TotalTokenCount = 105
                })],
                MessageId = "msg1"
            }
        ];

        List<BaseEvent> events = await CollectEventsAsync(updates);
        string allEventsJson = SerializeAllEvents(events);

        // Assert — Text should be present
        Assert.Contains(events, e => e is TextMessageContentEvent tce && tce.Delta.Contains("documented"));

        // Assert — Annotations should be present
        Assert.True(
            allEventsJson.Contains("docs.example.com/answer") || allEventsJson.Contains("Answer Documentation"),
            "Annotation data should be preserved in AGUI events when text and usage are both present. " +
            "See https://github.com/microsoft/agent-framework/issues/3752");

        // Assert — Usage should be present
        List<BaseEvent> baselineEvents = await CollectEventsAsync([]);
        int textAndLifecycleCount = events.Count(e =>
            e is RunStartedEvent or RunFinishedEvent or
            TextMessageStartEvent or TextMessageContentEvent or TextMessageEndEvent);
        Assert.True(
            events.Count > textAndLifecycleCount,
            "Usage data should produce additional events when combined with annotated text. " +
            "See https://github.com/microsoft/agent-framework/issues/3752");
    }

    #endregion

    #region Helpers

    private static async Task<List<BaseEvent>> CollectEventsAsync(List<ChatResponseUpdate> updates)
    {
        List<BaseEvent> events = [];
        await foreach (BaseEvent evt in updates.ToAsyncEnumerableAsync()
            .AsAGUIEventStreamAsync(ThreadId, RunId, AGUIJsonSerializerContext.Default.Options, CancellationToken.None))
        {
            events.Add(evt);
        }
        return events;
    }

    private static string SerializeAllEvents(List<BaseEvent> events)
    {
        return string.Join("\n", events.Select(e =>
            JsonSerializer.Serialize(e, AGUIJsonSerializerContext.Default.Options)));
    }

    #endregion
}
