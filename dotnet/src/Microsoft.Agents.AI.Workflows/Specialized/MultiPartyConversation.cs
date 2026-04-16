// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Specialized;

internal sealed class MultiPartyConversation
{
    private readonly List<ChatMessage> _history = [];
    private readonly object _mutex = new();

    public List<ChatMessage> CloneAllMessages()
    {
        lock (this._mutex)
        {
            return this._history.ToList();
        }
    }

    public (ChatMessage[], int) CollectNewMessages(int bookmark)
    {
        lock (this._mutex)
        {
            int count = this._history.Count - bookmark;
            if (count < 0)
            {
                throw new InvalidOperationException($"Bookmark value too large: {bookmark} vs count={count}");
            }

            return (this._history.Skip(bookmark).ToArray(), this.CurrentBookmark);
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
