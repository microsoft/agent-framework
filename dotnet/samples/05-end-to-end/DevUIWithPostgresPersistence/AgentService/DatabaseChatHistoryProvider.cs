// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace DevUIWithPostgresPersistence.AgentService;

internal sealed class DatabaseChatHistoryProvider : ChatHistoryProvider
{
    internal const string StateKey = "DevUIWithPostgresPersistence.ChatHistory";

    private readonly PostgresConversationStore _store;
    private readonly ProviderSessionState<State> _sessionState =
        new(
            _ => throw new InvalidOperationException(
                "The PostgreSQL session store must initialize the conversation history ID."),
            StateKey);

    public DatabaseChatHistoryProvider(PostgresConversationStore store)
    {
        this._store = store;
    }

    public override IReadOnlyList<string> StateKeys => [this._sessionState.StateKey];

    protected override ValueTask<IEnumerable<ChatMessage>> ProvideChatHistoryAsync(
        InvokingContext context,
        CancellationToken cancellationToken = default)
    {
        State state = this._sessionState.GetOrInitializeState(context.Session);
        return this._store.LoadChatHistoryAsync(state.HistoryId, cancellationToken);
    }

    protected override ValueTask StoreChatHistoryAsync(
        InvokedContext context,
        CancellationToken cancellationToken = default)
    {
        State state = this._sessionState.GetOrInitializeState(context.Session);
        return this._store.AppendChatHistoryAsync(
            state.HistoryId,
            context.RequestMessages.Concat(context.ResponseMessages ?? []),
            cancellationToken);
    }

    internal sealed class State
    {
        public required string HistoryId { get; init; }
    }
}
