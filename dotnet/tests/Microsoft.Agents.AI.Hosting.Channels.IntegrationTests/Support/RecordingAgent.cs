// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.Channels.IntegrationTests.Support;

/// <summary>
/// Agent that records the <see cref="ChatOptions"/> it was invoked with (unwrapped from
/// <see cref="ChatClientAgentRunOptions"/>) and echoes the user text. Used to prove option forwarding: by
/// default the channel strips parsed options, so <see cref="LastChatOptions"/> stays <see langword="null"/>;
/// a custom run hook that keeps them makes them visible here.
/// </summary>
internal sealed class RecordingAgent : AIAgent
{
    public ChatOptions? LastChatOptions { get; private set; }

    public bool RunCalled { get; private set; }

    protected override string? IdCore => "recording-agent";

    protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default) =>
        new(new RecordingSession());

    protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) =>
        new(new RecordingSession());

    protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) =>
        new(JsonSerializer.SerializeToElement(new { }));

    protected override Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        this.Record(options);
        var text = string.Concat(messages.Where(m => m.Role == ChatRole.User).Select(m => m.Text));
        return Task.FromResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, text)));
    }

    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        this.Record(options);
        var text = string.Concat(messages.Where(m => m.Role == ChatRole.User).Select(m => m.Text));
        yield return new AgentResponseUpdate { Role = ChatRole.Assistant, Contents = [new TextContent(text)] };
        await Task.Yield();
    }

    private void Record(AgentRunOptions? options)
    {
        this.RunCalled = true;
        this.LastChatOptions = (options as ChatClientAgentRunOptions)?.ChatOptions;
    }

    private sealed class RecordingSession : AgentSession
    {
        public RecordingSession()
        {
        }

        public RecordingSession(AgentSessionStateBag stateBag) : base(stateBag)
        {
        }
    }
}
