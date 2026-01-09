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

    protected override Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default) => Task.FromResult(new AgentResponse([.. messages]));

    protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default) => throw new NotSupportedException();

    private sealed class DummyAgentThread : AgentThread;
}
