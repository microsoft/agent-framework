// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Conversations;
using Microsoft.Agents.AI.Hosting.OpenAI.Conversations.Models;
using Microsoft.Agents.AI.Hosting.OpenAI.Models;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Unit tests for InMemoryConversationStorage implementation.
/// </summary>
public sealed class InMemoryConversationStorageTests
{
    [Fact]
    public async Task CreateConversationAsync_SuccessAsync()
    {
        // Arrange
        var storage = new InMemoryConversationStorage();
        var conversation = new Conversation
        {
            Id = "conv_test123",
            CreatedAt = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            Metadata = new Dictionary<string, string> { ["key"] = "value" }
        };

        // Act
        Conversation result = await storage.CreateConversationAsync(conversation);

        // Assert
        Assert.NotNull(result);
        Assert.Equal(conversation.Id, result.Id);
        Assert.Equal(conversation.CreatedAt, result.CreatedAt);
        Assert.NotNull(result.Metadata);
        Assert.Equal("value", result.Metadata["key"]);
    }

    [Fact]
    public async Task CreateConversationAsync_DuplicateId_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        var storage = new InMemoryConversationStorage();
        var conversation = new Conversation
        {
            Id = "conv_duplicate",
            CreatedAt = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            Metadata = []
        };

        await storage.CreateConversationAsync(conversation);

        // Act & Assert
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(
            () => storage.CreateConversationAsync(conversation));
        Assert.Contains("already exists", exception.Message);
    }

    [Fact]
    public async Task GetConversationAsync_ExistingConversation_ReturnsConversationAsync()
    {
        // Arrange
        var storage = new InMemoryConversationStorage();
        var conversation = new Conversation
        {
            Id = "conv_get123",
            CreatedAt = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            Metadata = []
        };
        await storage.CreateConversationAsync(conversation);

        // Act
        Conversation? result = await storage.GetConversationAsync("conv_get123");

        // Assert
        Assert.NotNull(result);
        Assert.Equal(conversation.Id, result.Id);
    }

    [Fact]
    public async Task GetConversationAsync_NonExistentConversation_ReturnsNullAsync()
    {
        // Arrange
        var storage = new InMemoryConversationStorage();

        // Act
        Conversation? result = await storage.GetConversationAsync("conv_nonexistent");

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public async Task UpdateConversationAsync_ExistingConversation_UpdatesSuccessfullyAsync()
    {
        // Arrange
        var storage = new InMemoryConversationStorage();
        var conversation = new Conversation
        {
            Id = "conv_update123",
            CreatedAt = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            Metadata = new Dictionary<string, string> { ["original"] = "value" }
        };
        await storage.CreateConversationAsync(conversation);

        var updatedConversation = new Conversation
        {
            Id = "conv_update123",
            CreatedAt = conversation.CreatedAt,
            Metadata = new Dictionary<string, string> { ["updated"] = "newvalue" }
        };

        // Act
        Conversation? result = await storage.UpdateConversationAsync(updatedConversation);

        // Assert
        Assert.NotNull(result);
        Assert.Equal(updatedConversation.Id, result.Id);
        Assert.NotNull(result.Metadata);
        Assert.Equal("newvalue", result.Metadata["updated"]);

        // Verify the update persisted
        Conversation? retrieved = await storage.GetConversationAsync("conv_update123");
        Assert.NotNull(retrieved);
        Assert.Equal("newvalue", retrieved.Metadata["updated"]);
    }

    [Fact]
    public async Task UpdateConversationAsync_NonExistentConversation_ReturnsNullAsync()
    {
        // Arrange
        var storage = new InMemoryConversationStorage();
        var conversation = new Conversation
        {
            Id = "conv_nonexistent",
            CreatedAt = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            Metadata = []
        };

        // Act
        Conversation? result = await storage.UpdateConversationAsync(conversation);

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public async Task DeleteConversationAsync_ExistingConversation_ReturnsTrueAsync()
    {
        // Arrange
        var storage = new InMemoryConversationStorage();
        var conversation = new Conversation
        {
            Id = "conv_delete123",
            CreatedAt = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            Metadata = []
        };
        await storage.CreateConversationAsync(conversation);

        // Act
        bool result = await storage.DeleteConversationAsync("conv_delete123");

        // Assert
        Assert.True(result);

        // Verify deletion
        Conversation? retrieved = await storage.GetConversationAsync("conv_delete123");
        Assert.Null(retrieved);
    }

    [Fact]
    public async Task DeleteConversationAsync_NonExistentConversation_ReturnsFalseAsync()
    {
        // Arrange
        var storage = new InMemoryConversationStorage();

        // Act
        bool result = await storage.DeleteConversationAsync("conv_nonexistent");

        // Assert
        Assert.False(result);
    }

    [Fact]
    public async Task AddItemsAsync_SuccessAsync()
    {
        // Arrange
        var storage = new InMemoryConversationStorage();
        var conversation = new Conversation
        {
            Id = "conv_items123",
            CreatedAt = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            Metadata = []
        };
        await storage.CreateConversationAsync(conversation);

        var item = new ResponsesUserMessageItemResource
        {
            Id = "msg_test123",
            Content = [new ItemContentInputText { Text = "Hello" }]
        };

        // Act
        await storage.AddItemsAsync("conv_items123", [item]);

        // Assert
        ItemResource? result = await storage.GetItemAsync("conv_items123", item.Id);
        Assert.NotNull(result);
        Assert.Equal(item.Id, result.Id);
    }

    [Fact]
    public async Task AddItemsAsync_NonExistentConversation_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        var storage = new InMemoryConversationStorage();
        var item = new ResponsesUserMessageItemResource
        {
            Id = "msg_test123",
            Content = [new ItemContentInputText { Text = "Hello" }]
        };

        // Act & Assert
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(
            () => storage.AddItemsAsync("conv_nonexistent", [item]));
        Assert.Contains("not found", exception.Message);
    }

    [Fact]
    public async Task AddItemsAsync_DuplicateItemId_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        var storage = new InMemoryConversationStorage();
        var conversation = new Conversation
        {
            Id = "conv_dup_items",
            CreatedAt = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            Metadata = []
        };
        await storage.CreateConversationAsync(conversation);

        var item = new ResponsesUserMessageItemResource
        {
            Id = "msg_duplicate",
            Content = [new ItemContentInputText { Text = "Hello" }]
        };

        await storage.AddItemsAsync("conv_dup_items", [item]);

        // Act & Assert
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(
            () => storage.AddItemsAsync("conv_dup_items", [item]));
        Assert.Contains("already exists", exception.Message);
    }

    [Fact]
    public async Task GetItemAsync_ExistingItem_ReturnsItemAsync()
    {
        // Arrange
        var storage = new InMemoryConversationStorage();
        var conversation = new Conversation
        {
            Id = "conv_getitem",
            CreatedAt = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            Metadata = []
        };
        await storage.CreateConversationAsync(conversation);

        var item = new ResponsesUserMessageItemResource
        {
            Id = "msg_getitem123",
            Content = [new ItemContentInputText { Text = "Test message" }]
        };
        await storage.AddItemsAsync("conv_getitem", [item]);

        // Act
        ItemResource? result = await storage.GetItemAsync("conv_getitem", "msg_getitem123");

        // Assert
        Assert.NotNull(result);
        Assert.Equal(item.Id, result.Id);
        var userMessage = Assert.IsType<ResponsesUserMessageItemResource>(result);
        Assert.NotEmpty(userMessage.Content);
    }

    [Fact]
    public async Task GetItemAsync_NonExistentItem_ReturnsNullAsync()
    {
        // Arrange
        var storage = new InMemoryConversationStorage();
        var conversation = new Conversation
        {
            Id = "conv_noitem",
            CreatedAt = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            Metadata = []
        };
        await storage.CreateConversationAsync(conversation);

        // Act
        ItemResource? result = await storage.GetItemAsync("conv_noitem", "msg_nonexistent");

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public async Task GetItemAsync_NonExistentConversation_ReturnsNullAsync()
    {
        // Arrange
        var storage = new InMemoryConversationStorage();

        // Act
        ItemResource? result = await storage.GetItemAsync("conv_nonexistent", "msg_any");

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public async Task ListItemsAsync_DefaultParameters_ReturnsDescendingOrderAsync()
    {
        // Arrange
        var storage = new InMemoryConversationStorage();
        var conversation = new Conversation
        {
            Id = "conv_list",
            CreatedAt = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            Metadata = []
        };
        await storage.CreateConversationAsync(conversation);

        // Add items in order
        var item1 = new ResponsesUserMessageItemResource
        {
            Id = "msg_001",
            Content = [new ItemContentInputText { Text = "First" }]
        };
        var item2 = new ResponsesUserMessageItemResource
        {
            Id = "msg_002",
            Content = [new ItemContentInputText { Text = "Second" }]
        };
        var item3 = new ResponsesUserMessageItemResource
        {
            Id = "msg_003",
            Content = [new ItemContentInputText { Text = "Third" }]
        };

        await storage.AddItemsAsync("conv_list", [item1]);
        await storage.AddItemsAsync("conv_list", [item2]);
        await storage.AddItemsAsync("conv_list", [item3]);

        // Act
        ListResponse<ItemResource> result = await storage.ListItemsAsync("conv_list");

        // Assert
        Assert.NotNull(result);
        Assert.NotNull(result.Data);
        Assert.Equal(3, result.Data.Count);
        Assert.Equal("msg_003", result.Data[0].Id); // Descending order
        Assert.Equal("msg_002", result.Data[1].Id);
        Assert.Equal("msg_001", result.Data[2].Id);
        Assert.Equal("msg_003", result.FirstId);
        Assert.Equal("msg_001", result.LastId);
        Assert.False(result.HasMore);
    }

    [Fact]
    public async Task ListItemsAsync_AscendingOrder_ReturnsCorrectOrderAsync()
    {
        // Arrange
        var storage = new InMemoryConversationStorage();
        var conversation = new Conversation
        {
            Id = "conv_asc",
            CreatedAt = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            Metadata = []
        };
        await storage.CreateConversationAsync(conversation);

        var item1 = new ResponsesUserMessageItemResource
        {
            Id = "msg_001",
            Content = [new ItemContentInputText { Text = "First" }]
        };
        var item2 = new ResponsesUserMessageItemResource
        {
            Id = "msg_002",
            Content = [new ItemContentInputText { Text = "Second" }]
        };

        await storage.AddItemsAsync("conv_asc", [item1]);
        await storage.AddItemsAsync("conv_asc", [item2]);

        // Act
        ListResponse<ItemResource> result = await storage.ListItemsAsync("conv_asc", order: SortOrder.Ascending);

        // Assert
        Assert.Equal(2, result.Data.Count);
        Assert.Equal("msg_001", result.Data[0].Id); // Ascending order
        Assert.Equal("msg_002", result.Data[1].Id);
    }

    [Fact]
    public async Task ListItemsAsync_WithLimit_ReturnsCorrectPageSizeAsync()
    {
        // Arrange
        var storage = new InMemoryConversationStorage();
        var conversation = new Conversation
        {
            Id = "conv_limit",
            CreatedAt = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            Metadata = []
        };
        await storage.CreateConversationAsync(conversation);

        for (int i = 1; i <= 10; i++)
        {
            var item = new ResponsesUserMessageItemResource
            {
                Id = $"msg_{i:D3}",
                Content = [new ItemContentInputText { Text = $"Message {i}" }]
            };
            await storage.AddItemsAsync("conv_limit", [item]);
        }

        // Act
        ListResponse<ItemResource> result = await storage.ListItemsAsync("conv_limit", limit: 5);

        // Assert
        Assert.Equal(5, result.Data.Count);
        Assert.True(result.HasMore);
        Assert.Equal("msg_010", result.FirstId); // First in descending order
        Assert.Equal("msg_006", result.LastId);
    }

    [Fact]
    public async Task ListItemsAsync_WithAfter_ReturnsNextPageAsync()
    {
        // Arrange
        var storage = new InMemoryConversationStorage();
        var conversation = new Conversation
        {
            Id = "conv_after",
            CreatedAt = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            Metadata = []
        };
        await storage.CreateConversationAsync(conversation);

        for (int i = 1; i <= 10; i++)
        {
            var item = new ResponsesUserMessageItemResource
            {
                Id = $"msg_{i:D3}",
                Content = [new ItemContentInputText { Text = $"Message {i}" }]
            };
            await storage.AddItemsAsync("conv_after", [item]);
        }

        // Act
        ListResponse<ItemResource> result = await storage.ListItemsAsync("conv_after", limit: 5, after: "msg_006");

        // Assert
        Assert.Equal(5, result.Data.Count);
        Assert.Equal("msg_005", result.Data[0].Id); // Next items after msg_006 in descending order
        Assert.Equal("msg_001", result.Data[4].Id);
        Assert.False(result.HasMore); // No more items after this page
    }

    [Fact]
    public async Task ListItemsAsync_LimitClamping_ClampsToValidRangeAsync()
    {
        // Arrange
        var storage = new InMemoryConversationStorage();
        var conversation = new Conversation
        {
            Id = "conv_clamp",
            CreatedAt = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            Metadata = []
        };
        await storage.CreateConversationAsync(conversation);

        for (int i = 1; i <= 5; i++)
        {
            var item = new ResponsesUserMessageItemResource
            {
                Id = $"msg_{i:D3}",
                Content = [new ItemContentInputText { Text = $"Message {i}" }]
            };
            await storage.AddItemsAsync("conv_clamp", [item]);
        }

        // Act - Test upper bound
        ListResponse<ItemResource> result1 = await storage.ListItemsAsync("conv_clamp", limit: 200);
        // Act - Test lower bound
        ListResponse<ItemResource> result2 = await storage.ListItemsAsync("conv_clamp", limit: 0);

        // Assert
        Assert.Equal(5, result1.Data.Count); // Should return all items (clamped to 100 max, but we only have 5)
        Assert.NotNull(result2.Data);
        Assert.NotEmpty(result2.Data);
        Assert.Single(result2.Data); // Should return at least 1 item (clamped to 1 min)
    }

    [Fact]
    public async Task ListItemsAsync_EmptyConversation_ReturnsEmptyListAsync()
    {
        // Arrange
        var storage = new InMemoryConversationStorage();
        var conversation = new Conversation
        {
            Id = "conv_empty",
            CreatedAt = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            Metadata = []
        };
        await storage.CreateConversationAsync(conversation);

        // Act
        ListResponse<ItemResource> result = await storage.ListItemsAsync("conv_empty");

        // Assert
        Assert.NotNull(result);
        Assert.NotNull(result.Data);
        Assert.Empty(result.Data);
        Assert.Null(result.FirstId);
        Assert.Null(result.LastId);
        Assert.False(result.HasMore);
    }

    [Fact]
    public async Task ListItemsAsync_NonExistentConversation_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        var storage = new InMemoryConversationStorage();

        // Act & Assert
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(
            () => storage.ListItemsAsync("conv_nonexistent"));
        Assert.Contains("not found", exception.Message);
    }

    [Fact]
    public async Task DeleteItemAsync_ExistingItem_ReturnsTrueAsync()
    {
        // Arrange
        var storage = new InMemoryConversationStorage();
        var conversation = new Conversation
        {
            Id = "conv_delitem",
            CreatedAt = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            Metadata = []
        };
        await storage.CreateConversationAsync(conversation);

        var item = new ResponsesUserMessageItemResource
        {
            Id = "msg_delete",
            Content = [new ItemContentInputText { Text = "Delete me" }]
        };
        await storage.AddItemsAsync("conv_delitem", [item]);

        // Act
        bool result = await storage.DeleteItemAsync("conv_delitem", "msg_delete");

        // Assert
        Assert.True(result);

        // Verify deletion
        ItemResource? retrieved = await storage.GetItemAsync("conv_delitem", "msg_delete");
        Assert.Null(retrieved);
    }

    [Fact]
    public async Task DeleteItemAsync_NonExistentItem_ReturnsFalseAsync()
    {
        // Arrange
        var storage = new InMemoryConversationStorage();
        var conversation = new Conversation
        {
            Id = "conv_delnoitem",
            CreatedAt = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            Metadata = []
        };
        await storage.CreateConversationAsync(conversation);

        // Act
        bool result = await storage.DeleteItemAsync("conv_delnoitem", "msg_nonexistent");

        // Assert
        Assert.False(result);
    }

    [Fact]
    public async Task DeleteItemAsync_NonExistentConversation_ReturnsFalseAsync()
    {
        // Arrange
        var storage = new InMemoryConversationStorage();

        // Act
        bool result = await storage.DeleteItemAsync("conv_nonexistent", "msg_any");

        // Assert
        Assert.False(result);
    }

    [Fact]
    public async Task ConcurrentOperations_ThreadSafeAsync()
    {
        // Arrange
        var storage = new InMemoryConversationStorage();
        var conversation = new Conversation
        {
            Id = "conv_concurrent",
            CreatedAt = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            Metadata = []
        };
        await storage.CreateConversationAsync(conversation);

        // Act - Add items concurrently
        var tasks = new List<Task>();
        for (int i = 0; i < 100; i++)
        {
            int index = i;
            tasks.Add(Task.Run(async () =>
            {
                var item = new ResponsesUserMessageItemResource
                {
                    Id = $"msg_{index:D3}",
                    Content = [new ItemContentInputText { Text = $"Message {index}" }]
                };
                await storage.AddItemsAsync("conv_concurrent", [item]);
            }));
        }

        await Task.WhenAll(tasks);

        // Assert
        ListResponse<ItemResource> result = await storage.ListItemsAsync("conv_concurrent", limit: 100);
        Assert.NotNull(result.Data);
        Assert.NotEmpty(result.Data);
        Assert.Equal(100, result.Data.Count);
    }
}
