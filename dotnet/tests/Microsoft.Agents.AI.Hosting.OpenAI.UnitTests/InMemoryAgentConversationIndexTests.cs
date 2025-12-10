// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Conversations;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Unit tests for InMemoryAgentConversationIndex implementation.
/// </summary>
public sealed class InMemoryAgentConversationIndexTests
{
    [Fact]
    public async Task AddConversationAsync_SuccessAsync()
    {
        // Arrange
        var index = new InMemoryAgentConversationIndex();
        const string AgentId = "agent_test123";
        const string ConversationId = "conv_test123";

        // Act
        await index.AddConversationAsync(AgentId, ConversationId);

        // Assert
        var response = await index.GetConversationIdsAsync(AgentId);
        Assert.Single(response.Data);
        Assert.Contains(ConversationId, response.Data);
    }

    [Fact]
    public async Task AddConversationAsync_MultipleConversations_AddsAllAsync()
    {
        // Arrange
        var index = new InMemoryAgentConversationIndex();
        const string AgentId = "agent_multi";
        const string ConversationId1 = "conv_001";
        const string ConversationId2 = "conv_002";
        const string ConversationId3 = "conv_003";

        // Act
        await index.AddConversationAsync(AgentId, ConversationId1);
        await index.AddConversationAsync(AgentId, ConversationId2);
        await index.AddConversationAsync(AgentId, ConversationId3);

        // Assert
        var response = await index.GetConversationIdsAsync(AgentId);
        Assert.Equal(3, response.Data.Count);
        Assert.Contains(ConversationId1, response.Data);
        Assert.Contains(ConversationId2, response.Data);
        Assert.Contains(ConversationId3, response.Data);
    }

    [Fact]
    public async Task AddConversationAsync_NullAgentId_ThrowsArgumentExceptionAsync()
    {
        // Arrange
        var index = new InMemoryAgentConversationIndex();

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(
            () => index.AddConversationAsync(null!, "conv_test"));
    }

    [Fact]
    public async Task AddConversationAsync_EmptyAgentId_ThrowsArgumentExceptionAsync()
    {
        // Arrange
        var index = new InMemoryAgentConversationIndex();

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(
            () => index.AddConversationAsync(string.Empty, "conv_test"));
    }

    [Fact]
    public async Task AddConversationAsync_NullConversationId_ThrowsArgumentExceptionAsync()
    {
        // Arrange
        var index = new InMemoryAgentConversationIndex();

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(
            () => index.AddConversationAsync("agent_test", null!));
    }

    [Fact]
    public async Task AddConversationAsync_EmptyConversationId_ThrowsArgumentExceptionAsync()
    {
        // Arrange
        var index = new InMemoryAgentConversationIndex();

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(
            () => index.AddConversationAsync("agent_test", string.Empty));
    }

    [Fact]
    public async Task AddConversationAsync_MultipleAgents_IsolatesConversationsAsync()
    {
        // Arrange
        var index = new InMemoryAgentConversationIndex();
        const string Agent1 = "agent_001";
        const string Agent2 = "agent_002";
        const string Conv1 = "conv_001";
        const string Conv2 = "conv_002";

        // Act
        await index.AddConversationAsync(Agent1, Conv1);
        await index.AddConversationAsync(Agent2, Conv2);

        // Assert
        var agent1Response = await index.GetConversationIdsAsync(Agent1);
        var agent2Response = await index.GetConversationIdsAsync(Agent2);

        Assert.Single(agent1Response.Data);
        Assert.Contains(Conv1, agent1Response.Data);
        Assert.DoesNotContain(Conv2, agent1Response.Data);

        Assert.Single(agent2Response.Data);
        Assert.Contains(Conv2, agent2Response.Data);
        Assert.DoesNotContain(Conv1, agent2Response.Data);
    }

    [Fact]
    public async Task RemoveConversationAsync_ExistingConversation_RemovesSuccessfullyAsync()
    {
        // Arrange
        var index = new InMemoryAgentConversationIndex();
        const string AgentId = "agent_remove";
        const string ConversationId = "conv_remove123";

        await index.AddConversationAsync(AgentId, ConversationId);

        // Act
        await index.RemoveConversationAsync(AgentId, ConversationId);

        // Assert
        var response = await index.GetConversationIdsAsync(AgentId);
        Assert.Empty(response.Data);
    }

    [Fact]
    public async Task RemoveConversationAsync_NonExistentConversation_NoErrorAsync()
    {
        // Arrange
        var index = new InMemoryAgentConversationIndex();
        const string AgentId = "agent_noremove";

        // Act - Should not throw
        await index.RemoveConversationAsync(AgentId, "conv_nonexistent");

        // Assert
        var response = await index.GetConversationIdsAsync(AgentId);
        Assert.Empty(response.Data);
    }

    [Fact]
    public async Task RemoveConversationAsync_OneOfMany_RemovesOnlyTargetedAsync()
    {
        // Arrange
        var index = new InMemoryAgentConversationIndex();
        const string AgentId = "agent_partial";
        const string Conv1 = "conv_001";
        const string Conv2 = "conv_002";
        const string Conv3 = "conv_003";

        await index.AddConversationAsync(AgentId, Conv1);
        await index.AddConversationAsync(AgentId, Conv2);
        await index.AddConversationAsync(AgentId, Conv3);

        // Act
        await index.RemoveConversationAsync(AgentId, Conv2);

        // Assert
        var response = await index.GetConversationIdsAsync(AgentId);
        Assert.Equal(2, response.Data.Count);
        Assert.Contains(Conv1, response.Data);
        Assert.DoesNotContain(Conv2, response.Data);
        Assert.Contains(Conv3, response.Data);
    }

    [Fact]
    public async Task RemoveConversationAsync_NullAgentId_ThrowsArgumentExceptionAsync()
    {
        // Arrange
        var index = new InMemoryAgentConversationIndex();

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(
            () => index.RemoveConversationAsync(null!, "conv_test"));
    }

    [Fact]
    public async Task RemoveConversationAsync_EmptyAgentId_ThrowsArgumentExceptionAsync()
    {
        // Arrange
        var index = new InMemoryAgentConversationIndex();

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(
            () => index.RemoveConversationAsync(string.Empty, "conv_test"));
    }

    [Fact]
    public async Task RemoveConversationAsync_NullConversationId_ThrowsArgumentExceptionAsync()
    {
        // Arrange
        var index = new InMemoryAgentConversationIndex();

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(
            () => index.RemoveConversationAsync("agent_test", null!));
    }

    [Fact]
    public async Task RemoveConversationAsync_EmptyConversationId_ThrowsArgumentExceptionAsync()
    {
        // Arrange
        var index = new InMemoryAgentConversationIndex();

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(
            () => index.RemoveConversationAsync("agent_test", string.Empty));
    }

    [Fact]
    public async Task GetConversationIdsAsync_EmptyIndex_ReturnsEmptyListAsync()
    {
        // Arrange
        var index = new InMemoryAgentConversationIndex();

        // Act
        var response = await index.GetConversationIdsAsync("agent_empty");

        // Assert
        Assert.NotNull(response);
        Assert.Empty(response.Data);
    }

    [Fact]
    public async Task GetConversationIdsAsync_NonExistentAgent_ReturnsEmptyListAsync()
    {
        // Arrange
        var index = new InMemoryAgentConversationIndex();
        await index.AddConversationAsync("agent_other", "conv_001");

        // Act
        var response = await index.GetConversationIdsAsync("agent_nonexistent");

        // Assert
        Assert.NotNull(response);
        Assert.Empty(response.Data);
    }

    [Fact]
    public async Task GetConversationIdsAsync_NullAgentId_ThrowsArgumentExceptionAsync()
    {
        // Arrange
        var index = new InMemoryAgentConversationIndex();

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(
            async () => await index.GetConversationIdsAsync(null!));
    }

    [Fact]
    public async Task GetConversationIdsAsync_EmptyAgentId_ThrowsArgumentExceptionAsync()
    {
        // Arrange
        var index = new InMemoryAgentConversationIndex();

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(
            () => index.GetConversationIdsAsync(string.Empty));
    }

    [Fact]
    public async Task GetConversationIdsAsync_AfterMultipleAddsAndRemoves_ReturnsCorrectListAsync()
    {
        // Arrange
        var index = new InMemoryAgentConversationIndex();
        const string AgentId = "agent_complex";

        await index.AddConversationAsync(AgentId, "conv_001");
        await index.AddConversationAsync(AgentId, "conv_002");
        await index.AddConversationAsync(AgentId, "conv_003");
        await index.RemoveConversationAsync(AgentId, "conv_002");
        await index.AddConversationAsync(AgentId, "conv_004");
        await index.RemoveConversationAsync(AgentId, "conv_001");

        // Act
        var response = await index.GetConversationIdsAsync(AgentId);

        // Assert
        Assert.Equal(2, response.Data.Count);
        Assert.Contains("conv_003", response.Data);
        Assert.Contains("conv_004", response.Data);
        Assert.DoesNotContain("conv_001", response.Data);
        Assert.DoesNotContain("conv_002", response.Data);
    }

    [Fact]
    public async Task ConcurrentOperations_ThreadSafeAsync()
    {
        // Arrange
        var index = new InMemoryAgentConversationIndex();
        const string AgentId = "agent_concurrent";
        const int OperationCount = 100;

        // Act - Add conversations concurrently
        var addTasks = new List<Task>();
        for (int i = 0; i < OperationCount; i++)
        {
            int index_local = i;
            addTasks.Add(Task.Run(async () => await index.AddConversationAsync(AgentId, $"conv_{index_local:D3}")));
        }

        await Task.WhenAll(addTasks);

        // Assert
        var response = await index.GetConversationIdsAsync(AgentId);
        Assert.Equal(OperationCount, response.Data.Count);

        // Act - Remove half of them concurrently
        var removeTasks = new List<Task>();
        for (int i = 0; i < OperationCount / 2; i++)
        {
            int index_local = i;
            removeTasks.Add(Task.Run(async () => await index.RemoveConversationAsync(AgentId, $"conv_{index_local:D3}")));
        }

        await Task.WhenAll(removeTasks);

        // Assert
        response = await index.GetConversationIdsAsync(AgentId);
        Assert.Equal(OperationCount / 2, response.Data.Count);
    }

    [Fact]
    public async Task AddConversationAsync_DuplicateConversation_DoesNotAddMultipleTimesAsync()
    {
        // Arrange
        var index = new InMemoryAgentConversationIndex();
        const string AgentId = "agent_dup";
        const string ConversationId = "conv_duplicate";

        // Act - Add the same conversation multiple times
        await index.AddConversationAsync(AgentId, ConversationId);
        await index.AddConversationAsync(AgentId, ConversationId);
        await index.AddConversationAsync(AgentId, ConversationId);

        // Assert - HashSet prevents duplicates
        var response = await index.GetConversationIdsAsync(AgentId);
        Assert.Single(response.Data);
        Assert.Contains(ConversationId, response.Data);
    }
}
