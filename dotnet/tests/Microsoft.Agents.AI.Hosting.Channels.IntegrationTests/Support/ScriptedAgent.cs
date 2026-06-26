// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.Channels.IntegrationTests.Support;

/// <summary>
/// Agent that replays a fixed list of assistant <see cref="ChatMessage"/> objects as its response, so the
/// channel's output-item rendering (multimodal content, call/result coalescing, raw-item passthrough) can be
/// driven with arbitrary content. No live model.
/// </summary>
internal sealed class ScriptedAgent : AIAgent
{
    private readonly List<ChatMessage> _messages;

    public ScriptedAgent(params AIContent[] contents)
        : this([new ChatMessage(ChatRole.Assistant, [.. contents])])
    {
    }

    public ScriptedAgent(List<ChatMessage> messages)
    {
        this._messages = messages;
    }

    protected override string? IdCore => "scripted-agent";

    protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default) =>
        new(new ScriptedSession());

    protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) =>
        new(new ScriptedSession());

    protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) =>
        new(JsonSerializer.SerializeToElement(new { }));

    protected override Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default) =>
        Task.FromResult(new AgentResponse(this._messages));

    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        foreach (var message in this._messages)
        {
            yield return new AgentResponseUpdate { Role = ChatRole.Assistant, Contents = message.Contents };
            await Task.Yield();
        }
    }

    private sealed class ScriptedSession : AgentSession
    {
        public ScriptedSession()
        {
        }

        public ScriptedSession(AgentSessionStateBag stateBag) : base(stateBag)
        {
        }
    }
}
