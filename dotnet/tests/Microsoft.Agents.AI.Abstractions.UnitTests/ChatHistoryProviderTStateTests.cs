// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Contains tests for the <see cref="ChatHistoryProvider{TState}"/> class.
/// </summary>
public class ChatHistoryProviderTStateTests
{
    private static readonly AIAgent s_mockAgent = new Mock<AIAgent>().Object;

    #region GetOrInitializeState Tests

    [Fact]
    public void GetOrInitializeState_InitializesFromStateInitializerOnFirstCall()
    {
        // Arrange
        var expectedState = new TestState { Value = "initialized" };
        var provider = new TestChatHistoryProvider(_ => expectedState);
        var session = new TestAgentSession();

        // Act
        var state = provider.GetState(session);

        // Assert
        Assert.Same(expectedState, state);
    }

    [Fact]
    public void GetOrInitializeState_ReturnsCachedStateFromStateBagOnSecondCall()
    {
        // Arrange
        var callCount = 0;
        var provider = new TestChatHistoryProvider(_ =>
        {
            callCount++;
            return new TestState { Value = $"init-{callCount}" };
        });
        var session = new TestAgentSession();

        // Act
        var state1 = provider.GetState(session);
        var state2 = provider.GetState(session);

        // Assert - initializer called only once; second call reads from StateBag
        Assert.Equal(1, callCount);
        Assert.Equal("init-1", state1.Value);
        Assert.Equal("init-1", state2.Value);
    }

    [Fact]
    public void GetOrInitializeState_WorksWhenSessionIsNull()
    {
        // Arrange
        var provider = new TestChatHistoryProvider(_ => new TestState { Value = "no-session" });

        // Act
        var state = provider.GetState(null);

        // Assert
        Assert.Equal("no-session", state.Value);
    }

    [Fact]
    public void GetOrInitializeState_ReInitializesWhenSessionIsNull()
    {
        // Arrange - without a session, state can't be cached in StateBag
        var callCount = 0;
        var provider = new TestChatHistoryProvider(_ =>
        {
            callCount++;
            return new TestState { Value = $"init-{callCount}" };
        });

        // Act
        _ = provider.GetState(null);
        provider.GetState(null);

        // Assert - initializer called each time since there's no session to cache in
        Assert.Equal(2, callCount);
    }

    #endregion

    #region SaveState Tests

    [Fact]
    public void SaveState_SavesToStateBag()
    {
        // Arrange
        var provider = new TestChatHistoryProvider(_ => new TestState());
        var session = new TestAgentSession();
        var state = new TestState { Value = "saved" };

        // Act
        provider.DoSaveState(session, state);
        var retrieved = provider.GetState(session);

        // Assert
        Assert.Equal("saved", retrieved.Value);
    }

    [Fact]
    public void SaveState_NoOpWhenSessionIsNull()
    {
        // Arrange
        var provider = new TestChatHistoryProvider(_ => new TestState { Value = "default" });

        // Act - should not throw
        provider.DoSaveState(null, new TestState { Value = "saved" });

        // Assert - no exception; can't verify further without a session
    }

    #endregion

    #region StateKey Tests

    [Fact]
    public void StateKey_DefaultsToTypeName()
    {
        // Arrange
        var provider = new TestChatHistoryProvider(_ => new TestState());

        // Act & Assert
        Assert.Equal(nameof(TestChatHistoryProvider), provider.StateKey);
    }

    [Fact]
    public void StateKey_UsesCustomKeyWhenProvided()
    {
        // Arrange
        var provider = new TestChatHistoryProvider(_ => new TestState(), stateKey: "custom-key");

        // Act & Assert
        Assert.Equal("custom-key", provider.StateKey);
    }

    #endregion

    #region Integration Tests

    [Fact]
    public async Task InvokingCoreAsync_CanUseStateInProvideChatHistoryAsync()
    {
        // Arrange
        var provider = new TestChatHistoryProvider(_ => new TestState { Value = "state-value" });
        var session = new TestAgentSession();
        var context = new ChatHistoryProvider.InvokingContext(s_mockAgent, session, [new ChatMessage(ChatRole.User, "Hi")]);

        // Act
        var result = (await provider.InvokingAsync(context)).ToList();

        // Assert - the provider uses state to produce history messages
        Assert.Equal(2, result.Count);
        Assert.Contains("state-value", result[0].Text);
    }

    #endregion

    public sealed class TestState
    {
        public string Value { get; set; } = string.Empty;
    }

    private sealed class TestChatHistoryProvider : ChatHistoryProvider<TestState>
    {
        public TestChatHistoryProvider(
            Func<AgentSession?, TestState> stateInitializer,
            string? stateKey = null)
            : base(stateInitializer, stateKey, null, null, null)
        {
        }

        public TestState GetState(AgentSession? session) => this.GetOrInitializeState(session);

        public void DoSaveState(AgentSession? session, TestState state) => this.SaveState(session, state);

        protected override ValueTask<IEnumerable<ChatMessage>> ProvideChatHistoryAsync(InvokingContext context, CancellationToken cancellationToken = default)
        {
            var state = this.GetOrInitializeState(context.Session);
            return new(new[] { new ChatMessage(ChatRole.System, $"History from state: {state.Value}") });
        }
    }

    private sealed class TestAgentSession : AgentSession;
}
