// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.Channels.IntegrationTests.Support;

/// <summary>
/// Agent that records the ambient <see cref="Activity.Current"/> trace id observed while it streams, so tests
/// can assert the deferred SSE stream runs under the request's parent span. No live model.
/// </summary>
internal sealed class SpanCapturingAgent : AIAgent
{
    public ActivityTraceId ObservedTraceId { get; private set; }

    protected override string? IdCore => "span-capturing-agent";

    protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default) =>
        new(new SpanSession());

    protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) =>
        new(new SpanSession());

    protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) =>
        new(JsonSerializer.SerializeToElement(new { }));

    protected override Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        this.ObservedTraceId = Activity.Current?.TraceId ?? default;
        return Task.FromResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "ok")));
    }

    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        this.ObservedTraceId = Activity.Current?.TraceId ?? default;
        yield return new AgentResponseUpdate { Role = ChatRole.Assistant, Contents = [new TextContent("ok")] };
        await Task.Yield();
    }

    private sealed class SpanSession : AgentSession
    {
        public SpanSession()
        {
        }

        public SpanSession(AgentSessionStateBag stateBag) : base(stateBag)
        {
        }
    }
}
