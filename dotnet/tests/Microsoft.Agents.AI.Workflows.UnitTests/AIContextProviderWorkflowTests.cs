// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

/// <summary>
/// Validates that messages injected by <see cref="AIContextProvider"/> into an inner agent
/// are correctly persisted into the workflow's chat history, without leaking to downstream agents.
/// </summary>
public class AIContextProviderWorkflowTests
{
    private const string UserText = "Where is Taggia?";
    private const string ContextText = "Taggia is a city in Liguria.";
    private const string FirstAgentResponseText = "Taggia is in Liguria.";

    /// <summary>
    /// Ensures that AIContextProvider-injected messages appear in the workflow session's
    /// chat history and survive serialization (regression test for the bug where such
    /// messages were lost because WorkflowHostAgent only persisted model outputs).
    /// </summary>
    [Fact]
    public async Task Test_WorkflowAsAgent_SerializesAIContextProviderRequestMessagesAsync()
    {
        // Arrange
        ChatClientAgent innerAgent = CreateContextAwareAgent();
        AIAgent workflowAgent = AgentWorkflowBuilder.BuildSequential(innerAgent).AsAIAgent();
        AgentSession session = await workflowAgent.CreateSessionAsync();

        // Act
        await workflowAgent.RunAsync(new ChatMessage(ChatRole.User, UserText), session);
        JsonElement serializedSession = await workflowAgent.SerializeSessionAsync(session);

        // Assert
        WorkflowSession workflowSession = session.Should().BeOfType<WorkflowSession>().Subject;
        string[] historyTexts =
        [
            .. workflowSession.ChatHistoryProvider
                .GetAllMessages(workflowSession)
                .Select(message => message.Text)
        ];

        historyTexts.Should().Contain(UserText);
        historyTexts.Should().Contain(ContextText);
        historyTexts.Should().Contain(FirstAgentResponseText);
        serializedSession.GetRawText().Should().Contain(ContextText);
    }

    /// <summary>
    /// Ensures that AIContextProvider-injected messages are still persisted when inner chat history is pruned.
    /// </summary>
    [Fact]
    public async Task Test_WorkflowAsAgent_SerializesAIContextProviderRequestMessagesWhenInnerHistoryIsPrunedAsync()
    {
        // Arrange
        RetainingChatHistoryProvider chatHistoryProvider = new(maxStoredMessages: 2);
        chatHistoryProvider.Add(new ChatMessage(ChatRole.User, "Previous question") { MessageId = "previous-user" });
        chatHistoryProvider.Add(new ChatMessage(ChatRole.Assistant, "Previous answer") { MessageId = "previous-assistant" });
        ChatClientAgent innerAgent = CreateContextAwareAgent(chatHistoryProvider);
        AIAgent workflowAgent = AgentWorkflowBuilder.BuildSequential(innerAgent).AsAIAgent();
        AgentSession session = await workflowAgent.CreateSessionAsync();

        // Act
        await workflowAgent.RunAsync(new ChatMessage(ChatRole.User, UserText), session);

        // Assert
        WorkflowSession workflowSession = session.Should().BeOfType<WorkflowSession>().Subject;
        workflowSession.ChatHistoryProvider
            .GetAllMessages(workflowSession)
            .Select(message => message.Text)
            .Should()
            .Contain(ContextText);
    }

    /// <summary>
    /// Ensures that AIContextProvider-injected messages are saved to workflow history
    /// but are NOT forwarded as part of the input to subsequent agents in the workflow.
    /// </summary>
    [Fact]
    public async Task Test_WorkflowAsAgent_DoesNotForwardAIContextProviderRequestMessagesToDownstreamAgentAsync()
    {
        // Arrange
        ChatClientAgent innerAgent = CreateContextAwareAgent();
        RecordingEchoAgent downstreamAgent = new(id: "downstream", name: "downstream", prefix: "downstream:");
        AIAgent workflowAgent = AgentWorkflowBuilder.BuildSequential(innerAgent, downstreamAgent).AsAIAgent();

        // Act
        await workflowAgent.RunAsync(new ChatMessage(ChatRole.User, UserText), await workflowAgent.CreateSessionAsync());

        // Assert
        downstreamAgent.RecordedInputs.Should().ContainSingle();
        string[] downstreamTexts = [.. downstreamAgent.RecordedInputs[0].Select(message => message.Text)];
        downstreamTexts.Should().Contain(FirstAgentResponseText);
        downstreamTexts.Should().NotContain(ContextText);
    }

    /// <summary>Builds an agent whose IChatClient always replies with <see cref="FirstAgentResponseText"/>, prepopulated with a <see cref="StaticAIContextProvider"/>.</summary>
    private static ChatClientAgent CreateContextAwareAgent(ChatHistoryProvider? chatHistoryProvider = null)
    {
        return new ChatClientAgent(
            new StubChatClient(_ => new ChatResponse([new ChatMessage(ChatRole.Assistant, FirstAgentResponseText)])),
            new ChatClientAgentOptions
            {
                Name = "inner",
                ChatHistoryProvider = chatHistoryProvider,
                AIContextProviders = [new StaticAIContextProvider(ContextText)]
            });
    }

    /// <summary>Always injects a single System message containing the configured text.</summary>
    private sealed class StaticAIContextProvider(string text) : AIContextProvider
    {
        protected override ValueTask<AIContext> ProvideAIContextAsync(InvokingContext context, CancellationToken cancellationToken = default)
        {
            return new(new AIContext
            {
                Messages = [new ChatMessage(ChatRole.System, text)]
            });
        }
    }

    private sealed class RetainingChatHistoryProvider(int maxStoredMessages) : ChatHistoryProvider
    {
        private readonly List<ChatMessage> _messages = [];

        public void Add(ChatMessage message)
        {
            this._messages.Add(message);
        }

        protected override ValueTask<IEnumerable<ChatMessage>> InvokingCoreAsync(InvokingContext context, CancellationToken cancellationToken = default)
        {
            return new(this._messages.Concat(context.RequestMessages));
        }

        protected override ValueTask StoreChatHistoryAsync(InvokedContext context, CancellationToken cancellationToken = default)
        {
            this._messages.AddRange(context.RequestMessages);
            if (context.ResponseMessages is not null)
            {
                this._messages.AddRange(context.ResponseMessages);
            }

            if (this._messages.Count > maxStoredMessages)
            {
                this._messages.RemoveRange(0, this._messages.Count - maxStoredMessages);
            }

            return default;
        }
    }

    /// <summary>Test double for <see cref="IChatClient"/> that returns deterministic responses via the supplied factory.</summary>
    private sealed class StubChatClient(Func<IEnumerable<ChatMessage>, ChatResponse> responseFactory) : IChatClient
    {
        public Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
            => Task.FromResult(responseFactory(messages));

        public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
            IEnumerable<ChatMessage> messages,
            ChatOptions? options = null,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            ChatResponse response = await this.GetResponseAsync(messages, options, cancellationToken).ConfigureAwait(false);
            foreach (ChatResponseUpdate update in response.ToChatResponseUpdates())
            {
                yield return update;
            }
        }

        public object? GetService(Type serviceType, object? serviceKey = null) => null;

        public void Dispose()
        {
        }
    }
}
