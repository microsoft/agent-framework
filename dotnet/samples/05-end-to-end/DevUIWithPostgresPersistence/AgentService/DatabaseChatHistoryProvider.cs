// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace DevUIWithPostgresPersistence.AgentService;

internal sealed class DatabaseChatHistoryProvider : ChatHistoryProvider
{
    internal const string StateKey = "DevUIWithPostgresPersistence.ChatHistory";

    private readonly PostgresAgentSessionStore _store;
    private readonly ProviderSessionState<State> _sessionState =
        new(
            _ => throw new InvalidOperationException(
                "The PostgreSQL session store must initialize the conversation history ID."),
            StateKey);

    public DatabaseChatHistoryProvider(PostgresAgentSessionStore store)
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

    protected override async ValueTask StoreChatHistoryAsync(
        InvokedContext context,
        CancellationToken cancellationToken = default)
    {
        State state = this._sessionState.GetOrInitializeState(context.Session);
        string nextHistoryId = Guid.NewGuid().ToString("N");
        await this._store.ForkAndAppendChatHistoryAsync(
            state.HistoryId,
            nextHistoryId,
            context.RequestMessages.Concat(context.ResponseMessages ?? []),
            cancellationToken).ConfigureAwait(false);
        state.HistoryId = nextHistoryId;
        this._sessionState.SaveState(context.Session, state);
    }

    internal sealed class State
    {
        public required string HistoryId { get; set; }
    }
}
