// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Agents.AI.DurableTask.Workflows;

namespace Microsoft.Agents.AI.DurableTask.UnitTests.Workflows;

/// <summary>
/// Tests for the bounded live-status event window that keeps the orchestration custom status under the
/// Durable Functions 16 KB (UTF-16) cap. See issue #5745.
/// </summary>
public sealed class DurableWorkflowRunnerEventWindowTests
{
    // Durable Functions caps custom status at 16 KB UTF-16 == 8192 .NET chars.
    private const int CustomStatusCharLimit = 8192;

    private static string MakeEvent(int index, int approxChars)
        => $"{{\"index\":{index},\"data\":\"{new string('x', approxChars)}\"}}";

    private static int CharCost(IEnumerable<string> events)
        => events.Sum(DurableWorkflowRunner.SerializedElementCost);

    private static int SerializedStatusLength(List<string> window, int startIndex)
    {
        DurableWorkflowLiveStatus status = new() { Events = window, EventsStartIndex = startIndex };
        return JsonSerializer.Serialize(status, DurableSerialization.Options).Length;
    }

    [Fact]
    public void BuildEventWindow_WithinBudget_ReturnsFullListFromZero()
    {
        // Arrange — a handful of small events well under the budget.
        List<string> events = [.. Enumerable.Range(0, 5).Select(i => MakeEvent(i, 100))];

        // Act
        (List<string> window, int startIndex) = DurableWorkflowRunner.BuildEventWindow(events, CharCost(events), []);

        // Assert — published in full, starting at absolute index 0.
        Assert.Equal(0, startIndex);
        Assert.Equal(events, window);
        Assert.True(SerializedStatusLength(window, startIndex) <= CustomStatusCharLimit);
    }

    [Fact]
    public void BuildEventWindow_ExceedsBudget_TrimsOldestAndStaysUnderCap()
    {
        // Arrange — 40 events of ~1 KB each (~40 KB cumulative), far over the 16 KB custom status cap.
        List<string> events = [.. Enumerable.Range(0, 40).Select(i => MakeEvent(i, 1000))];

        // Act
        (List<string> window, int startIndex) = DurableWorkflowRunner.BuildEventWindow(events, CharCost(events), []);

        // Assert — a non-empty trailing window that fits under the cap.
        Assert.True(startIndex > 0, "Expected the oldest events to be trimmed.");
        Assert.NotEmpty(window);
        Assert.True(
            SerializedStatusLength(window, startIndex) <= CustomStatusCharLimit,
            "Published status must stay under the 16 KB custom status cap.");

        // The window is the contiguous tail ending at the most recent event.
        Assert.Equal(events.GetRange(startIndex, events.Count - startIndex), window);
        Assert.Equal(events[^1], window[^1]);
    }

    [Fact]
    public void BuildEventWindow_SingleOversizedEvent_ReturnsEmptyWindowAtEnd()
    {
        // Arrange — one event larger than the entire budget. It cannot be published live without
        // overflowing the cap, so it must be excluded (delivered via the output at completion instead).
        List<string> events = [MakeEvent(0, 20_000)];

        // Act
        (List<string> window, int startIndex) = DurableWorkflowRunner.BuildEventWindow(events, CharCost(events), []);

        // Assert — empty window, start index past the (excluded) event; status stays trivially under cap.
        Assert.Empty(window);
        Assert.Equal(events.Count, startIndex);
        Assert.True(SerializedStatusLength(window, startIndex) <= CustomStatusCharLimit);
    }

    [Fact]
    public void BuildEventWindow_OversizedTailEventThenSmallEvents_ExcludesOversizedEvent()
    {
        // Arrange — a giant event in the middle followed by small ones. The window should include the
        // recent small events but stop before the oversized one.
        List<string> events =
        [
            MakeEvent(0, 100),
            MakeEvent(1, 20_000), // oversized — cannot be carried live
            MakeEvent(2, 100),
            MakeEvent(3, 100),
        ];

        // Act
        (List<string> window, int startIndex) = DurableWorkflowRunner.BuildEventWindow(events, CharCost(events), []);

        // Assert — window starts after the oversized event.
        Assert.Equal(2, startIndex);
        Assert.Equal([events[2], events[3]], window);
        Assert.True(SerializedStatusLength(window, startIndex) <= CustomStatusCharLimit);
    }

    [Fact]
    public void BuildEventWindow_LargePendingEvents_ShrinkWindowToLeaveRoom()
    {
        // Arrange — events that on their own would nearly fill the budget, plus a large pending request
        // port input. The window must shrink so the combined status stays under the cap.
        List<string> events = [.. Enumerable.Range(0, 20).Select(i => MakeEvent(i, 500))];
        List<PendingRequestPortStatus> pending = [new(EventName: "approval", Input: new string('p', 3000))];

        // Act
        (List<string> window, int startIndex) = DurableWorkflowRunner.BuildEventWindow(events, CharCost(events), pending);

        // Assert — combined status (events window + pending events) stays under the cap.
        DurableWorkflowLiveStatus status = new() { Events = window, EventsStartIndex = startIndex, PendingEvents = pending };
        int length = JsonSerializer.Serialize(status, DurableSerialization.Options).Length;
        Assert.True(length <= CustomStatusCharLimit, $"Combined status length {length} exceeded cap.");
        Assert.True(startIndex > 0, "Expected the window to shrink to make room for pending events.");
    }

    [Fact]
    public void TrimLiveStatusToBudget_WithinBudget_LeavesStatusUnchanged()
    {
        // Arrange — an already-published small window with no pending events.
        List<string> events = [.. Enumerable.Range(0, 5).Select(i => MakeEvent(i, 100))];
        DurableWorkflowLiveStatus status = new() { Events = events, EventsStartIndex = 0 };

        // Act
        DurableWorkflowRunner.TrimLiveStatusToBudget(status);

        // Assert — nothing trimmed.
        Assert.Equal(0, status.EventsStartIndex);
        Assert.Equal(events, status.Events);
        Assert.True(SerializedStatusLength(status.Events, status.EventsStartIndex) <= CustomStatusCharLimit);
    }

    [Fact]
    public void TrimLiveStatusToBudget_LargePendingAddedToPublishedWindow_ShrinksAndStaysUnderCap()
    {
        // Arrange — a previously-published trailing window that fit the budget on its own and is already
        // offset (absolute indices start at 6), mirroring PublishEventsToLiveStatus output. A request port
        // then adds a large pending input after that publish — the direct-write path from issue #5745.
        const int InitialStart = 6;
        List<string> events = [.. Enumerable.Range(0, 20).Select(i => MakeEvent(InitialStart + i, 300))];
        DurableWorkflowLiveStatus status = new()
        {
            Events = events,
            EventsStartIndex = InitialStart,
            PendingEvents = [new(EventName: "approval", Input: new string('p', 4000))],
        };

        // Act
        DurableWorkflowRunner.TrimLiveStatusToBudget(status);

        // Assert — the combined status (events window + pending) stays under the cap, the window shrank to
        // make room, and the absolute start index advanced past where it began.
        int length = JsonSerializer.Serialize(status, DurableSerialization.Options).Length;
        Assert.True(length <= CustomStatusCharLimit, $"Combined status length {length} exceeded cap.");
        Assert.True(status.EventsStartIndex > InitialStart, "Expected the window to shrink and advance the start index.");
        Assert.NotEmpty(status.Events);

        // The retained events are still the contiguous tail ending at the most recent event.
        Assert.Equal(events[^1], status.Events[^1]);
    }
}
