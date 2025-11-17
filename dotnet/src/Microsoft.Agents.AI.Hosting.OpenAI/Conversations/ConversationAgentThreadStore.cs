// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Models;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Converters;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Extensions.AI;
using static Microsoft.Agents.AI.ChatClientAgentOptions;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Conversations;

/// <summary>
/// Implements ChatMessageStore for managing messages within a conversation thread using IConversationStorage.
/// </summary>
public class ConversationAgentThreadStore : ChatMessageStore
{
    private readonly IConversationStorage _conversationStorage;

#pragma warning disable IDE0052 // Remove unread private members
    private readonly ChatMessageStoreFactoryContext _ctx;
#pragma warning restore IDE0052 // Remove unread private members

    /// <summary>
    /// constructs
    /// </summary>
    public ConversationAgentThreadStore(ChatMessageStoreFactoryContext ctx)
        : this(ctx, new InMemoryConversationStorage())
    {
    }

    /// <summary>
    /// Constructs
    /// </summary>
    internal ConversationAgentThreadStore(ChatMessageStoreFactoryContext ctx, IConversationStorage conversationStorage)
    {
        this._conversationStorage = conversationStorage;
        this._ctx = ctx;
    }

    /// <summary>
    /// add
    /// </summary>
    public override Task AddMessagesAsync(IEnumerable<ChatMessage> messages, CancellationToken cancellationToken = default)
    {
        // missing responseId, conversationId

        //var idGenerator = new IdGenerator(responseId: ..., conversationId: ...);
        var idGenerator = new IdGenerator(responseId: "1", conversationId: "2");

        var items = messages.SelectMany(x => x.ToItemResource(idGenerator, OpenAIHostingJsonUtilities.DefaultOptions));

        return this._conversationStorage.AddItemsAsync(conversationId: "2", items, cancellationToken);
    }

    /// <summary>
    /// get
    /// </summary>
    public override async Task<IEnumerable<ChatMessage>> GetMessagesAsync(CancellationToken cancellationToken = default)
    {
        // missing conversationId

        ListResponse<ItemResource> items = await this._conversationStorage.ListItemsAsync(conversationId: "2", cancellationToken: cancellationToken).ConfigureAwait(false);
        return items.Data.Select(x => x.ToChatMessage());
    }

    /// <summary>
    /// serialize
    /// </summary>
    public override JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
    {
        // no conversationId. What can be even done here?

        return JsonDocument.Parse("{}").RootElement;
    }
}
