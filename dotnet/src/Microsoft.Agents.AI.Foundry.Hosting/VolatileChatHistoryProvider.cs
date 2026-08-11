// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// A <see cref="ChatHistoryProvider"/> that holds a conversation in a field, for the lifetime of one
/// request and no longer.
/// </summary>
/// <remarks>
/// <para>
/// A hosted agent's conversation is recorded by the AgentServer SDK's own storage provider, which
/// writes every turn the caller asked it to store and serves it back through
/// <see cref="Azure.AI.AgentServer.Responses.ResponseContext.GetHistoryAsync"/>. That happens around
/// the handler, not through it. An agent with no provider of its own is given that record here, so it
/// reads the conversation the way it reads any other history, and anything it stores back is dropped
/// with this instance rather than kept somewhere the storage provider never sees.
/// </para>
/// <para>
/// Within a single run the provider still does its ordinary work: an agent calling tools goes back to
/// the chat client several times, and each of those calls needs the messages the earlier ones produced.
/// Those live here until the run ends and the instance is dropped.
/// </para>
/// <para>
/// Supplied as a run-scoped override through <see cref="AgentRunOptions.AdditionalProperties"/>, so it
/// serves the turn without changing the agent. An agent that does not read its history through a
/// provider ignores it.
/// </para>
/// </remarks>
internal sealed class VolatileChatHistoryProvider : ChatHistoryProvider
{
    private readonly List<ChatMessage> _messages;

    /// <summary>
    /// Initializes a new instance of the <see cref="VolatileChatHistoryProvider"/> class holding the
    /// conversation so far.
    /// </summary>
    /// <param name="history">The turns of this conversation the hosting service has recorded.</param>
    public VolatileChatHistoryProvider(IEnumerable<ChatMessage>? history = null)
    {
        this._messages = history is null ? [] : [.. history];
    }

    /// <inheritdoc />
    protected override ValueTask<IEnumerable<ChatMessage>> ProvideChatHistoryAsync(InvokingContext context, CancellationToken cancellationToken = default)
        => new(this._messages);

    /// <inheritdoc />
    protected override ValueTask StoreChatHistoryAsync(InvokedContext context, CancellationToken cancellationToken = default)
    {
        this._messages.AddRange(context.RequestMessages);
        if (context.ResponseMessages is not null)
        {
            this._messages.AddRange(context.ResponseMessages);
        }

        return default;
    }
}
