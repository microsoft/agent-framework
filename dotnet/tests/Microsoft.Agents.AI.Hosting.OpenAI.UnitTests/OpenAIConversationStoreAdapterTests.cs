// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Conversations;
using Microsoft.Agents.AI.Hosting.OpenAI.Conversations.Models;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

public sealed class OpenAIConversationStoreAdapterTests
{
    [Fact]
    public async Task UseOpenAIConversationStore_ReplacesDefaultStorageAndRoundTripsOpaquePayloadsAsync()
    {
        // Arrange
        var store = new RecordingConversationStore();
        var services = new ServiceCollection();
        services.AddOpenAIResponses();
        services.AddOpenAIConversations();
        services.UseOpenAIConversationStore(store);
        await using ServiceProvider provider = services.BuildServiceProvider();
        var storage = provider.GetRequiredService<IConversationStorage>();
        var index = provider.GetRequiredService<IAgentConversationIndex>();
        var conversation = new Conversation
        {
            Id = "conv_1",
            CreatedAt = 42,
            Metadata = new Dictionary<string, string> { ["agent_id"] = "assistant" },
        };
        var item = new ResponsesUserMessageItemResource
        {
            Id = "msg_1",
            Content = [new ItemContentInputText { Text = "hello" }],
        };

        // Act
        await storage.CreateConversationAsync(conversation);
        await storage.AddItemsAsync(conversation.Id, [item]);
        await index.AddConversationAsync("assistant", conversation.Id);
        Conversation? restoredConversation = await storage.GetConversationAsync(conversation.Id);
        var restoredItem = await storage.GetItemAsync(conversation.Id, item.Id);
        var conversationIds = await index.GetConversationIdsAsync("assistant");

        // Assert
        Assert.Same(store, provider.GetRequiredService<IOpenAIConversationStore>());
        Assert.NotNull(restoredConversation);
        Assert.Equal(conversation.Id, restoredConversation.Id);
        Assert.Equal(conversation.CreatedAt, restoredConversation.CreatedAt);
        Assert.Equal(conversation.Metadata, restoredConversation.Metadata);
        var restoredMessage = Assert.IsType<ResponsesUserMessageItemResource>(restoredItem);
        Assert.Equal("hello", Assert.IsType<ItemContentInputText>(Assert.Single(restoredMessage.Content)).Text);
        Assert.Equal([conversation.Id], conversationIds.Data);
    }

    private sealed class RecordingConversationStore : IOpenAIConversationStore
    {
        private readonly Dictionary<string, OpenAIConversationRecord> _conversations = [];
        private readonly Dictionary<string, List<OpenAIConversationItem>> _items = [];
        private readonly Dictionary<string, List<string>> _agentConversations = [];

        public ValueTask CreateConversationAsync(OpenAIConversationRecord conversation, CancellationToken cancellationToken = default)
        {
            this._conversations.Add(conversation.Id, Clone(conversation));
            this._items.Add(conversation.Id, []);
            return ValueTask.CompletedTask;
        }

        public ValueTask<OpenAIConversationRecord?> GetConversationAsync(string conversationId, CancellationToken cancellationToken = default)
            => ValueTask.FromResult(this._conversations.TryGetValue(conversationId, out OpenAIConversationRecord? conversation)
                ? Clone(conversation)
                : null);

        public ValueTask<bool> UpdateConversationAsync(OpenAIConversationRecord conversation, CancellationToken cancellationToken = default)
        {
            if (!this._conversations.ContainsKey(conversation.Id))
            {
                return ValueTask.FromResult(false);
            }

            this._conversations[conversation.Id] = Clone(conversation);
            return ValueTask.FromResult(true);
        }

        public ValueTask<bool> DeleteConversationAsync(string conversationId, CancellationToken cancellationToken = default)
        {
            this._items.Remove(conversationId);
            return ValueTask.FromResult(this._conversations.Remove(conversationId));
        }

        public ValueTask AddItemsAsync(string conversationId, IReadOnlyList<OpenAIConversationItem> items, CancellationToken cancellationToken = default)
        {
            this._items[conversationId].AddRange(items.Select(Clone));
            return ValueTask.CompletedTask;
        }

        public ValueTask<OpenAIConversationItem?> GetItemAsync(string conversationId, string itemId, CancellationToken cancellationToken = default)
            => ValueTask.FromResult(this._items[conversationId].Find(item => item.Id == itemId) is { } item ? Clone(item) : null);

        public ValueTask<OpenAIConversationItemsPage> ListItemsAsync(
            string conversationId,
            int limit,
            OpenAIConversationItemOrder order,
            string? after,
            CancellationToken cancellationToken = default)
        {
            IEnumerable<OpenAIConversationItem> items = this._items[conversationId];
            if (order is OpenAIConversationItemOrder.Descending)
            {
                items = items.Reverse();
            }

            if (after is not null)
            {
                items = items.SkipWhile(item => item.Id != after).Skip(1);
            }

            List<OpenAIConversationItem> page = [.. items.Take(limit + 1).Select(Clone)];
            bool hasMore = page.Count > limit;
            if (hasMore)
            {
                page.RemoveAt(page.Count - 1);
            }

            return ValueTask.FromResult(new OpenAIConversationItemsPage { Items = page, HasMore = hasMore });
        }

        public ValueTask<bool> DeleteItemAsync(string conversationId, string itemId, CancellationToken cancellationToken = default)
            => ValueTask.FromResult(this._items[conversationId].RemoveAll(item => item.Id == itemId) > 0);

        public ValueTask AddConversationToAgentAsync(string agentId, string conversationId, CancellationToken cancellationToken = default)
        {
            if (!this._agentConversations.TryGetValue(agentId, out List<string>? conversations))
            {
                this._agentConversations.Add(agentId, conversations = []);
            }

            conversations.Add(conversationId);
            return ValueTask.CompletedTask;
        }

        public ValueTask RemoveConversationFromAgentAsync(string agentId, string conversationId, CancellationToken cancellationToken = default)
        {
            if (this._agentConversations.TryGetValue(agentId, out List<string>? conversations))
            {
                conversations.Remove(conversationId);
            }

            return ValueTask.CompletedTask;
        }

        public ValueTask<IReadOnlyList<string>> ListConversationIdsAsync(string agentId, CancellationToken cancellationToken = default)
            => ValueTask.FromResult<IReadOnlyList<string>>(
                this._agentConversations.TryGetValue(agentId, out List<string>? conversations) ? [.. conversations] : []);

        private static OpenAIConversationRecord Clone(OpenAIConversationRecord record) => new()
        {
            Id = record.Id,
            Data = record.Data.Clone(),
        };

        private static OpenAIConversationItem Clone(OpenAIConversationItem item) => new()
        {
            Id = item.Id,
            Data = item.Data.Clone(),
        };
    }
}
