// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions.UnitTests;

internal sealed class TestAgent(string name, string description) : AIAgent
{
    public override string? Name => name;

    public override string? Description => description;

    public override AgentThread GetNewThread() => new DummyAgentThread();

    public override AgentThread DeserializeThread(
        JsonElement serializedThread,
        JsonSerializerOptions? jsonSerializerOptions = null) => new DummyAgentThread();

    public override Task<AgentRunResponse> RunAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default) => Task.FromResult(new AgentRunResponse([.. messages]));

    public override IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default) => throw new NotSupportedException();

    private sealed class DummyAgentThread : AgentThread;
}
