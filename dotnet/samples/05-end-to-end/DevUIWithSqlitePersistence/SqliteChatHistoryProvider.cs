// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace DevUIWithSqlitePersistence;

internal sealed class SqliteChatHistoryProvider : ChatHistoryProvider
{
    private const string StateKey = "DevUIWithSqlitePersistence.ChatHistory";

    private readonly SqliteConversationDatabase _database;
    private readonly ProviderSessionState<State> _sessionState =
        new(_ => new State { HistoryId = Guid.NewGuid().ToString("N") }, StateKey);

    public SqliteChatHistoryProvider(SqliteConversationDatabase database)
    {
        this._database = database;
    }

    public override IReadOnlyList<string> StateKeys => [this._sessionState.StateKey];

    protected override ValueTask<IEnumerable<ChatMessage>> ProvideChatHistoryAsync(
        InvokingContext context,
        CancellationToken cancellationToken = default)
    {
        State state = this._sessionState.GetOrInitializeState(context.Session);
        return this._database.LoadChatHistoryAsync(state.HistoryId, cancellationToken);
    }

    protected override ValueTask StoreChatHistoryAsync(
        InvokedContext context,
        CancellationToken cancellationToken = default)
    {
        State state = this._sessionState.GetOrInitializeState(context.Session);
        return this._database.AppendChatHistoryAsync(
            state.HistoryId,
            context.RequestMessages.Concat(context.ResponseMessages ?? []),
            cancellationToken);
    }

    private sealed class State
    {
        public required string HistoryId { get; init; }
    }
}
