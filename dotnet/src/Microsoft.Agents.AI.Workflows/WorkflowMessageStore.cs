// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

internal sealed class WorkflowMessageStore : ChatMessageStore
{
    private int _bookmark;
    private readonly List<ChatMessage> _chatMessages = [];

    public WorkflowMessageStore()
    {
    }

    public WorkflowMessageStore(StoreState state)
    {
        this.ImportStoreState(Throw.IfNull(state));
    }

    private void ImportStoreState(StoreState state, bool clearMessages = false)
    {
        if (clearMessages)
        {
            this._chatMessages.Clear();
        }

        if (state?.Messages is not null)
        {
            this._chatMessages.AddRange(state.Messages);
        }
        this._bookmark = state?.Bookmark ?? 0;
    }

    internal sealed class StoreState
    {
        public int Bookmark { get; set; }
        public IList<ChatMessage> Messages { get; set; } = [];
    }

    internal void AddMessages(params IEnumerable<ChatMessage> messages) => this._chatMessages.AddRange(messages);

    public override ValueTask<IEnumerable<ChatMessage>> InvokingAsync(InvokingContext context, CancellationToken cancellationToken = default)
        => new(this._chatMessages.AsReadOnly());

    public override ValueTask InvokedAsync(InvokedContext context, CancellationToken cancellationToken = default)
    {
        if (context.InvokeException is not null)
        {
            return default;
        }

        var allNewMessages = context.RequestMessages.Concat(context.AIContextProviderMessages ?? []).Concat(context.ResponseMessages ?? []);
        this._chatMessages.AddRange(allNewMessages);

        return default;
    }

    public IEnumerable<ChatMessage> GetFromBookmark()
    {
        for (int i = this._bookmark; i < this._chatMessages.Count; i++)
        {
            yield return this._chatMessages[i];
        }
    }

    public void UpdateBookmark() => this._bookmark = this._chatMessages.Count;

    public override JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
    {
        StoreState state = this.ExportStoreState();

        return JsonSerializer.SerializeToElement(state,
            WorkflowsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(StoreState)));
    }

    internal StoreState ExportStoreState() => new() { Bookmark = this._bookmark, Messages = this._chatMessages };
}
