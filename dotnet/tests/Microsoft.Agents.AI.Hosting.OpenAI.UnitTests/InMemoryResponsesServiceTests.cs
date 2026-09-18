// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Conversations;
using Microsoft.Agents.AI.Hosting.OpenAI.Conversations.Models;
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
