// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class WorkflowHostAgentChatHistoryProviderTests
{
    private static Workflow CreateWorkflow() => AgentWorkflowBuilder.BuildSequential(new TestEchoAgent("echo", "Echo"));

    private static Task<AgentResponse> RunAgentAsync(AIAgent agent, string input, AgentSession session, bool streaming)
        => streaming
            ? agent.RunStreamingAsync(input, session).ToAgentResponseAsync()
            : agent.RunAsync(input, session);

    [Fact]
    public void AsAIAgent_WithNullOptions_Throws()
    {
        // Arrange
        Workflow workflow = CreateWorkflow();

        // Act & Assert
        Assert.Throws<ArgumentNullException>("options", () => workflow.AsAIAgent(options: null!));
    }

    [Fact]
    public void AsAIAgent_WithOptions_AppliesAgentMetadata()
    {
        // Arrange
        InMemoryChatHistoryProvider provider = new();

        // Act
        AIAgent agent = CreateWorkflow().AsAIAgent(new WorkflowAgentOptions
        {
            Id = "workflow-agent",
            Name = "WorkflowAgent",
            Description = "A workflow agent",
            ChatHistoryProvider = provider,
        });

        // Assert
        Assert.Equal("workflow-agent", agent.Id);
        Assert.Equal("WorkflowAgent", agent.Name);
        Assert.Equal("A workflow agent", agent.Description);
        Assert.Same(provider, agent.GetService<ChatHistoryProvider>());
        Assert.Same(provider, agent.GetService<InMemoryChatHistoryProvider>());
    }

    [Fact]
    public void AsAIAgent_WithOptions_IsNotAffectedByLaterOptionChanges()
    {
        // Arrange
        InMemoryChatHistoryProvider provider = new();
        WorkflowAgentOptions options = new() { Name = "Original", ChatHistoryProvider = provider };
        AIAgent agent = CreateWorkflow().AsAIAgent(options);

        // Act
        options.Name = "Changed";
        options.ChatHistoryProvider = null;

        // Assert
        Assert.Equal("Original", agent.Name);
        Assert.Same(provider, agent.GetService<ChatHistoryProvider>());
    }

    [Fact]
    public async Task AsAIAgent_WithChatHistoryProviderParameter_UsesProviderAsync()
    {
        // Arrange
        InMemoryChatHistoryProvider provider = new();
        AIAgent agent = CreateWorkflow().AsAIAgent("workflow-agent", "WorkflowAgent", chatHistoryProvider: provider);
        AgentSession session = await agent.CreateSessionAsync();

        // Act
        await agent.RunAsync("Hello", session);

        // Assert
        Assert.Equal("workflow-agent", agent.Id);
        Assert.Equal("WorkflowAgent", agent.Name);
        Assert.Same(provider, agent.GetService<ChatHistoryProvider>());
        (ChatRole, string)[] expected = [(ChatRole.User, "Hello"), (ChatRole.Assistant, "Hello")];
        Assert.Equal(expected, provider.GetMessages(session).Select(m => (m.Role, m.Text)));
    }

    [Fact]
    public void AsAIAgent_WithoutCustomProvider_DoesNotExposeChatHistoryProvider()
    {
        // Arrange & Act
        AIAgent agent = CreateWorkflow().AsAIAgent(new WorkflowAgentOptions());

        // Assert
        Assert.Null(agent.GetService<ChatHistoryProvider>());
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task RunAsync_WithCustomProvider_StoresRequestAndResponseMessagesAsync(bool streaming)
    {
        // Arrange
        InMemoryChatHistoryProvider provider = new();
        AIAgent agent = CreateWorkflow().AsAIAgent(new WorkflowAgentOptions { ChatHistoryProvider = provider });
        AgentSession session = await agent.CreateSessionAsync();

        // Act
        await RunAgentAsync(agent, "Hello", session, streaming);
        await RunAgentAsync(agent, "World", session, streaming);

        // Assert
        (ChatRole, string)[] expected =
        [
            (ChatRole.User, "Hello"),
            (ChatRole.Assistant, "Hello"),
            (ChatRole.User, "World"),
            (ChatRole.Assistant, "World"),
        ];
        Assert.Equal(expected, provider.GetMessages(session).Select(m => (m.Role, m.Text)));

        // The default workflow provider should not be used when a custom provider is configured.
        WorkflowSession workflowSession = Assert.IsType<WorkflowSession>(session);
        Assert.Empty(workflowSession.ChatHistoryProvider.GetAllMessages(workflowSession));
    }

    [Fact]
    public async Task RunAsync_WithCustomProvider_AppliesProviderOptionsAsync()
    {
        // Arrange
        InMemoryChatHistoryProvider provider = new(new InMemoryChatHistoryProviderOptions
        {
            StorageInputResponseMessageFilter = _ => [],
        });
        AIAgent agent = CreateWorkflow().AsAIAgent(new WorkflowAgentOptions { ChatHistoryProvider = provider });
        AgentSession session = await agent.CreateSessionAsync();

        // Act
        await agent.RunAsync("Hello", session);

        // Assert
        ChatMessage message = Assert.Single(provider.GetMessages(session));
        Assert.Equal(ChatRole.User, message.Role);
        Assert.Equal("Hello", message.Text);
    }

    [Fact]
    public async Task SerializeSession_WithCustomProvider_RoundTripsHistoryAsync()
    {
        // Arrange
        InMemoryChatHistoryProvider provider = new();
        AIAgent agent = CreateWorkflow().AsAIAgent(new WorkflowAgentOptions { ChatHistoryProvider = provider });
        AgentSession session = await agent.CreateSessionAsync();
        await agent.RunAsync("Hello", session);

        // Act
        JsonElement serialized = await agent.SerializeSessionAsync(session);
        AgentSession restored = await agent.DeserializeSessionAsync(serialized);
        await agent.RunAsync("World", restored);

        // Assert
        (ChatRole, string)[] expected =
        [
            (ChatRole.User, "Hello"),
            (ChatRole.Assistant, "Hello"),
            (ChatRole.User, "World"),
            (ChatRole.Assistant, "World"),
        ];
        Assert.Equal(expected, provider.GetMessages(restored).Select(m => (m.Role, m.Text)));
    }

    [Fact]
    public async Task WithCheckpointing_PreservesCustomProviderAsync()
    {
        // Arrange
        InMemoryChatHistoryProvider provider = new();
        AIAgent agent = CreateWorkflow().AsAIAgent(new WorkflowAgentOptions { ChatHistoryProvider = provider });

        // Act
        AIAgent redirected = agent.WithCheckpointing(CheckpointManager.CreateInMemory());
        AgentSession session = await redirected.CreateSessionAsync();
        await redirected.RunAsync("Hello", session);

        // Assert
        Assert.NotSame(agent, redirected);
        Assert.Same(provider, redirected.GetService<ChatHistoryProvider>());
        Assert.Contains(provider.GetMessages(session), m => m.Role == ChatRole.User && m.Text == "Hello");
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task RunAsync_WhenWorkflowRunFails_NotifiesProviderWithExceptionAsync(bool streaming)
    {
        // Arrange
        RecordingChatHistoryProvider provider = new();
        AIAgent agent = CreateWorkflow().AsAIAgent(new WorkflowAgentOptions { ChatHistoryProvider = provider });
        AgentSession session = await agent.CreateSessionAsync();

        // Resuming from a checkpoint that does not exist makes the workflow run throw.
        WorkflowSessionCheckpointRecovery recovery = session.GetService<WorkflowSessionCheckpointRecovery>()!;
        Assert.True(recovery.TryPrepare("missing-checkpoint"));

        // Act
        Exception exception = await Assert.ThrowsAnyAsync<Exception>(() => RunAgentAsync(agent, "Hello", session, streaming));

        // Assert
        ChatHistoryProvider.InvokedContext context = Assert.Single(provider.InvokedContexts);
        Assert.Same(exception, context.InvokeException);
        Assert.Same(agent, context.Agent);
        Assert.Same(session, context.Session);
        Assert.Null(context.ResponseMessages);
        ChatMessage requestMessage = Assert.Single(context.RequestMessages);
        Assert.Equal(ChatRole.User, requestMessage.Role);
        Assert.Equal("Hello", requestMessage.Text);
    }

    private sealed class RecordingChatHistoryProvider : ChatHistoryProvider
    {
        public List<InvokedContext> InvokedContexts { get; } = [];

        protected override ValueTask InvokedCoreAsync(InvokedContext context, CancellationToken cancellationToken = default)
        {
            this.InvokedContexts.Add(context);
            return default;
        }
    }
}
