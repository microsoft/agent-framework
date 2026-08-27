// Copyright (c) Microsoft. All rights reserved.

using System.Runtime.CompilerServices;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace Foundry.Hosting.IntegrationTests.TestContainer;

/// <summary>
/// Wraps the container's agent and tells the caller which conversation the agent's own run left behind
/// on the service, by appending <c>DOWNSTREAM_ID=&lt;id&gt;</c> to the reply.
/// </summary>
/// <remarks>
/// <para>
/// The platform already records every hosted turn around the handler, and that is the conversation the
/// caller reads. The agent's run inside the container talks to its own service, and if that service is
/// asked to keep the turn it writes a second record, on a trail of its own that the caller never sees.
/// </para>
/// <para>
/// After the run, the id of that trail is on the session, so reporting it is enough for a test to go
/// look for it on the service. No id means the container asked for nothing to be kept.
/// </para>
/// </remarks>
internal sealed class DownstreamConversationReportingAgent(AIAgent innerAgent) : DelegatingAIAgent(innerAgent)
{
    /// <summary>
    /// Marker that carries the id. Tests read the value that follows it.
    /// </summary>
    public const string IdPrefix = "DOWNSTREAM_ID=";

    /// <summary>
    /// Value reported when the agent's run left nothing behind on the service.
    /// </summary>
    public const string NoId = "none";

    /// <inheritdoc />
    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        await foreach (var update in this.InnerAgent
            .RunStreamingAsync(messages, session, options, cancellationToken)
            .ConfigureAwait(false))
        {
            yield return update;
        }

        var downstreamId = (session as ChatClientAgentSession)?.ConversationId;
        yield return new AgentResponseUpdate(
            ChatRole.Assistant,
            $" {IdPrefix}{(string.IsNullOrWhiteSpace(downstreamId) ? NoId : downstreamId)}");
    }
}
