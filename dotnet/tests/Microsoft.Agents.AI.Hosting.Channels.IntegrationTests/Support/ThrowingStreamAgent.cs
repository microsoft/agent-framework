// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.Channels.IntegrationTests.Support;

/// <summary>
/// Agent whose streaming run yields one update and then throws, to exercise the channel's mid-stream
/// failure path (a Responses <c>response.failed</c> SSE event).
/// </summary>
internal sealed class ThrowingStreamAgent : AIAgent
{
    public const string PartialText = "partial";
    public const string ErrorMessage = "boom mid-stream";

    protected override string? IdCore => "throwing-agent";

    protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default) =>
        new(new ThrowingSession());

    protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) =>
        new(new ThrowingSession());

    protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) =>
        new(JsonSerializer.SerializeToElement(new { }));

    protected override Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default) =>
        Task.FromResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, PartialText)));

    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        yield return new AgentResponseUpdate { Role = ChatRole.Assistant, Contents = [new TextContent(PartialText)] };
        await Task.Yield();
        throw new InvalidOperationException(ErrorMessage);
    }

    private sealed class ThrowingSession : AgentSession
    {
        public ThrowingSession()
        {
        }

        public ThrowingSession(AgentSessionStateBag stateBag) : base(stateBag)
        {
        }
    }
}
