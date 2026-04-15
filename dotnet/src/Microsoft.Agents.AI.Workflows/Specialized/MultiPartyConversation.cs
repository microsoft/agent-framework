// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Specialized;

internal sealed class MultiPartyConversation
{
    private readonly List<ChatMessage> _history = [];
    private readonly object _mutex = new();

    public List<ChatMessage> CloneAllMessages() => this._history.ToList();

    public (ChatMessage[], int) CollectNewMessages(int bookmark)
    {
        lock (this._mutex)
        {
            int count = this._history.Count - bookmark;
            if (count > 0)
            {
                return (this._history.Skip(bookmark).ToArray(), this.CurrentBookmark);
            }

            return ([], this.CurrentBookmark);
        }
    }

    private int CurrentBookmark => this._history.Count;

    public int AddMessages(IEnumerable<ChatMessage> messages)
    {
        lock (this._mutex)
        {
            this._history.AddRange(messages);
            return this.CurrentBookmark;
        }
    }

    public int AddMessage(ChatMessage message)
    {
        lock (this._mutex)
        {
            this._history.Add(message);
            return this.CurrentBookmark;
        }
    }
}
