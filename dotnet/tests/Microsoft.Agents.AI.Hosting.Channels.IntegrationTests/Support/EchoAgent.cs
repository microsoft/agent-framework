// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.Channels.IntegrationTests.Support;

/// <summary>Agent that replies with the concatenated text of the user messages it received.</summary>
internal sealed class EchoAgent : AIAgent
{
    protected override string? IdCore => "echo-agent";

    protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default) =>
        new(new EchoSession());

    protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) =>
        new(new EchoSession());

    protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) =>
        new(JsonSerializer.SerializeToElement(new { }));

    protected override Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        var text = string.Concat(messages.Where(m => m.Role == ChatRole.User).Select(m => m.Text));
        return Task.FromResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, text)));
    }

    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var text = string.Concat(messages.Where(m => m.Role == ChatRole.User).Select(m => m.Text));
        yield return new AgentResponseUpdate { Role = ChatRole.Assistant, Contents = [new TextContent(text)] };
        await Task.Yield();
    }

    private sealed class EchoSession : AgentSession
    {
        public EchoSession()
        {
        }

        public EchoSession(AgentSessionStateBag stateBag) : base(stateBag)
        {
        }
    }
}
