// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// A <see cref="ChatHistoryProvider"/> that holds the turn's messages in a field, for the lifetime of
/// one request and no longer.
/// </summary>
/// <remarks>
/// <para>
/// A hosted agent's conversation is recorded by the AgentServer SDK's own storage provider, which
/// writes every turn the caller asked it to store and serves it back through
/// <see cref="Azure.AI.AgentServer.Responses.ResponseContext.GetHistoryAsync"/>. That happens around
/// the handler, not through it. The handler reads the conversation from there and passes it in as the
/// run's input, so nothing has to be carried between requests, and a provider storing anything of its
/// own would only add a copy the storage provider never sees.
/// </para>
/// <para>
/// Within a single run the provider still does its ordinary work: an agent calling tools goes back to
/// the chat client several times, and each of those calls needs the messages the earlier ones produced.
/// Those live here until the run ends and the instance is dropped.
/// </para>
/// <para>
/// Supplied as a run-scoped override through <see cref="ChatOptions.AdditionalProperties"/>, so it takes
/// the place of the agent's own provider for the turn without changing the agent. An agent that does not
/// read its history through a provider ignores it.
/// </para>
/// </remarks>
internal sealed class VolatileChatHistoryProvider : ChatHistoryProvider
{
    private readonly List<ChatMessage> _messages = [];

    /// <inheritdoc />
    protected override ValueTask<IEnumerable<ChatMessage>> ProvideChatHistoryAsync(InvokingContext context, CancellationToken cancellationToken = default)
        => new(this._messages);

    /// <inheritdoc />
    protected override ValueTask StoreChatHistoryAsync(InvokedContext context, CancellationToken cancellationToken = default)
    {
        // Only what this run produced arrives here: the base class filters out everything already marked
        // as chat history, which covers the turns the handler took from the storage provider.
        this._messages.AddRange(context.RequestMessages);
        if (context.ResponseMessages is not null)
        {
            this._messages.AddRange(context.ResponseMessages);
        }

        return default;
    }
}
