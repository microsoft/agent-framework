// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Conversations;
using Microsoft.Agents.AI.Hosting.OpenAI.Conversations.Models;
using Microsoft.Agents.AI.Hosting.OpenAI.Models;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Unit tests for <see cref="InMemoryResponsesService"/> request validation.
/// </summary>
public sealed class InMemoryResponsesServiceTests
{
    [Fact]
    public async Task ValidateRequestAsync_NonexistentConversation_ReturnsNotFoundErrorAsync()
    {
        // Arrange
        using var storage = new InMemoryConversationStorage();
        using var service = new InMemoryResponsesService(
            new StubResponseExecutor(), new InMemoryStorageOptions(), storage);
        var request = new CreateResponse
        {
            Input = ResponseInput.FromText("hello"),
            Conversation = ConversationReference.FromId("conv_does_not_exist")
        };

        // Act
        ResponseError? error = await service.ValidateRequestAsync(request);

        // Assert
        Assert.NotNull(error);
        Assert.Equal("conversation_not_found", error.Code);
    }

    [Fact]
    public async Task ValidateRequestAsync_ExistingConversation_ReturnsNullAsync()
    {
        // Arrange
        using var storage = new InMemoryConversationStorage();
        var conversation = new Conversation
        {
            Id = "conv_" + Guid.NewGuid().ToString("N"),
            CreatedAt = DateTimeOffset.UtcNow.ToUnixTimeSeconds()
        };
        await storage.CreateConversationAsync(conversation);
        using var service = new InMemoryResponsesService(
            new StubResponseExecutor(), new InMemoryStorageOptions(), storage);
        var request = new CreateResponse
        {
            Input = ResponseInput.FromText("hello"),
            Conversation = ConversationReference.FromId(conversation.Id)
        };

        // Act
        ResponseError? error = await service.ValidateRequestAsync(request);

        // Assert
        Assert.Null(error);
    }

    [Fact]
    public async Task ValidateRequestAsync_ConversationSuppliedButNoStorage_ReturnsNullAsync()
    {
        // Arrange - without a conversation store there is no existence to verify.
        using var service = new InMemoryResponsesService(
            new StubResponseExecutor(), new InMemoryStorageOptions());
        var request = new CreateResponse
        {
            Input = ResponseInput.FromText("hello"),
            Conversation = ConversationReference.FromId("conv_does_not_exist")
        };

        // Act
        ResponseError? error = await service.ValidateRequestAsync(request);

        // Assert
        Assert.Null(error);
    }

    /// <summary>
    /// Pagination of the input items of a response holding six messages. Numbers are positions in the
    /// list returned in the order under test, so 0 is the first item listed; a cursor of -1 is not sent,
    /// and 99 names an id the response does not have.
    /// </summary>
    [Theory]
    [InlineData(true, -1, -1, null, new[] { 0, 1, 2, 3, 4, 5 }, false)] // no cursor
    [InlineData(true, 1, -1, null, new[] { 2, 3, 4, 5 }, false)] // after 1
    [InlineData(true, -1, 4, null, new[] { 0, 1, 2, 3 }, false)] // before 4
    [InlineData(true, 1, 4, null, new[] { 2, 3 }, false)] // between 1 and 4
    [InlineData(false, 1, 4, null, new[] { 2, 3 }, false)] // between them, in descending order
    [InlineData(true, 1, 4, 1, new[] { 2 }, true)] // between them, one page at a time
    [InlineData(true, 4, 1, null, new int[0], false)] // before precedes after
    [InlineData(true, 2, 2, null, new int[0], false)] // the same item as both cursors
    [InlineData(true, 99, -1, null, new[] { 0, 1, 2, 3, 4, 5 }, false)] // unknown after: ignored
    [InlineData(true, -1, 99, null, new[] { 0, 1, 2, 3, 4, 5 }, false)] // unknown before: ignored
    public async Task ListResponseInputItemsAsync_ReturnsTheItemsTheCursorsSelectAsync(
        bool ascending, int after, int before, int? limit, int[] expected, bool hasMore)
    {
        // Arrange
        SortOrder order = ascending ? SortOrder.Ascending : SortOrder.Descending;
        using var service = new InMemoryResponsesService(new StubResponseExecutor(), new InMemoryStorageOptions());
        Response response = await service.CreateResponseAsync(new CreateResponse
        {
            Input = ResponseInput.FromMessages(
                Enumerable.Range(0, 6)
                    .Select(i => new InputMessage { Role = ChatRole.User, Content = $"message {i}" })
                    .ToList())
        });
        List<string> ids = (await service.ListResponseInputItemsAsync(response.Id, limit: 100, order: order))
            .Data.ConvertAll(item => item.Id);

        // Act
        ListResponse<ItemResource> page = await service.ListResponseInputItemsAsync(
            response.Id,
            limit: limit,
            order: order,
            after: Cursor(after),
            before: Cursor(before));

        // Assert
        Assert.Equal(expected.Select(position => ids[position]), page.Data.Select(item => item.Id));
        Assert.Equal(hasMore, page.HasMore);

        string? Cursor(int position) => position switch
        {
            -1 => null,
            99 => "msg_unknown",
            _ => ids[position]
        };
    }

    private sealed class StubResponseExecutor : IResponseExecutor
    {
        public ValueTask<ResponseError?> ValidateRequestAsync(CreateResponse request, CancellationToken cancellationToken = default)
            => ValueTask.FromResult<ResponseError?>(null);

        public async IAsyncEnumerable<StreamingResponseEvent> ExecuteAsync(
            AgentInvocationContext context,
            CreateResponse request,
            IReadOnlyList<ChatMessage>? conversationHistory = null,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            await Task.CompletedTask.ConfigureAwait(false);
            yield break;
        }
    }
}
