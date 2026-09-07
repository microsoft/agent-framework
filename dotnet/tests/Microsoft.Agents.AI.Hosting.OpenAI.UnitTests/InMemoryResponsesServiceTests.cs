// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Conversations;
using Microsoft.Agents.AI.Hosting.OpenAI.Conversations.Models;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Moq;

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

    [Fact]
    public async Task DeleteResponseAsync_RemovesPersistedAgentSessionAsync()
    {
        // Arrange
        AIAgent agent = new ChatClientAgent(new TestHelpers.SimpleMockChatClient(), name: "agent");
        AgentSession session = await agent.CreateSessionAsync();
        Mock<AgentSessionStore> store = new();
        store.Setup(s => s.GetSessionAsync(agent, It.IsAny<string>(), It.IsAny<CancellationToken>())).ReturnsAsync(session);
        ServiceCollection services = new();
        services.AddKeyedSingleton(agent.Name, store.Object);
        using ServiceProvider provider = services.BuildServiceProvider();
        using var service = new InMemoryResponsesService(new AIAgentResponseExecutor(agent, provider));
        Response response = await service.CreateResponseAsync(new CreateResponse { Input = "hello" });
        Assert.Equal(ResponseStatus.Completed, response.Status);

        // Act
        bool deleted = await service.DeleteResponseAsync(response.Id);

        // Assert
        Assert.True(deleted);
        Assert.Null(await service.GetResponseAsync(response.Id));
        store.Verify(s => s.DeleteSessionAsync(agent, response.Id, It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task CreateResponseStreamingAsync_SessionSaveFails_ReportsFailureWithoutCompletionAsync()
    {
        // Arrange
        AIAgent agent = new ChatClientAgent(new TestHelpers.SimpleMockChatClient(), name: "agent");
        AgentSession session = await agent.CreateSessionAsync();
        Mock<AgentSessionStore> store = new();
        store.Setup(s => s.GetSessionAsync(agent, It.IsAny<string>(), It.IsAny<CancellationToken>())).ReturnsAsync(session);
        store.Setup(s => s.SaveSessionAsync(agent, It.IsAny<string>(), session, It.IsAny<CancellationToken>()))
            .Returns(() => ValueTask.FromException(new InvalidOperationException("session save failed")));
        ServiceCollection services = new();
        services.AddKeyedSingleton(agent.Name, store.Object);
        using ServiceProvider provider = services.BuildServiceProvider();
        using var service = new InMemoryResponsesService(new AIAgentResponseExecutor(agent, provider));

        // Act
        List<StreamingResponseEvent> events = await service.CreateResponseStreamingAsync(
            new CreateResponse { Input = "hello", Stream = true }).ToListAsync();

        // Assert
        StreamingResponseFailed failure = Assert.IsType<StreamingResponseFailed>(events.Last());
        Assert.Equal("session save failed", failure.Response.Error?.Message);
        Assert.DoesNotContain(events, e => e is StreamingResponseCompleted);
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
