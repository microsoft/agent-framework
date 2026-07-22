// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions.UnitTests;

internal sealed class TestAgent(string name, string description) : AIAgent
{
    public override string? Name => name;

    public override string? Description => description;

    protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default) => new(new DummyAgentSession());

    protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
        => throw new NotImplementedException();

    protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
        JsonElement serializedState,
        JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) => new(new DummyAgentSession());

    protected override Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default) => Task.FromResult(new AgentResponse([.. messages]));

    protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default) => throw new NotSupportedException();

    private sealed class DummyAgentSession : AgentSession;
}
