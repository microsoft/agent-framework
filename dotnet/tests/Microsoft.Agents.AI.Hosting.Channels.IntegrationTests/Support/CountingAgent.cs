// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Globalization;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.Channels.IntegrationTests.Support;

/// <summary>
/// Agent whose reply is the running turn count held on its <see cref="CountingSession"/>. Because the host
/// runner caches one session instance per active alias, identical isolation keys reuse the same session and
/// the count increments; a fresh session resets to 1. Proves session continuity end to end.
/// </summary>
internal sealed class CountingAgent : AIAgent
{
    protected override string? IdCore => "counting-agent";

    protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default) =>
        new(new CountingSession());

    protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) =>
        new(new CountingSession());

    protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) =>
        new(JsonSerializer.SerializeToElement(new { }));

    protected override Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        var count = session is CountingSession counting ? counting.Next() : 0;
        var response = new AgentResponse(new ChatMessage(ChatRole.Assistant, count.ToString(CultureInfo.InvariantCulture)));
        return Task.FromResult(response);
    }

    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var count = session is CountingSession counting ? counting.Next() : 0;
        yield return new AgentResponseUpdate { Role = ChatRole.Assistant, Contents = [new TextContent(count.ToString(CultureInfo.InvariantCulture))] };
        await Task.Yield();
    }

    private sealed class CountingSession : AgentSession
    {
        private int _count;

        public CountingSession()
        {
        }

        public CountingSession(AgentSessionStateBag stateBag) : base(stateBag)
        {
        }

        public int Next() => ++this._count;
    }
}
