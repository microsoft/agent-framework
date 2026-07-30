// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Specialized;

internal sealed class MultiPartyConversation
{
    private readonly object _mutex = new();

    [JsonConstructor]
    internal MultiPartyConversation(List<ChatMessage> history)
    {
        this.History = history ?? [];
    }

    /// <summary>
    /// In order to support JSON serializaiton, this property must be internally visible. However, it should not be used
    /// in concurrent contexts without proper locking, as the underlying list is not thread safe.
    /// </summary>
    [JsonInclude]
    internal List<ChatMessage> History { get; }

    public List<ChatMessage> CloneHistory()
    {
        lock (this._mutex)
        {
            return this.History.ToList();
        }
    }

    public (ChatMessage[], int) CollectNewMessages(int bookmark)
    {
        lock (this._mutex)
        {
            int count = this.History.Count - bookmark;
            if (count < 0)
            {
                throw new InvalidOperationException($"Bookmark value too large: {bookmark} vs count={count}");
            }

            return (this.History.Skip(bookmark).ToArray(), this.CurrentBookmark);
        }
    }

    [JsonIgnore]
    private int CurrentBookmark => this.History.Count;

    public int AddMessages(IEnumerable<ChatMessage> messages)
    {
        lock (this._mutex)
        {
            this.History.AddRange(messages);
            return this.CurrentBookmark;
        }
    }

    public int AddMessage(ChatMessage message)
    {
        lock (this._mutex)
        {
            this.History.Add(message);
            return this.CurrentBookmark;
        }
    }
}
