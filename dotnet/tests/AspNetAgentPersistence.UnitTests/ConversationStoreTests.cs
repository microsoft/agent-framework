// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Moq;

namespace AspNetAgentPersistence.UnitTests;

public class ConversationStoreTests
{
    [Fact]
    public async Task ConversationSurvivesNewStoreAndAgentWithoutDuplicatingHistoryAsync()
    {
        // Arrange
        string path = Path.Combine(Path.GetTempPath(), $"{Guid.NewGuid():N}.db");
        try
        {
            Guid id = Guid.NewGuid();
            List<ChatMessage> observed = [];
            var firstAgent = CreateAgent(observed);
            var store = new ConversationStore(path);
            AgentSession session = await store.LoadAsync(firstAgent, id);
            await firstAgent.RunAsync("Remember invoice 123", session);
            await store.SaveAsync(firstAgent, id, session);

            // Act: reconstruct both objects, as after an application restart.
            var resumedAgent = CreateAgent(observed);
            var reopened = new ConversationStore(path);
            AgentSession restored = await reopened.LoadAsync(resumedAgent, id);
            await resumedAgent.RunAsync("What invoice?", restored);
            await reopened.SaveAsync(resumedAgent, id, restored);
            restored = await reopened.LoadAsync(resumedAgent, id);
            await resumedAgent.RunAsync("Continue", restored);

            // Assert
            Assert.Equal(["Remember invoice 123", "reply", "What invoice?", "reply", "Continue"], observed.Select(m => m.Text));

            AgentSession separate = await reopened.LoadAsync(resumedAgent, Guid.NewGuid());
            await resumedAgent.RunAsync("New conversation", separate);
            Assert.Equal("New conversation", Assert.Single(observed).Text);
        }
        finally
        {
            File.Delete(path);
        }
    }

    [Fact]
    public async Task UncommittedSessionDoesNotReplaceStoredHistoryAsync()
    {
        // Arrange
        string path = Path.Combine(Path.GetTempPath(), $"{Guid.NewGuid():N}.db");
        try
        {
            Guid id = Guid.NewGuid();
            List<ChatMessage> observed = [];
            var agent = CreateAgent(observed);
            var store = new ConversationStore(path);
            AgentSession session = await store.LoadAsync(agent, id);
            await agent.RunAsync("Committed", session);
            await store.SaveAsync(agent, id, session);

            // Act: mutate the in-memory session but do not commit it.
            await agent.RunAsync("Uncommitted", session);
            AgentSession restored = await store.LoadAsync(agent, id);
            await agent.RunAsync("Retry", restored);

            // Assert
            Assert.Equal(["Committed", "reply", "Retry"], observed.Select(m => m.Text));
        }
        finally
        {
            File.Delete(path);
        }
    }

    [Fact]
    public async Task CompletedTurnCanBeCommittedAfterRequestCancellationAsync()
    {
        // Arrange
        string path = Path.Combine(Path.GetTempPath(), $"{Guid.NewGuid():N}.db");
        try
        {
            using CancellationTokenSource request = new();
            Guid id = Guid.NewGuid();
            List<ChatMessage> observed = [];
            var agent = CreateAgent(observed);
            var store = new ConversationStore(path);
            AgentSession session = await store.LoadAsync(agent, id, request.Token);
            await agent.RunAsync("Completed turn", session, cancellationToken: request.Token);

            // Act: the HTTP request is aborted after the model has finished.
            request.Cancel();
            await store.SaveAsync(agent, id, session, CancellationToken.None);
            AgentSession restored = await new ConversationStore(path).LoadAsync(agent, id);
            await agent.RunAsync("Next turn", restored);

            // Assert
            Assert.Equal(["Completed turn", "reply", "Next turn"], observed.Select(m => m.Text));
        }
        finally
        {
            File.Delete(path);
        }
    }
    private static ChatClientAgent CreateAgent(List<ChatMessage> observed)
    {
        var client = new Mock<IChatClient>();
        client.Setup(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((IEnumerable<ChatMessage> messages, ChatOptions? options, CancellationToken cancellationToken) =>
            {
                observed.Clear();
                observed.AddRange(messages);
                return new ChatResponse(new ChatMessage(ChatRole.Assistant, "reply"));
            });
        return new ChatClientAgent(client.Object);
    }
}
