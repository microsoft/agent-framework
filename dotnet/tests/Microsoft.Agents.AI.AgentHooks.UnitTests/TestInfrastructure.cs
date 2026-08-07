// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using AgentHooks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AgentHooks.UnitTests;

/// <summary>A scriptable chat client: queued responses, recorded requests.</summary>
internal sealed class MockChatClient : IChatClient
{
    private readonly object _lock = new();

    public Queue<Func<List<ChatMessage>, ChatResponse>> Responses { get; } = new();

    public List<List<ChatMessage>> Requests { get; } = [];

    public int CallCount
    {
        get { lock (this._lock) { return this.Requests.Count; } }
    }

    public MockChatClient EnqueueText(string text)
    {
        lock (this._lock)
        {
            this.Responses.Enqueue(_ => new ChatResponse(new ChatMessage(ChatRole.Assistant, text)));
        }

        return this;
    }

    public MockChatClient EnqueueResponse(ChatResponse response)
    {
        lock (this._lock)
        {
            this.Responses.Enqueue(_ => response);
        }

        return this;
    }

    public MockChatClient EnqueueFunctionCall(string callId, string name, Dictionary<string, object?> arguments)
    {
        lock (this._lock)
        {
            this.Responses.Enqueue(_ => new ChatResponse(
                new ChatMessage(ChatRole.Assistant, [new FunctionCallContent(callId, name, arguments)])));
        }

        return this;
    }

    private ChatResponse NextResponse(IEnumerable<ChatMessage> messages)
    {
        lock (this._lock)
        {
            List<ChatMessage> request = [.. messages];
            this.Requests.Add(request);
            return this.Responses.Dequeue()(request);
        }
    }

    public Task<ChatResponse> GetResponseAsync(
        IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default) =>
        Task.FromResult(this.NextResponse(messages));

    public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
        IEnumerable<ChatMessage> messages, ChatOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var response = this.NextResponse(messages);
        await Task.Yield();
        foreach (var update in response.ToChatResponseUpdates())
        {
            yield return update;
        }
    }

    public object? GetService(Type serviceType, object? serviceKey = null) =>
        serviceKey is null && serviceType.IsInstanceOfType(this) ? this : null;

    public void Dispose()
    {
    }
}

/// <summary>Allows everything and records every context it sees (point + deep clone).</summary>
internal sealed class AllowGuard : IInterceptor
{
    private readonly object _lock = new();

    public List<(string Point, JsonObject Context)> Seen { get; } = [];

    public List<string> Points
    {
        get { lock (this._lock) { return [.. this.Seen.Select(entry => entry.Point)]; } }
    }

    public JsonObject Context(string point)
    {
        lock (this._lock)
        {
            return this.Seen.First(entry => entry.Point == point).Context;
        }
    }

    public List<JsonObject> Contexts(string point)
    {
        lock (this._lock)
        {
            return [.. this.Seen.Where(entry => entry.Point == point).Select(entry => entry.Context)];
        }
    }

    public ValueTask<Verdict> InterceptAsync(AgentContext context, CancellationToken ct = default)
    {
        lock (this._lock)
        {
            this.Seen.Add((context.InterceptionPoint.ToWireName(), (JsonObject)context.Json.DeepClone()));
        }

        return new(Verdict.Allow);
    }
}

/// <summary>Returns a configured verdict at one interception point, allow elsewhere.</summary>
internal sealed class PointGuard(InterceptionPoint point, Verdict verdict) : IInterceptor
{
    public int Hits;

    public ValueTask<Verdict> InterceptAsync(AgentContext context, CancellationToken ct = default)
    {
        if (context.InterceptionPoint == point)
        {
            Interlocked.Increment(ref this.Hits);
            return new(verdict);
        }

        return new(Verdict.Allow);
    }
}

/// <summary>Throws at one interception point, allow elsewhere (drives host_error:interceptor_failed).</summary>
internal sealed class CrashingGuard(InterceptionPoint point) : IInterceptor
{
    public ValueTask<Verdict> InterceptAsync(AgentContext context, CancellationToken ct = default) =>
        context.InterceptionPoint == point
            ? throw new InvalidOperationException("guard crashed")
            : new(Verdict.Allow);
}

/// <summary>Denies at one point only when the projected context contains a marker string.</summary>
internal sealed class ContentDenyGuard(InterceptionPoint point, string marker) : IInterceptor
{
    public ValueTask<Verdict> InterceptAsync(AgentContext context, CancellationToken ct = default) =>
        context.InterceptionPoint == point && context.Json.ToJsonString().Contains(marker, StringComparison.Ordinal)
            ? new(Verdict.Deny("marker_blocked"))
            : new(Verdict.Allow);
}

/// <summary>An argument value whose serialization throws (drives projection-failure halts).</summary>
internal sealed class PoisonedValue
{
    public string Boom => throw new ArgumentException("poisoned getter");
}

/// <summary>A chat history provider that records exactly what becomes durable.</summary>
internal sealed class RecordingHistoryProvider : ChatHistoryProvider
{
    public List<ChatMessage> Stored { get; } = [];

    public int StoreCalls;

    protected override ValueTask<IEnumerable<ChatMessage>> ProvideChatHistoryAsync(InvokingContext context, CancellationToken cancellationToken = default) =>
        new([.. this.Stored]);

    protected override ValueTask StoreChatHistoryAsync(InvokedContext context, CancellationToken cancellationToken = default)
    {
        _ = Interlocked.Increment(ref this.StoreCalls);
        this.Stored.AddRange(context.RequestMessages);
        this.Stored.AddRange(context.ResponseMessages ?? []);
        return default;
    }
}

/// <summary>A context provider that records its run-end (durable) notifications.</summary>
internal sealed class RecordingContextProvider : AIContextProvider
{
    public List<ChatMessage> StoredResponses { get; } = [];

    public int StoreCalls;

    protected override ValueTask<AIContext> ProvideAIContextAsync(InvokingContext context, CancellationToken cancellationToken = default) =>
        new(new AIContext());

    protected override ValueTask StoreAIContextAsync(InvokedContext context, CancellationToken cancellationToken = default)
    {
        _ = Interlocked.Increment(ref this.StoreCalls);
        this.StoredResponses.AddRange(context.ResponseMessages ?? []);
        return default;
    }
}

internal static class TestHelpers
{
    public static List<ChatMessage> UserMessage(string text) => [new ChatMessage(ChatRole.User, text)];

    public static AIFunction WeatherTool(Action<string>? onInvoke = null) =>
        AIFunctionFactory.Create(
            (string location) =>
            {
                onInvoke?.Invoke(location);
                return $"weather:{location}";
            },
            "get_weather");

    public static ChatClientAgentOptions AgentOptionsWithTools(params AITool[] tools) => new()
    {
        Name = "assistant",
        ChatOptions = new ChatOptions { Tools = [.. tools] },
    };

    public static Verdict TransformTarget(JsonNode? value) =>
        new(Decision.Transform, Transform: new Transform("$target", value));

    public static async Task<List<AgentResponseUpdate>> CollectAsync(IAsyncEnumerable<AgentResponseUpdate> stream)
    {
        List<AgentResponseUpdate> updates = [];
        await foreach (var update in stream)
        {
            updates.Add(update);
        }

        return updates;
    }
}
