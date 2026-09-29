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

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task ListResponseInputItemsAsync_WithAfterAndBefore_ReturnsOnlyTheItemsBetweenThemAsync(bool ascending)
    {
        SortOrder order = ascending ? SortOrder.Ascending : SortOrder.Descending;

        // Arrange
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
            response.Id, order: order, after: ids[1], before: ids[4]);

        // Assert
        Assert.Equal([ids[2], ids[3]], page.Data.Select(item => item.Id));
        Assert.False(page.HasMore);
    }

    [Fact]
    public async Task ListResponseInputItemsAsync_WithBeforePrecedingAfter_ReturnsAnEmptyPageAsync()
    {
        // Arrange
        using var service = new InMemoryResponsesService(new StubResponseExecutor(), new InMemoryStorageOptions());
        Response response = await service.CreateResponseAsync(new CreateResponse
        {
            Input = ResponseInput.FromMessages(
                Enumerable.Range(0, 6)
                    .Select(i => new InputMessage { Role = ChatRole.User, Content = $"message {i}" })
                    .ToList())
        });
        List<string> ids = (await service.ListResponseInputItemsAsync(response.Id, limit: 100, order: SortOrder.Ascending))
            .Data.ConvertAll(item => item.Id);

        // Act
        ListResponse<ItemResource> page = await service.ListResponseInputItemsAsync(
            response.Id, order: SortOrder.Ascending, after: ids[4], before: ids[1]);

        // Assert
        Assert.Empty(page.Data);
        Assert.False(page.HasMore);
    }

    [Fact]
    public async Task ListResponseInputItemsAsync_WithBeforeOnly_ReturnsTheItemsBeforeItAsync()
    {
        // Arrange
        using var service = new InMemoryResponsesService(new StubResponseExecutor(), new InMemoryStorageOptions());
        Response response = await service.CreateResponseAsync(new CreateResponse
        {
            Input = ResponseInput.FromMessages(
                Enumerable.Range(0, 4)
                    .Select(i => new InputMessage { Role = ChatRole.User, Content = $"message {i}" })
                    .ToList())
        });
        List<string> ids = (await service.ListResponseInputItemsAsync(response.Id, limit: 100, order: SortOrder.Ascending))
            .Data.ConvertAll(item => item.Id);

        // Act
        ListResponse<ItemResource> page = await service.ListResponseInputItemsAsync(
            response.Id, order: SortOrder.Ascending, before: ids[2]);

        // Assert
        Assert.Equal([ids[0], ids[1]], page.Data.Select(item => item.Id));
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
