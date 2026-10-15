// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public sealed class WorkflowExecutorStateTests
{
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task StatefulExecutor_InitializesOnlyWhenStateIsMissingAsync(bool publish)
    {
        // Arrange
        int initializationCount = 0;
        ValueStateExecutor executor = new(() => ++initializationCount);
        TestWorkflowContext context = new(executor.Id);
        int first = await executor.ReadAsync(context, false);
        if (publish)
        {
            await context.StateManager.PublishUpdatesAsync(null);
        }

        // Act
        int second = await executor.ReadAsync(context, false);

        // Assert
        Assert.Equal(1, first);
        Assert.Equal(first, second);
        Assert.Equal(1, initializationCount);
    }

    [Fact]
    public async Task StatefulExecutor_PreservesNestedReadUpdatesDuringInitializationAsync()
    {
        // Arrange
        SessionStateExecutor executor = new(true);
        TestWorkflowContext context = new(executor.Id);

        // Act
        List<string> state = await executor.UpdateWithNestedReadAsync(context);

        // Assert
        Assert.Equal(["outer", "inner"], state);
    }

    [Fact]
    public async Task MixedWorkflow_RequiresExplicitResetSupportForReuseAsync()
    {
        // Arrange
        SessionStateExecutor executor = new(false);
        ChatForwardingExecutor forwarding = new("forward");
        Workflow workflow = new WorkflowBuilder(executor).AddEdge(executor, forwarding).Build();
        workflow.TakeOwnership("first");
        await workflow.ReleaseOwnershipAsync("first", null);

        // Act
        void reuse() => workflow.TakeOwnership("second");

        // Assert
        InvalidOperationException exception = Assert.Throws<InvalidOperationException>(reuse);
        Assert.Contains("Cannot reuse Workflow", exception.Message);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task OutputExecutor_ResetClearsMessagesAfterInterruptedTurnAsync(bool cancel)
    {
        // Arrange
        OutputMessagesExecutor executor = new(new ChatProtocolExecutorOptions { AutoSendTurnToken = false });
        TestWorkflowContext firstContext = new(executor.Id);
        using CancellationTokenSource cancellation = new();
        Mock<IWorkflowContext> interruptedContext = new();
        interruptedContext.Setup(context => context.ReadOrInitStateAsync(
                It.IsAny<string>(), It.IsAny<Func<List<ChatMessage>>>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .Returns((string key, Func<List<ChatMessage>> factory, string? scope, CancellationToken token) =>
                firstContext.ReadOrInitStateAsync(key, factory, scope, token));
        interruptedContext.Setup(context => context.YieldOutputAsync(It.IsAny<object>(), It.IsAny<CancellationToken>()))
            .Returns((object output, CancellationToken token) =>
            {
                List<ChatMessage> messages = Assert.IsType<List<ChatMessage>>(output);
                Assert.Equal(["first"], messages.Select(message => message.Text));
                if (cancel)
                {
                    cancellation.Cancel();
                    return new ValueTask(Task.FromCanceled(cancellation.Token));
                }

                return new ValueTask(Task.FromException(new InvalidOperationException("Output interrupted.")));
            });
        await executor.ExecuteCoreAsync(new ChatMessage(ChatRole.User, "first"), new TypeId(typeof(ChatMessage)), firstContext);
        if (cancel)
        {
            await Assert.ThrowsAnyAsync<OperationCanceledException>(
                () => executor.TakeTurnAsync(new TurnToken(), interruptedContext.Object, cancellation.Token).AsTask());
        }
        else
        {
            await Assert.ThrowsAsync<InvalidOperationException>(
                () => executor.TakeTurnAsync(new TurnToken(), interruptedContext.Object).AsTask());
        }

        // Act
        Assert.True(await new ExecutorInstanceBinding(executor).TryResetAsync());
        TestWorkflowContext secondContext = new(executor.Id);
        await executor.ExecuteCoreAsync(new ChatMessage(ChatRole.User, "second"), new TypeId(typeof(ChatMessage)), secondContext);
        await executor.TakeTurnAsync(new TurnToken(), secondContext);

        // Assert
        List<ChatMessage> output = Assert.IsType<List<ChatMessage>>(Assert.Single(secondContext.YieldedOutputs));
        Assert.Equal(["second"], output.Select(message => message.Text));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task StatefulExecutor_ResetReloadsValueStateAsync(bool useInvocation)
    {
        // Arrange
        ValueStateExecutor executor = new();
        TestWorkflowContext context = new(executor.Id);
        await context.QueueStateUpdateAsync("value", 7);
        Assert.Equal(7, await executor.ReadAsync(context, useInvocation));
        await context.QueueStateUpdateAsync("value", 9);

        // Act
        await ((IResettableExecutor)executor).ResetAsync();
        int restored = await executor.ReadAsync(context, useInvocation);

        // Assert
        Assert.Equal(9, restored);
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public async Task HostedStatefulExecutor_RestoresEachSessionAsync(bool useInvocation, bool streaming)
    {
        // Arrange
        SessionStateExecutor executor = new(useInvocation);
        AIAgent agent = new WorkflowBuilder(executor).Build().AsAIAgent();
        AgentSession firstSession = await agent.CreateSessionAsync();
        AgentSession secondSession = await agent.CreateSessionAsync();

        // Act
        AgentResponse first = await RunAsync("first", firstSession);
        AgentResponse second = await RunAsync("second", secondSession);
        AgentResponse resumedFirst = await RunAsync("next", firstSession);
        AgentResponse resumedSecond = await RunAsync("last", secondSession);

        // Assert
        Assert.Equal("first", first.Text);
        Assert.Equal("second", second.Text);
        Assert.Equal("first|next", resumedFirst.Text);
        Assert.Equal("second|last", resumedSecond.Text);

        async Task<AgentResponse> RunAsync(string message, AgentSession session)
        {
            return streaming
                ? await agent.RunStreamingAsync(message, session).ToAgentResponseAsync()
                : await agent.RunAsync(message, session);
        }
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task HostedChatExecutor_StartsWithNewMessagesAfterInterruptedTurnAsync(bool cancel)
    {
        // Arrange
        using CancellationTokenSource cancellation = new();
        InterruptedChatExecutor executor = new(cancel ? cancellation : null);
        AIAgent agent = new WorkflowBuilder(executor).Build().AsAIAgent();
        AgentSession firstSession = await agent.CreateSessionAsync();
        AgentSession secondSession = await agent.CreateSessionAsync();

        // Act
        AgentResponse interrupted = await agent.RunAsync("first", firstSession, cancellationToken: cancellation.Token);
        if (!cancel)
        {
            Assert.NotEmpty(interrupted.Messages.SelectMany(message => message.Contents).OfType<ErrorContent>());
        }
        Assert.Equal(cancel, cancellation.IsCancellationRequested);

        AgentResponse second = await agent.RunAsync("second", secondSession);
        AgentResponse resumedSecond = await agent.RunAsync("next", secondSession);

        // Assert
        Assert.Equal("second", second.Text);
        Assert.Equal("next", resumedSecond.Text);
    }

    private sealed class ValueStateExecutor(Func<int>? initialStateFactory = null)
        : StatefulExecutor<int>("value", initialStateFactory ?? (() => 3), new StatefulExecutorOptions { StateKey = "value" }), IResettableExecutor
    {
        protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder) => protocolBuilder;

        ValueTask IResettableExecutor.ResetAsync() => this.ResetAsync();

        public async ValueTask<int> ReadAsync(IWorkflowContext context, bool useInvocation)
        {
            if (!useInvocation)
            {
                return await this.ReadStateAsync(context);
            }

            int result = 0;
            await this.InvokeWithStateAsync((state, _, _) =>
            {
                result = state;
                return new ValueTask<int>(state);
            }, context);
            return result;
        }
    }

    private sealed class SessionStateExecutor(bool useInvocation) : StatefulExecutor<List<string>>("state", () => [])
    {
        public async ValueTask<List<string>> UpdateWithNestedReadAsync(IWorkflowContext context)
        {
            await this.InvokeWithStateAsync(async (state, ctx, cancellationToken) =>
            {
                state.Add("outer");
                List<string> nestedState = await this.ReadStateAsync(ctx, cancellationToken: cancellationToken);
                nestedState.Add("inner");
                return state;
            }, context);

            return await this.ReadStateAsync(context);
        }

        protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
        {
            return protocolBuilder.ConfigureRoutes(routes => routes
                .AddHandler<IEnumerable<ChatMessage>>(this.AddMessagesAsync)
                .AddHandler<TurnToken>(this.TakeTurnAsync));
        }

        private async ValueTask AddMessagesAsync(IEnumerable<ChatMessage> messages, IWorkflowContext context, CancellationToken cancellationToken)
        {
            if (useInvocation)
            {
                await this.InvokeWithStateAsync((state, _, _) =>
                {
                    state.AddRange(messages.Select(message => message.Text));
                    return new ValueTask<List<string>?>(state);
                }, context, cancellationToken: cancellationToken);
            }
            else
            {
                List<string> state = await this.ReadStateAsync(context, cancellationToken: cancellationToken);
                state.AddRange(messages.Select(message => message.Text));
                await this.QueueStateUpdateAsync(state, context, cancellationToken);
            }
        }

        private async ValueTask TakeTurnAsync(TurnToken token, IWorkflowContext context, CancellationToken cancellationToken)
        {
            List<string> state = await this.ReadStateAsync(context, cancellationToken: cancellationToken);
            await context.AddEventAsync(new AgentResponseUpdateEvent(this.Id,
                new AgentResponseUpdate(ChatRole.Assistant, string.Join("|", state))), cancellationToken);
        }
    }

    private sealed class InterruptedChatExecutor(CancellationTokenSource? cancellation)
        : ChatProtocolExecutor("chat", new ChatProtocolExecutorOptions { AutoSendTurnToken = false })
    {
        private bool _interruptNextTurn = true;

        protected override async ValueTask TakeTurnAsync(
            List<ChatMessage> messages, IWorkflowContext context, bool? emitEvents, CancellationToken cancellationToken = default)
        {
            if (this._interruptNextTurn)
            {
                this._interruptNextTurn = false;
                if (cancellation is not null)
                {
                    cancellation.Cancel();
                    cancellationToken.ThrowIfCancellationRequested();
                }

                throw new InvalidOperationException("Turn interrupted.");
            }

            await context.AddEventAsync(new AgentResponseUpdateEvent(this.Id,
                new AgentResponseUpdate(ChatRole.Assistant, string.Join("|", messages.Select(message => message.Text)))),
                cancellationToken);
        }
    }
}
