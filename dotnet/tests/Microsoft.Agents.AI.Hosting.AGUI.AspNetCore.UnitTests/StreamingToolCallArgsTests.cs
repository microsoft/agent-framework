// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
using Microsoft.Extensions.AI;
using OpenAI.Chat;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.UnitTests;

/// <summary>
/// Tests for progressive tool-call argument streaming: OpenAI streamed argument
/// fragments observable on <see cref="ChatResponseUpdate.RawRepresentation"/> are
/// surfaced as incremental <see cref="ToolCallArgsEvent"/>s, and the coalesced
/// <see cref="FunctionCallContent"/> that follows emits only the closing event.
/// </summary>
public sealed class StreamingToolCallArgsTests
{
    private const string ThreadId = "thread1";
    private const string RunId = "run1";
    private const string CallId = "call_123";

    private static readonly string[] s_sequentialCallIds = ["call_a", "call_b"];

    private static ChatResponseUpdate FragmentUpdate(int index, string? callId, string? functionName, string argumentsDelta)
    {
        StreamingChatToolCallUpdate toolCallUpdate = OpenAIChatModelFactory.StreamingChatToolCallUpdate(
            index: index,
            toolCallId: callId,
            functionName: functionName,
            functionArgumentsUpdate: BinaryData.FromString(argumentsDelta));
        StreamingChatCompletionUpdate rawUpdate = OpenAIChatModelFactory.StreamingChatCompletionUpdate(
            toolCallUpdates: [toolCallUpdate]);
        return new ChatResponseUpdate(ChatRole.Assistant, Array.Empty<AIContent>())
        {
            RawRepresentation = rawUpdate,
        };
    }

    private static ChatResponseUpdate CoalescedFunctionCallUpdate(string callId, string functionName)
        => new(ChatRole.Assistant, [new FunctionCallContent(callId, functionName, new Dictionary<string, object?> { ["city"] = "Paris" })]);

    private static async Task<List<BaseEvent>> CollectAsync(IEnumerable<ChatResponseUpdate> updates)
    {
        List<BaseEvent> events = [];
        await foreach (BaseEvent evt in updates.ToAsyncEnumerableAsync().AsAGUIEventStreamAsync(
            ThreadId, RunId, AGUIJsonSerializerContext.Default.Options, CancellationToken.None))
        {
            events.Add(evt);
        }

        return events;
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_RawToolCallFragments_EmitIncrementalArgsAsync()
    {
        // Arrange: three fragments (first carries id+name) then the coalesced content.
        List<ChatResponseUpdate> updates =
        [
            FragmentUpdate(0, CallId, "get_weather", "{\"ci"),
            FragmentUpdate(0, callId: null, functionName: null, "ty\":\"Pa"),
            FragmentUpdate(0, callId: null, functionName: null, "ris\"}"),
            CoalescedFunctionCallUpdate(CallId, "get_weather"),
        ];

        // Act
        List<BaseEvent> events = await CollectAsync(updates);

        // Assert
        ToolCallStartEvent start = Assert.Single(events.OfType<ToolCallStartEvent>());
        Assert.Equal(CallId, start.ToolCallId);
        Assert.Equal("get_weather", start.ToolCallName);

        List<ToolCallArgsEvent> args = events.OfType<ToolCallArgsEvent>().ToList();
        Assert.Equal(3, args.Count);
        Assert.All(args, a => Assert.Equal(CallId, a.ToolCallId));
        Assert.Equal("{\"city\":\"Paris\"}", string.Concat(args.Select(a => a.Delta)));

        ToolCallEndEvent end = Assert.Single(events.OfType<ToolCallEndEvent>());
        Assert.Equal(CallId, end.ToolCallId);
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_CoalescedContentAfterFragments_DoesNotDuplicateArgsAsync()
    {
        // Arrange
        List<ChatResponseUpdate> updates =
        [
            FragmentUpdate(0, CallId, "get_weather", "{\"city\":\"Paris\"}"),
            CoalescedFunctionCallUpdate(CallId, "get_weather"),
        ];

        // Act
        List<BaseEvent> events = await CollectAsync(updates);

        // Assert: one Start, one Args (the fragment), one End — the coalesced
        // FunctionCallContent must not re-emit the full arguments.
        Assert.Single(events.OfType<ToolCallStartEvent>());
        ToolCallArgsEvent argsEvent = Assert.Single(events.OfType<ToolCallArgsEvent>());
        Assert.Equal("{\"city\":\"Paris\"}", argsEvent.Delta);
        Assert.Single(events.OfType<ToolCallEndEvent>());
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_NoRawFragments_KeepsAtomicEmission()
    {
        // Arrange: providers without raw OpenAI fragments keep the existing behavior.
        List<ChatResponseUpdate> updates = [CoalescedFunctionCallUpdate(CallId, "get_weather")];

        // Act
        List<BaseEvent> events = await CollectAsync(updates);

        // Assert
        Assert.Single(events.OfType<ToolCallStartEvent>());
        ToolCallArgsEvent argsEvent = Assert.Single(events.OfType<ToolCallArgsEvent>());
        Assert.Contains("Paris", argsEvent.Delta);
        Assert.Single(events.OfType<ToolCallEndEvent>());
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_ParallelToolCalls_StreamIndependentlyAsync()
    {
        // Arrange: two interleaved calls on distinct indexes.
        List<ChatResponseUpdate> updates =
        [
            FragmentUpdate(0, "call_a", "get_weather", "{\"city\":"),
            FragmentUpdate(1, "call_b", "get_time", "{\"zone\":"),
            FragmentUpdate(0, callId: null, functionName: null, "\"Paris\"}"),
            FragmentUpdate(1, callId: null, functionName: null, "\"CET\"}"),
        ];

        // Act
        List<BaseEvent> events = await CollectAsync(updates);

        // Assert: each call gets its own Start (no shared parent message collapsing
        // the two calls into one bubble).
        List<ToolCallStartEvent> starts = events.OfType<ToolCallStartEvent>().ToList();
        Assert.Equal(2, starts.Count);
        Assert.Equal(s_sequentialCallIds, starts.Select(e => e.ToolCallId).ToArray());
        Assert.Equal(
            "{\"city\":\"Paris\"}",
            string.Concat(events.OfType<ToolCallArgsEvent>().Where(a => a.ToolCallId == "call_a").Select(a => a.Delta)));
        Assert.Equal(
            "{\"zone\":\"CET\"}",
            string.Concat(events.OfType<ToolCallArgsEvent>().Where(a => a.ToolCallId == "call_b").Select(a => a.Delta)));
        // Both calls were started on the wire, so both must close — here via the
        // end-of-stream sweep, since no coalesced content ever arrives. The sweep
        // promises deterministic tool-call index order, so assert the wire order.
        Assert.Equal(
            s_sequentialCallIds,
            events.OfType<ToolCallEndEvent>().Select(e => e.ToolCallId).ToArray());
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_IndexReusedAcrossRounds_StartsANewCallAsync()
    {
        // Arrange: two sequential tool-call rounds in one stream; OpenAI restarts the
        // fragment index at 0 for the second round.
        List<ChatResponseUpdate> updates =
        [
            FragmentUpdate(0, "call_a", "get_weather", "{\"city\":\"Paris\"}"),
            CoalescedFunctionCallUpdate("call_a", "get_weather"),
            FragmentUpdate(0, "call_b", "get_time", "{\"zone\":\"CET\"}"),
            CoalescedFunctionCallUpdate("call_b", "get_time"),
        ];

        // Act
        List<BaseEvent> events = await CollectAsync(updates);

        // Assert: each round gets its own Start, its args land on its own call id, and
        // each call closes exactly once (no duplicate atomic re-emission).
        Assert.Equal(
            s_sequentialCallIds,
            events.OfType<ToolCallStartEvent>().Select(e => e.ToolCallId).ToArray());
        Assert.Equal(
            "{\"city\":\"Paris\"}",
            string.Concat(events.OfType<ToolCallArgsEvent>().Where(a => a.ToolCallId == "call_a").Select(a => a.Delta)));
        Assert.Equal(
            "{\"zone\":\"CET\"}",
            string.Concat(events.OfType<ToolCallArgsEvent>().Where(a => a.ToolCallId == "call_b").Select(a => a.Delta)));
        Assert.Equal(
            s_sequentialCallIds,
            events.OfType<ToolCallEndEvent>().Select(e => e.ToolCallId).ToArray());
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_FragmentsWithoutCoalescedContent_CloseAtEndOfStreamAsync()
    {
        // Arrange: a raw-streamed call whose coalesced FunctionCallContent never arrives.
        List<ChatResponseUpdate> updates = [FragmentUpdate(0, CallId, "get_weather", "{\"city\":\"Paris\"}")];

        // Act
        List<BaseEvent> events = await CollectAsync(updates);

        // Assert: the end-of-stream sweep closes the call before RunFinished.
        ToolCallEndEvent end = Assert.Single(events.OfType<ToolCallEndEvent>());
        Assert.Equal(CallId, end.ToolCallId);
        Assert.True(
            events.FindIndex(e => e is ToolCallEndEvent) < events.FindIndex(e => e is RunFinishedEvent),
            "ToolCallEnd must precede RunFinished");
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_WrappedRawRepresentation_IsUnwrappedAsync()
    {
        // Arrange: agent pipelines wrap the provider update one level deep.
        ChatResponseUpdate fragment = FragmentUpdate(0, CallId, "get_weather", "{}");
        var wrapped = new ChatResponseUpdate(ChatRole.Assistant, Array.Empty<AIContent>())
        {
            RawRepresentation = fragment,
        };

        // Act
        List<BaseEvent> events = await CollectAsync([wrapped]);

        // Assert
        Assert.Single(events.OfType<ToolCallStartEvent>());
    }
}
