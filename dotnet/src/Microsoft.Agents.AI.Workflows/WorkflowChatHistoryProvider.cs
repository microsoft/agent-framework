// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows;

internal sealed class WorkflowChatHistoryProvider : ChatHistoryProvider<WorkflowChatHistoryProvider.StoreState>
{
    /// <summary>
    /// Initializes a new instance of the <see cref="WorkflowChatHistoryProvider"/> class.
    /// </summary>
    /// <param name="jsonSerializerOptions">
    /// Optional JSON serializer options for serializing the state of this provider.
    /// This is valuable for cases like when the chat history contains custom <see cref="AIContent"/> types
    /// and source generated serializers are required, or Native AOT / Trimming is required.
    /// </param>
    public WorkflowChatHistoryProvider(JsonSerializerOptions? jsonSerializerOptions = null)
        : base(stateInitializer: _ => new StoreState(), stateKey: null, jsonSerializerOptions: jsonSerializerOptions, provideOutputMessageFilter: null, storeInputMessageFilter: null)
    {
    }

    internal sealed class StoreState
    {
        public int Bookmark { get; set; }
        public List<ChatMessage> Messages { get; set; } = [];
    }

    internal void AddMessages(AgentSession session, params IEnumerable<ChatMessage> messages)
        => this.GetOrInitializeState(session).Messages.AddRange(messages);

    protected override ValueTask<IEnumerable<ChatMessage>> ProvideChatHistoryAsync(InvokingContext context, CancellationToken cancellationToken = default)
        => new(this.GetOrInitializeState(context.Session).Messages);

    protected override ValueTask StoreChatHistoryAsync(InvokedContext context, CancellationToken cancellationToken = default)
    {
        var allNewMessages = context.RequestMessages.Concat(context.ResponseMessages ?? []);
        this.GetOrInitializeState(context.Session).Messages.AddRange(allNewMessages);
        return default;
    }

    public IEnumerable<ChatMessage> GetFromBookmark(AgentSession session)
    {
        var state = this.GetOrInitializeState(session);

        for (int i = state.Bookmark; i < state.Messages.Count; i++)
        {
            yield return state.Messages[i];
        }
    }

    public void UpdateBookmark(AgentSession session)
    {
        var state = this.GetOrInitializeState(session);
        state.Bookmark = state.Messages.Count;
    }
}
