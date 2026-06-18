// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel;
using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using OpenAI.Chat;

namespace Microsoft.Agents.AI.OpenAI.UnitTests.ChatClient;

/// <summary>
/// Unit tests for the <see cref="AsyncStreamingChatCompletionUpdateCollectionResult"/> class.
/// </summary>
public sealed class AsyncStreamingChatCompletionUpdateCollectionResultTests
{
    /// <summary>
    /// Verify that GetContinuationToken returns null.
    /// </summary>
    [Fact]
    public void GetContinuationToken_ReturnsNull()
    {
        // Arrange
        IAsyncEnumerable<AgentResponseUpdate> updates = CreateTestUpdatesAsync();
        AsyncCollectionResult<StreamingChatCompletionUpdate> collectionResult = new AsyncStreamingChatCompletionUpdateCollectionResult(updates);

        // Act
        ContinuationToken? token = collectionResult.GetContinuationToken(null!);

        // Assert
        Assert.Null(token);
    }

    /// <summary>
    /// Verify that GetRawPagesAsync returns a single page.
    /// </summary>
    [Fact]
    public async Task GetRawPagesAsync_ReturnsSinglePageAsync()
    {
        // Arrange
        IAsyncEnumerable<AgentResponseUpdate> updates = CreateTestUpdatesAsync();
        AsyncCollectionResult<StreamingChatCompletionUpdate> collectionResult = new AsyncStreamingChatCompletionUpdateCollectionResult(updates);

        // Act
        List<ClientResult> pages = [];
        await foreach (ClientResult page in collectionResult.GetRawPagesAsync())
        {
            pages.Add(page);
        }

        // Assert
        Assert.Single(pages);
    }

    /// <summary>
    /// Verify that iterating through the collection yields streaming updates.
    /// </summary>
    [Fact]
    public async Task IterateCollection_YieldsUpdatesAsync()
    {
        // Arrange
        IAsyncEnumerable<AgentResponseUpdate> updates = CreateTestUpdatesAsync();
        AsyncCollectionResult<StreamingChatCompletionUpdate> collectionResult = new AsyncStreamingChatCompletionUpdateCollectionResult(updates);

        // Act
        List<StreamingChatCompletionUpdate> results = [];
        await foreach (StreamingChatCompletionUpdate update in collectionResult)
        {
            results.Add(update);
        }

        // Assert
        Assert.Single(results);
    }

    /// <summary>
    /// Verify that iterating through the collection with multiple updates yields all updates.
    /// </summary>
    [Fact]
    public async Task IterateCollection_WithMultipleUpdates_YieldsAllUpdatesAsync()
    {
        // Arrange
        IAsyncEnumerable<AgentResponseUpdate> updates = CreateMultipleTestUpdatesAsync();
        AsyncCollectionResult<StreamingChatCompletionUpdate> collectionResult = new AsyncStreamingChatCompletionUpdateCollectionResult(updates);

        // Act
        List<StreamingChatCompletionUpdate> results = [];
        await foreach (StreamingChatCompletionUpdate update in collectionResult)
        {
            results.Add(update);
        }

        // Assert
        Assert.Equal(3, results.Count);
    }

    private static async IAsyncEnumerable<AgentResponseUpdate> CreateTestUpdatesAsync()
    {
        yield return new AgentResponseUpdate(ChatRole.Assistant, "test");
        await Task.CompletedTask;
    }

    private static async IAsyncEnumerable<AgentResponseUpdate> CreateMultipleTestUpdatesAsync()
    {
        yield return new AgentResponseUpdate(ChatRole.Assistant, "first");
        yield return new AgentResponseUpdate(ChatRole.Assistant, "second");
        yield return new AgentResponseUpdate(ChatRole.Assistant, "third");
        await Task.CompletedTask;
    }
}
