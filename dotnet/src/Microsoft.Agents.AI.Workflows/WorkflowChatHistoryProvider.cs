// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows;

internal sealed class WorkflowChatHistoryProvider : ChatHistoryProvider
{
    private readonly ProviderSessionState<StoreState> _sessionState;

    /// <summary>
    /// Initializes a new instance of the <see cref="WorkflowChatHistoryProvider"/> class.
    /// </summary>
    /// <param name="jsonSerializerOptions">
    /// Optional JSON serializer options for serializing the state of this provider.
    /// This is valuable for cases like when the chat history contains custom <see cref="AIContent"/> types
    /// and source generated serializers are required, or Native AOT / Trimming is required.
    /// </param>
    public WorkflowChatHistoryProvider(JsonSerializerOptions? jsonSerializerOptions = null)
        : base(provideOutputMessageFilter: null, storeInputMessageFilter: null)
    {
        this._sessionState = new ProviderSessionState<StoreState>(
            _ => new StoreState(),
            this.GetType().Name,
            jsonSerializerOptions);
    }

    /// <inheritdoc />
    public override string StateKey => this._sessionState.StateKey;

    internal sealed class StoreState
    {
        public int Bookmark { get; set; }
        public List<ChatMessage> Messages { get; set; } = [];
    }

    internal void AddMessages(AgentSession session, params IEnumerable<ChatMessage> messages)
        => this._sessionState.GetOrInitializeState(session).Messages.AddRange(messages);

    protected override ValueTask<IEnumerable<ChatMessage>> ProvideChatHistoryAsync(InvokingContext context, CancellationToken cancellationToken = default)
        => new(this._sessionState.GetOrInitializeState(context.Session).Messages);

    protected override ValueTask StoreChatHistoryAsync(InvokedContext context, CancellationToken cancellationToken = default)
    {
        var allNewMessages = context.RequestMessages.Concat(context.ResponseMessages ?? []);
        this._sessionState.GetOrInitializeState(context.Session).Messages.AddRange(allNewMessages);
        return default;
    }

    public IEnumerable<ChatMessage> GetFromBookmark(AgentSession session)
    {
        var state = this._sessionState.GetOrInitializeState(session);

        for (int i = state.Bookmark; i < state.Messages.Count; i++)
        {
            yield return state.Messages[i];
        }
    }

    public void UpdateBookmark(AgentSession session)
    {
        var state = this._sessionState.GetOrInitializeState(session);
        state.Bookmark = state.Messages.Count;
    }
}
