// Copyright (c) Microsoft. All rights reserved.

using System.Runtime.CompilerServices;
using System.Text.Json;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Extensions.AI;

namespace Foundry.Hosting.IntegrationTests.TestContainer;

/// <summary>
/// Minimal agent that echoes the platform user isolation key as <c>USER-ID:&lt;key&gt;</c>.
/// Does not call a model, so identity ITs do not depend on OpenAI quota or catalog access.
/// </summary>
#pragma warning disable MAAI001 // HostedSessionContext / experimental surface
internal sealed class UserIdentityEchoAgent : AIAgent
{
    public override string Name => "user-identity-agent";

    public override string Description =>
        "Echoes the platform user isolation key for user-identity IT assertions.";

    protected override Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        var text = BuildReply(session);
        return Task.FromResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, text)));
    }

    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var text = BuildReply(session);
        yield return new AgentResponseUpdate
        {
            Role = ChatRole.Assistant,
            Contents = [new TextContent(text)],
        };

        await Task.CompletedTask.ConfigureAwait(false);
    }

    protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
        => new(new InMemorySession());

    protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
        AgentSession session,
        JsonSerializerOptions? jsonSerializerOptions = null,
        CancellationToken cancellationToken = default)
        => new(JsonSerializer.SerializeToElement(new { }, jsonSerializerOptions));

    protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
        JsonElement serializedState,
        JsonSerializerOptions? jsonSerializerOptions = null,
        CancellationToken cancellationToken = default)
        => new(new InMemorySession());

    private static string BuildReply(AgentSession? session)
    {
        var userId = session?.GetHostedContext()?.UserId;
        var token = string.IsNullOrWhiteSpace(userId) ? "USER-ID:missing" : $"USER-ID:{userId}";
        return $"ready\n{token}";
    }

    private sealed class InMemorySession : AgentSession;
}
#pragma warning restore MAAI001
