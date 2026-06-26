// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.Channels.IntegrationTests.Support;

/// <summary>Deterministic agent that streams a fixed reply in chunks. No live model.</summary>
internal sealed class FakeChatAgent : AIAgent
{
    public const string Reply = "Hello from fake agent!";

    protected override string? IdCore => "fake-agent";

    public override string? Description => "A fake agent for testing";

    protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default) =>
        new(new FakeSession());

    protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) =>
        new(new FakeSession());

    protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) =>
        new(JsonSerializer.SerializeToElement(new { }));

    protected override async Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        List<AgentResponseUpdate> updates = [];
        await foreach (var update in this.RunStreamingAsync(messages, session, options, cancellationToken).ConfigureAwait(false))
        {
            updates.Add(update);
        }

        return updates.ToAgentResponse();
    }

    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var messageId = Guid.NewGuid().ToString("N");
        foreach (var chunk in new[] { "Hello", " ", "from", " ", "fake", " ", "agent", "!" })
        {
            yield return new AgentResponseUpdate { MessageId = messageId, Role = ChatRole.Assistant, Contents = [new TextContent(chunk)] };
            await Task.Yield();
        }
    }

    private sealed class FakeSession : AgentSession
    {
        public FakeSession()
        {
        }

        public FakeSession(AgentSessionStateBag stateBag) : base(stateBag)
        {
        }
    }
}
