// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using OpenAI.Responses;

namespace Microsoft.Agents.AI.OpenAI.UnitTests.ChatClient;

/// <summary>
/// Unit tests for the <see cref="AsyncStreamingResponseUpdateCollectionResult"/> class.
/// </summary>
public sealed class AsyncStreamingResponseUpdateCollectionResultTests
{
    /// <summary>
    /// Verify that GetContinuationToken returns null.
    /// </summary>
    [Fact]
    public void GetContinuationToken_ReturnsNull()
    {
        // Arrange
        IAsyncEnumerable<AgentResponseUpdate> updates = CreateTestUpdatesAsync();
        AsyncCollectionResult<StreamingResponseUpdate> collectionResult = new AsyncStreamingResponseUpdateCollectionResult(updates);

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
        AsyncCollectionResult<StreamingResponseUpdate> collectionResult = new AsyncStreamingResponseUpdateCollectionResult(updates);

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
    /// Verify that iterating through the collection yields streaming updates when RawRepresentation is a StreamingResponseUpdate.
    /// </summary>
    [Fact]
    public async Task IterateCollection_WithStreamingResponseUpdateRawRepresentation_YieldsUpdatesAsync()
    {
        // Arrange
        StreamingResponseUpdate rawUpdate = CreateStreamingResponseUpdate();
        IAsyncEnumerable<AgentResponseUpdate> updates = CreateTestUpdatesWithRawRepresentationAsync(rawUpdate);
        AsyncCollectionResult<StreamingResponseUpdate> collectionResult = new AsyncStreamingResponseUpdateCollectionResult(updates);

        // Act
        List<StreamingResponseUpdate> results = [];
        await foreach (StreamingResponseUpdate update in collectionResult)
        {
            results.Add(update);
        }

        // Assert
        Assert.Single(results);
        Assert.Same(rawUpdate, results[0]);
    }

    /// <summary>
    /// Verify that iterating through the collection yields updates when RawRepresentation is a ChatResponseUpdate containing a StreamingResponseUpdate.
    /// </summary>
    [Fact]
    public async Task IterateCollection_WithChatResponseUpdateContainingStreamingResponseUpdate_YieldsUpdatesAsync()
    {
        // Arrange
        StreamingResponseUpdate rawUpdate = CreateStreamingResponseUpdate();
        ChatResponseUpdate chatResponseUpdate = new() { RawRepresentation = rawUpdate };
        IAsyncEnumerable<AgentResponseUpdate> updates = CreateTestUpdatesWithChatResponseUpdateAsync(chatResponseUpdate);
        AsyncCollectionResult<StreamingResponseUpdate> collectionResult = new AsyncStreamingResponseUpdateCollectionResult(updates);

        // Act
        List<StreamingResponseUpdate> results = [];
        await foreach (StreamingResponseUpdate update in collectionResult)
        {
            results.Add(update);
        }

        // Assert
        Assert.Single(results);
        Assert.Same(rawUpdate, results[0]);
    }

    /// <summary>
    /// Verify that iterating through the collection skips updates when RawRepresentation is not a StreamingResponseUpdate.
    /// </summary>
    [Fact]
    public async Task IterateCollection_WithNonStreamingResponseUpdateRawRepresentation_SkipsUpdateAsync()
    {
        // Arrange
        IAsyncEnumerable<AgentResponseUpdate> updates = CreateTestUpdatesAsync();
        AsyncCollectionResult<StreamingResponseUpdate> collectionResult = new AsyncStreamingResponseUpdateCollectionResult(updates);

        // Act
        List<StreamingResponseUpdate> results = [];
        await foreach (StreamingResponseUpdate update in collectionResult)
        {
            results.Add(update);
        }

        // Assert
        Assert.Empty(results);
    }

    /// <summary>
    /// Verify that iterating through the collection skips updates when RawRepresentation is a ChatResponseUpdate without StreamingResponseUpdate.
    /// </summary>
    [Fact]
    public async Task IterateCollection_WithChatResponseUpdateWithoutStreamingResponseUpdate_SkipsUpdateAsync()
    {
        // Arrange
        ChatResponseUpdate chatResponseUpdate = new() { RawRepresentation = "not a streaming update" };
        IAsyncEnumerable<AgentResponseUpdate> updates = CreateTestUpdatesWithChatResponseUpdateAsync(chatResponseUpdate);
        AsyncCollectionResult<StreamingResponseUpdate> collectionResult = new AsyncStreamingResponseUpdateCollectionResult(updates);

        // Act
        List<StreamingResponseUpdate> results = [];
        await foreach (StreamingResponseUpdate update in collectionResult)
        {
            results.Add(update);
        }

        // Assert
        Assert.Empty(results);
    }

    private static async IAsyncEnumerable<AgentResponseUpdate> CreateTestUpdatesAsync()
    {
        yield return new AgentResponseUpdate(ChatRole.Assistant, "test");
        await Task.CompletedTask;
    }

    private static async IAsyncEnumerable<AgentResponseUpdate> CreateTestUpdatesWithRawRepresentationAsync(object rawRepresentation)
    {
        AgentResponseUpdate update = new(ChatRole.Assistant, "test")
        {
            RawRepresentation = rawRepresentation
        };
        yield return update;
        await Task.CompletedTask;
    }

    private static async IAsyncEnumerable<AgentResponseUpdate> CreateTestUpdatesWithChatResponseUpdateAsync(ChatResponseUpdate chatResponseUpdate)
    {
        AgentResponseUpdate update = new(ChatRole.Assistant, "test")
        {
            RawRepresentation = chatResponseUpdate
        };
        yield return update;
        await Task.CompletedTask;
    }

    private static StreamingResponseUpdate CreateStreamingResponseUpdate()
    {
        const string Json = """
        {
            "type": "response.output_item.added",
            "sequence_number": 1,
            "output_index": 0,
            "item": {
                "id": "item_abc123",
                "type": "message",
                "status": "in_progress",
                "role": "assistant",
                "content": []
            }
        }
        """;

        return System.ClientModel.Primitives.ModelReaderWriter.Read<StreamingResponseUpdate>(BinaryData.FromString(Json))!;
    }
}
