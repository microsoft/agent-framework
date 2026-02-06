// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows;

internal sealed class WorkflowChatHistoryProvider : ChatHistoryProvider
{
    private const string DefaultStateBagKey = "WorkflowChatHistoryProvider.State";

    public WorkflowChatHistoryProvider()
    {
    }

    internal sealed class StoreState
    {
        public int Bookmark { get; set; }
        public List<ChatMessage> Messages { get; set; } = [];
    }

    private StoreState GetOrInitializeState(AgentSession? session)
    {
        var state = session?.StateBag.GetValue<StoreState>(DefaultStateBagKey, AgentAbstractionsJsonUtilities.DefaultOptions);
        if (state is not null)
        {
            return state;
        }

        state = new();
        if (session is not null)
        {
            session.StateBag.SetValue(DefaultStateBagKey, state, AgentAbstractionsJsonUtilities.DefaultOptions);
        }

        return state;
    }

    internal void AddMessages(AgentSession session, params IEnumerable<ChatMessage> messages)
        => this.GetOrInitializeState(session).Messages.AddRange(messages);

    public override ValueTask<IEnumerable<ChatMessage>> InvokingAsync(InvokingContext context, CancellationToken cancellationToken = default)
        => new(this.GetOrInitializeState(context.Session).Messages.AsReadOnly());

    public override ValueTask InvokedAsync(InvokedContext context, CancellationToken cancellationToken = default)
    {
        if (context.InvokeException is not null)
        {
            return default;
        }

        var allNewMessages = context.RequestMessages.Concat(context.AIContextProviderMessages ?? []).Concat(context.ResponseMessages ?? []);
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
