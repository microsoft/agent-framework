// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Moq;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Tests for session persistence in the Responses agent executor.
/// </summary>
public sealed class AIAgentResponseExecutorTests
{
    [Fact]
    public async Task ExecuteAsync_PreviousResponseId_RestoresIndependentSnapshotsAsync()
    {
        // Arrange
        var chatClient = new TestHelpers.ConversationMemoryMockChatClient("answer");
        AIAgent agent = new ChatClientAgent(chatClient, name: "agent");
        List<AgentSession?> sessions = [];
        agent = agent.AsBuilder().Use((messages, session, options, next, cancellationToken) =>
        {
            sessions.Add(session);
            return next(messages, session, options, cancellationToken);
        }).Build();
        AgentSessionStore store = new InMemoryAgentSessionStore();

        // Act - Recreate the executor on each request; only the store carries continuity.
        await RunAsync(agent, store, "resp_root", "root");
        await RunAsync(agent, store, "resp_left", "left", previousResponseId: "resp_root");
        await RunAsync(agent, store, "resp_right", "right", previousResponseId: "resp_root");
        await RunAsync(agent, store, "resp_left_next", "left next", previousResponseId: "resp_left");

        // Assert
        Assert.Equal(4, sessions.Count);
        Assert.All(sessions, Assert.NotNull);
        Assert.Equal(4, sessions.Distinct().Count());
        Assert.Equal(["root", "left"], UserTexts(chatClient.CallHistory[1]));
        Assert.Equal(["root", "right"], UserTexts(chatClient.CallHistory[2]));
        Assert.Equal(["root", "left", "left next"], UserTexts(chatClient.CallHistory[3]));
    }

    [Fact]
    public async Task ExecuteAsync_Conversation_RestoresHeadWithoutReplayingTranscriptAsync()
    {
        // Arrange
        var chatClient = new TestHelpers.ConversationMemoryMockChatClient("answer");
        AIAgent agent = new ChatClientAgent(chatClient, name: "agent");
        AgentSessionStore store = new InMemoryAgentSessionStore();
        IReadOnlyList<ChatMessage> transcript = [new(ChatRole.User, "transcript must not be replayed")];

        // Act
        await RunAsync(agent, store, "resp_one", "one", conversationId: "conv_1");
        await RunAsync(agent, store, "resp_two", "two", conversationId: "conv_1", history: transcript);
        await RunAsync(agent, store, "resp_three", "three", conversationId: "conv_1", history: transcript);
        await RunAsync(agent, store, "resp_branch", "branch", previousResponseId: "resp_one");

        // Assert
        Assert.Equal(["one", "two"], UserTexts(chatClient.CallHistory[1]));
        Assert.Equal(["one", "two", "three"], UserTexts(chatClient.CallHistory[2]));
        Assert.Equal(["one", "branch"], UserTexts(chatClient.CallHistory[3]));
    }

    [Fact]
    public async Task ExecuteAsync_NoSessionStore_PreservesTranscriptBasedBehaviorAsync()
    {
        // Arrange
        var chatClient = new TestHelpers.ConversationMemoryMockChatClient("answer");
        AIAgent agent = new ChatClientAgent(chatClient, name: "agent");
        IReadOnlyList<ChatMessage> transcript = [new(ChatRole.User, "prior turn")];

        // Act
        await RunAsync(agent, null, "resp_one", "one");
        await RunAsync(agent, null, "resp_two", "two", history: transcript);

        // Assert
        Assert.Equal(["prior turn", "two"], UserTexts(chatClient.CallHistory[1]));
    }

    [Fact]
    public async Task ExecuteAsync_SameConversation_DifferentAgentsHaveIndependentSessionsAsync()
    {
        // Arrange
        var firstClient = new TestHelpers.ConversationMemoryMockChatClient("first answer");
        var secondClient = new TestHelpers.ConversationMemoryMockChatClient("second answer");
        AIAgent firstAgent = new ChatClientAgent(firstClient, name: "first");
        AIAgent secondAgent = new ChatClientAgent(secondClient, name: "second");
        AgentSessionStore store = new InMemoryAgentSessionStore();

        // Act
        await RunAsync(firstAgent, store, "resp_one", "first user's turn", conversationId: "conv_same");
        await RunAsync(secondAgent, store, "resp_two", "second user's turn", conversationId: "conv_same");
        await RunAsync(firstAgent, store, "resp_three", "first next", conversationId: "conv_same");

        // Assert
        Assert.Equal(["second user's turn"], UserTexts(secondClient.CallHistory[0]));
        Assert.Equal(["first user's turn", "first next"], UserTexts(firstClient.CallHistory[1]));
    }

    [Fact]
    public async Task ExecuteAsync_StoreFalse_DoesNotSaveResponseSnapshotAsync()
    {
        // Arrange
        AIAgent agent = new ChatClientAgent(new TestHelpers.SimpleMockChatClient(), name: "agent");
        Mock<AgentSessionStore> store = new();
        AgentSession session = await agent.CreateSessionAsync();
        store.Setup(s => s.GetSessionAsync(agent, "conv_1", It.IsAny<CancellationToken>())).ReturnsAsync(session);
        using ServiceProvider services = CreateServices(agent, store.Object);
        var executor = new AIAgentResponseExecutor(agent, services);
        CreateResponse request = new()
        {
            Input = "hello",
            Store = false,
            Conversation = ConversationReference.FromId("conv_1")
        };

        // Act
        List<StreamingResponseEvent> events = await executor.ExecuteAsync(
            new AgentInvocationContext(new IdGenerator("resp_1", "conv_1")), request).ToListAsync();

        // Assert
        Assert.IsType<StreamingResponseCompleted>(events.Last());
        store.Verify(s => s.SaveSessionAsync(agent, "resp_1", session, It.IsAny<CancellationToken>()), Times.Never);
        store.Verify(s => s.SaveSessionAsync(agent, "conv_1", session, It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task ExecuteAsync_SaveFails_DoesNotPublishCompletionAsync()
    {
        // Arrange
        AIAgent agent = new ChatClientAgent(new TestHelpers.SimpleMockChatClient(), name: "agent");
        Mock<AgentSessionStore> store = new();
        AgentSession session = await agent.CreateSessionAsync();
        store.Setup(s => s.GetSessionAsync(agent, "resp_1", It.IsAny<CancellationToken>())).ReturnsAsync(session);
        store.Setup(s => s.SaveSessionAsync(agent, "resp_1", session, It.IsAny<CancellationToken>()))
            .Returns(() => ValueTask.FromException(new InvalidOperationException("save failed")));
        using ServiceProvider services = CreateServices(agent, store.Object);
        var executor = new AIAgentResponseExecutor(agent, services);
        List<StreamingResponseEvent> events = [];

        // Act
        InvalidOperationException exception = await Assert.ThrowsAsync<InvalidOperationException>(async () =>
        {
            await foreach (StreamingResponseEvent item in executor.ExecuteAsync(
                new AgentInvocationContext(new IdGenerator("resp_1", null)), new CreateResponse { Input = "hello" }))
            {
                events.Add(item);
            }
        });

        // Assert
        Assert.Equal("save failed", exception.Message);
        Assert.DoesNotContain(events, e => e is StreamingResponseCompleted);
    }

    [Fact]
    public async Task ExecuteAsync_SaveIsPending_CompletionWaitsForPersistenceAsync()
    {
        // Arrange
        AIAgent agent = new ChatClientAgent(new TestHelpers.SimpleMockChatClient(), name: "agent");
        var saveStarted = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var allowSave = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        AgentSession session = await agent.CreateSessionAsync();
        Mock<AgentSessionStore> store = new();
        store.Setup(s => s.GetSessionAsync(agent, "resp_1", It.IsAny<CancellationToken>())).ReturnsAsync(session);
        store.Setup(s => s.SaveSessionAsync(agent, "resp_1", session, It.IsAny<CancellationToken>()))
            .Returns(() =>
            {
                saveStarted.SetResult();
                return new ValueTask(allowSave.Task);
            });
        using ServiceProvider services = CreateServices(agent, store.Object);
        var executor = new AIAgentResponseExecutor(agent, services);

        // Act
        Task<List<StreamingResponseEvent>> execution = executor.ExecuteAsync(
            new AgentInvocationContext(new IdGenerator("resp_1", null)), new CreateResponse { Input = "hello" }).ToListAsync().AsTask();
        await saveStarted.Task.WaitAsync(TimeSpan.FromSeconds(10));
        bool completedBeforeSave = execution.IsCompleted;
        allowSave.SetResult();
        List<StreamingResponseEvent> events = await execution;

        // Assert
        Assert.False(completedBeforeSave);
        Assert.IsType<StreamingResponseCompleted>(events.Last());
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task ExecuteAsync_RunFails_DoesNotSaveSessionAsync(bool cancelled)
    {
        // Arrange
        AIAgent agent = new ChatClientAgent(new TestHelpers.SimpleMockChatClient(), name: "agent");
        Exception failure = cancelled ? new OperationCanceledException() : new InvalidOperationException("run failed");
        agent = agent.AsBuilder().Use((_, _, _, _, _) => Task.FromException(failure)).Build();
        AgentSession session = await agent.CreateSessionAsync();
        Mock<AgentSessionStore> store = new();
        store.Setup(s => s.GetSessionAsync(agent, "resp_1", It.IsAny<CancellationToken>())).ReturnsAsync(session);
        using ServiceProvider provider = CreateServices(agent, store.Object);
        var executor = new AIAgentResponseExecutor(agent, provider);

        // Act
        Exception? exception = await Record.ExceptionAsync(() => executor.ExecuteAsync(
            new AgentInvocationContext(new IdGenerator("resp_1", null)), new CreateResponse { Input = "hello" }).ToListAsync().AsTask());

        // Assert
        Assert.Same(failure, exception);
        store.Verify(s => s.SaveSessionAsync(It.IsAny<AIAgent>(), It.IsAny<string>(), It.IsAny<AgentSession>(), It.IsAny<CancellationToken>()), Times.Never);
    }

    [Fact]
    public async Task ExecuteAsync_CancelledDuringSave_DoesNotPublishCompletionAsync()
    {
        // Arrange
        using CancellationTokenSource cancellation = new();
        AIAgent agent = new ChatClientAgent(new TestHelpers.SimpleMockChatClient(), name: "agent");
        AgentSession session = await agent.CreateSessionAsync();
        Mock<AgentSessionStore> store = new();
        store.Setup(s => s.GetSessionAsync(agent, "resp_1", cancellation.Token)).ReturnsAsync(session);
        store.Setup(s => s.SaveSessionAsync(agent, "resp_1", session, cancellation.Token)).Returns(() =>
        {
            cancellation.Cancel();
            return ValueTask.CompletedTask;
        });
        using ServiceProvider provider = CreateServices(agent, store.Object);
        var executor = new AIAgentResponseExecutor(agent, provider);
        List<StreamingResponseEvent> events = [];

        // Act
        await Assert.ThrowsAnyAsync<OperationCanceledException>(async () =>
        {
            await foreach (StreamingResponseEvent item in executor.ExecuteAsync(
                new AgentInvocationContext(new IdGenerator("resp_1", null)), new CreateResponse { Input = "hello" },
                cancellationToken: cancellation.Token))
            {
                events.Add(item);
            }
        });

        // Assert
        Assert.DoesNotContain(events, e => e is StreamingResponseCompleted);
    }

    [Fact]
    public async Task DeleteResponseStateAsync_WaitsForRunBeforeDeletingSnapshotAsync()
    {
        // Arrange
        AIAgent agent = new ChatClientAgent(new TestHelpers.SimpleMockChatClient(), name: "agent");
        Mock<AgentSessionStore> store = new();
        using ServiceProvider provider = CreateServices(agent, store.Object);
        var executor = new AIAgentResponseExecutor(agent, provider);
        var completion = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);

        // Act
        Task deletion = executor.DeleteResponseStateAsync("resp_1", new CreateResponse { Input = "hello" }, completion.Task).AsTask();
        bool deletedBeforeCompletion = deletion.IsCompleted;
        store.Verify(s => s.DeleteSessionAsync(agent, "resp_1", It.IsAny<CancellationToken>()), Times.Never);
        completion.SetResult();
        await deletion;

        // Assert
        Assert.False(deletedBeforeCompletion);
        store.Verify(s => s.DeleteSessionAsync(agent, "resp_1", It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task DeleteResponseStateAsync_NoStore_DoesNotWaitForRunAsync()
    {
        // Arrange
        AIAgent agent = new ChatClientAgent(new TestHelpers.SimpleMockChatClient(), name: "agent");
        using ServiceProvider provider = CreateServices(agent, null);
        var executor = new AIAgentResponseExecutor(agent, provider);
        var completion = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);

        // Act
        Task deletion = executor.DeleteResponseStateAsync("resp_1", new CreateResponse { Input = "hello" }, completion.Task).AsTask();
        bool deletedBeforeCompletion = deletion.IsCompleted;
        completion.SetResult();
        await deletion;

        // Assert
        Assert.True(deletedBeforeCompletion);
    }

    [Fact]
    public async Task DeleteResponseStateAsync_DeletesSnapshotWithoutDeletingConversationHeadAsync()
    {
        // Arrange
        var chatClient = new TestHelpers.ConversationMemoryMockChatClient("answer");
        AIAgent agent = new ChatClientAgent(chatClient, name: "agent");
        AgentSessionStore store = new InMemoryAgentSessionStore();
        await RunAsync(agent, store, "resp_1", "one", conversationId: "conv_1");
        using ServiceProvider provider = CreateServices(agent, store);
        var executor = new AIAgentResponseExecutor(agent, provider);

        // Act
        await executor.DeleteResponseStateAsync("resp_1", new CreateResponse { Input = "one", Conversation = ConversationReference.FromId("conv_1") });
        await RunAsync(agent, store, "resp_two", "two", conversationId: "conv_1");
        await RunAsync(agent, store, "resp_missing", "fresh", previousResponseId: "resp_1");

        // Assert
        Assert.Equal(["one", "two"], UserTexts(chatClient.CallHistory[1]));
        Assert.Equal(["fresh"], UserTexts(chatClient.CallHistory[2]));
    }

    [Fact]
    public async Task ResolveSessionStore_IsolatesCustomStoreByCallerAsync()
    {
        // Arrange
        ServiceCollection services = new();
        services.AddKeyedSingleton<AgentSessionStore>("agent", new InMemoryAgentSessionStore());
        Mock<AgentIsolationKeyProvider> provider = new();
        string caller = "alice";
        provider.Setup(p => p.GetIsolationKeyAsync(It.IsAny<CancellationToken>()))
            .Returns(() => ValueTask.FromResult<string?>(caller));
        services.AddSingleton(provider.Object);
        using ServiceProvider serviceProvider = services.BuildServiceProvider();
        var chatClient = new TestHelpers.ConversationMemoryMockChatClient("answer");
        AIAgent agent = new ChatClientAgent(chatClient, name: "agent");

        // Act
        var executor = new AIAgentResponseExecutor(agent, serviceProvider);
        await RunAsync(executor, "resp_alice", "alice's turn", conversationId: "conv_same");
        caller = "bob";
        await RunAsync(executor, "resp_bob", "bob's turn", conversationId: "conv_same");
        caller = "alice";
        await RunAsync(executor, "resp_alice_next", "alice next", conversationId: "conv_same");

        // Assert
        Assert.Equal(["bob's turn"], UserTexts(chatClient.CallHistory[1]));
        Assert.Equal(["alice's turn", "alice next"], UserTexts(chatClient.CallHistory[2]));
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task ResolveSessionStore_PrefersResolvedAgentStoreThenDefaultAsync(bool registerKeyedStore)
    {
        // Arrange
        AIAgent agent = new ChatClientAgent(new TestHelpers.SimpleMockChatClient(), name: "actual-agent");
        Mock<AgentSessionStore> keyedStore = new();
        Mock<AgentSessionStore> defaultStore = new();
        Mock<AgentSessionStore> otherStore = new(MockBehavior.Strict);
        AgentSession session = await agent.CreateSessionAsync();
        keyedStore.Setup(s => s.GetSessionAsync(agent, "resp_1", It.IsAny<CancellationToken>())).ReturnsAsync(session);
        defaultStore.Setup(s => s.GetSessionAsync(agent, "resp_1", It.IsAny<CancellationToken>())).ReturnsAsync(session);
        ServiceCollection services = new();
        services.AddSingleton(defaultStore.Object);
        services.AddKeyedSingleton("request-agent", otherStore.Object);
        if (registerKeyedStore)
        {
            services.AddKeyedSingleton(agent.Name, keyedStore.Object);
        }

        using ServiceProvider provider = services.BuildServiceProvider();
        var executor = new AIAgentResponseExecutor(agent, provider);
        CreateResponse request = new()
        {
            Input = "hello",
            Metadata = new Dictionary<string, string> { ["entity_id"] = "request-agent" }
        };

        // Act
        await executor.ExecuteAsync(new AgentInvocationContext(new IdGenerator("resp_1", null)), request).ToListAsync();

        // Assert
        keyedStore.Verify(s => s.GetSessionAsync(agent, "resp_1", It.IsAny<CancellationToken>()),
            registerKeyedStore ? Times.Once : Times.Never);
        defaultStore.Verify(s => s.GetSessionAsync(agent, "resp_1", It.IsAny<CancellationToken>()),
            registerKeyedStore ? Times.Never : Times.Once);
        otherStore.VerifyNoOtherCalls();
    }

    [Fact]
    public async Task ResolveSessionStore_ExistingIsolationWrapper_IsNotAppliedTwiceAsync()
    {
        // Arrange
        AIAgent agent = new ChatClientAgent(new TestHelpers.SimpleMockChatClient(), name: "agent");
        Mock<AgentSessionStore> innerStore = new();
        Mock<AgentIsolationKeyProvider> keyProvider = new();
        keyProvider.Setup(p => p.GetIsolationKeyAsync(It.IsAny<CancellationToken>())).ReturnsAsync("alice");
        AgentSession session = await agent.CreateSessionAsync();
        innerStore.Setup(s => s.GetSessionAsync(agent, "alice::resp_1", It.IsAny<CancellationToken>())).ReturnsAsync(session);
        var scopedStore = new IsolationKeyScopedAgentSessionStore(innerStore.Object, keyProvider.Object);

        // Act
        await RunAsync(agent, scopedStore, "resp_1", "hello");

        // Assert
        innerStore.Verify(s => s.GetSessionAsync(agent, "alice::resp_1", It.IsAny<CancellationToken>()), Times.Once);
        innerStore.Verify(s => s.SaveSessionAsync(agent, "alice::resp_1", session, It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task ResolveSessionStore_MissingCallerIdentity_PropagatesIsolationFailureAsync()
    {
        // Arrange
        AIAgent agent = new ChatClientAgent(new TestHelpers.SimpleMockChatClient(), name: "agent");
        Mock<AgentSessionStore> store = new();
        Mock<AgentIsolationKeyProvider> keyProvider = new();
        keyProvider.Setup(p => p.GetIsolationKeyAsync(It.IsAny<CancellationToken>())).ReturnsAsync((string?)null);
        ServiceCollection services = new();
        services.AddKeyedSingleton(agent.Name, store.Object);
        services.AddSingleton(keyProvider.Object);
        using ServiceProvider provider = services.BuildServiceProvider();
        var executor = new AIAgentResponseExecutor(agent, provider);

        // Act
        await Assert.ThrowsAsync<InvalidOperationException>(() => executor.ExecuteAsync(
            new AgentInvocationContext(new IdGenerator("resp_1", null)), new CreateResponse { Input = "hello" }).ToListAsync().AsTask());

        // Assert
        store.Verify(s => s.GetSessionAsync(It.IsAny<AIAgent>(), It.IsAny<string>(), It.IsAny<CancellationToken>()), Times.Never);
        store.Verify(s => s.SaveSessionAsync(It.IsAny<AIAgent>(), It.IsAny<string>(), It.IsAny<AgentSession>(), It.IsAny<CancellationToken>()), Times.Never);
    }

    private static async Task RunAsync(
        AIAgent agent, AgentSessionStore? store, string responseId, string input,
        string? previousResponseId = null, string? conversationId = null, IReadOnlyList<ChatMessage>? history = null)
    {
        using ServiceProvider services = CreateServices(agent, store);
        await RunAsync(new AIAgentResponseExecutor(agent, services), responseId, input, previousResponseId, conversationId, history);
    }

    private static async Task RunAsync(
        AIAgentResponseExecutor executor, string responseId, string input,
        string? previousResponseId = null, string? conversationId = null, IReadOnlyList<ChatMessage>? history = null)
    {
        CreateResponse request = new()
        {
            Input = input,
            PreviousResponseId = previousResponseId,
            Conversation = conversationId is null ? null : ConversationReference.FromId(conversationId)
        };
        List<StreamingResponseEvent> events = await executor.ExecuteAsync(
            new AgentInvocationContext(new IdGenerator(responseId, conversationId)), request, history).ToListAsync();
        Assert.IsType<StreamingResponseCompleted>(events.Last());
    }

    private static string[] UserTexts(IEnumerable<ChatMessage> messages) =>
        messages.Where(m => m.Role == ChatRole.User).Select(m => m.Text).ToArray();

    private static ServiceProvider CreateServices(AIAgent agent, AgentSessionStore? store)
    {
        ServiceCollection services = new();
        if (store is not null)
        {
            services.AddKeyedSingleton(agent.Name, store);
        }

        return services.BuildServiceProvider();
    }
}
