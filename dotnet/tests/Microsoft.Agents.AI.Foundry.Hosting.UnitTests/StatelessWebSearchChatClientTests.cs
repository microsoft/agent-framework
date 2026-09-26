// Copyright (c) Microsoft. All rights reserved.

#if NET10_0
#pragma warning disable OPENAI001 // Web-search response items are experimental.

using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;
using OpenAI.Responses;
using SampleApp;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

public class StatelessWebSearchChatClientTests
{
    [Fact]
    public async Task GetStreamingResponseAsync_RemovesRawSearchResultWithoutMutatingHistoryAsync()
    {
        // Arrange
        var rawSearch = ResponseItem.CreateWebSearchCallItem();
        var searchResult = new WebSearchToolResultContent("search_1") { RawRepresentation = rawSearch };
        var searchCall = new WebSearchToolCallContent("search_1");
        var functionCall = new FunctionCallContent("call_1", "file_memory_write");
        var assistant = new ChatMessage(ChatRole.Assistant,
        [
            new TextContent("Source citation"),
            searchCall,
            searchResult,
            functionCall,
        ]);
        var tool = new ChatMessage(ChatRole.Tool, [new FunctionResultContent("call_1", "saved")]);
        List<ChatMessage>? forwarded = null;
        var inner = new Mock<IChatClient>();
        inner.Setup(client => client.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .Returns((IEnumerable<ChatMessage> messages, ChatOptions? _, CancellationToken _) =>
            {
                forwarded = messages.ToList();
                return GetUpdatesAsync();
            });

        // Act
        var client = new StatelessWebSearchChatClient(inner.Object);
        await foreach (var _ in client.GetStreamingResponseAsync([assistant, tool], new ChatOptions()))
        {
        }

        // Assert: only the raw search item is withheld from the model; stored history and
        // the following function call and result keep their original identities.
        Assert.NotNull(forwarded);
        Assert.Equal(2, forwarded.Count);
        Assert.NotSame(assistant, forwarded[0]);
        Assert.NotSame(assistant.Contents, forwarded[0].Contents);
        Assert.DoesNotContain(forwarded[0].Contents, content => content is WebSearchToolResultContent);
        Assert.Contains(forwarded[0].Contents, content => ReferenceEquals(content, searchCall));
        Assert.Contains(forwarded[0].Contents, content => ReferenceEquals(content, functionCall));
        Assert.Same(tool, forwarded[1]);
        Assert.Same(searchResult, assistant.Contents[2]);
        Assert.Same(rawSearch, searchResult.RawRepresentation);
    }

    [Fact]
    public async Task GetResponseAsync_RemovesRawSearchResultButKeepsUnrelatedContentsAsync()
    {
        // Arrange
        var searchResult = new WebSearchToolResultContent("search_1")
        {
            RawRepresentation = ResponseItem.CreateWebSearchCallItem(),
        };
        var otherSearchResult = new WebSearchToolResultContent("search_2");
        var assistant = new ChatMessage(ChatRole.Assistant,
        [
            new TextContent("Summary"),
            searchResult,
            otherSearchResult,
        ]);
        List<ChatMessage>? forwarded = null;
        var inner = new Mock<IChatClient>();
        inner.Setup(client => client.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .Returns((IEnumerable<ChatMessage> messages, ChatOptions? _, CancellationToken _) =>
            {
                forwarded = messages.ToList();
                return Task.FromResult(new ChatResponse(new ChatMessage(ChatRole.Assistant, "done")));
            });

        // Act
        var client = new StatelessWebSearchChatClient(inner.Object);
        _ = await client.GetResponseAsync([assistant], new ChatOptions());

        // Assert
        Assert.NotNull(forwarded);
        Assert.DoesNotContain(forwarded[0].Contents, content => ReferenceEquals(content, searchResult));
        Assert.Contains(forwarded[0].Contents, content => ReferenceEquals(content, otherSearchResult));
        Assert.Contains(assistant.Contents, content => ReferenceEquals(content, searchResult));
    }

    private static async IAsyncEnumerable<ChatResponseUpdate> GetUpdatesAsync()
    {
        yield return new ChatResponseUpdate(ChatRole.Assistant, "done");
        await Task.CompletedTask;
    }
}
#endif
