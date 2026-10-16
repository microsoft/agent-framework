// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.IntegrationTests.Workflows;

internal sealed class DeterministicAgent(string name, string response) : AIAgent
{
    public override string? Name => name;

    protected override Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
        => Task.FromResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, response)));

    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        await Task.Yield();
        yield return new AgentResponseUpdate(ChatRole.Assistant, response)
        {
            AuthorName = name,
            MessageId = $"{name}-message",
            ResponseId = $"{name}-response",
        };
    }

    protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
        => new(new TestSession());

    protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
        AgentSession session,
        JsonSerializerOptions? jsonSerializerOptions = null,
        CancellationToken cancellationToken = default)
        => new(JsonSerializer.SerializeToElement(new Dictionary<string, string>()));

    protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
        JsonElement serializedState,
        JsonSerializerOptions? jsonSerializerOptions = null,
        CancellationToken cancellationToken = default)
        => new(new TestSession());

    private sealed class TestSession : AgentSession;
}
