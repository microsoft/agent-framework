// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Contains tests for the <see cref="ProviderSessionState{TState}"/> class.
/// </summary>
public class ProviderSessionStateTests
{
    #region GetOrInitializeState Tests

    [Fact]
    public void GetOrInitializeState_InitializesFromStateInitializerOnFirstCall()
    {
        // Arrange
        var expectedState = new TestState { Value = "initialized" };
        var sessionState = new ProviderSessionState<TestState>(_ => expectedState, "test-key");
        var session = new TestAgentSession();

        // Act
        var state = sessionState.GetOrInitializeState(session);

        // Assert
        Assert.Same(expectedState, state);
    }

    [Fact]
    public void GetOrInitializeState_ReturnsCachedStateFromStateBagOnSecondCall()
    {
        // Arrange
        var callCount = 0;
        var sessionState = new ProviderSessionState<TestState>(_ =>
        {
            callCount++;
            return new TestState { Value = $"init-{callCount}" };
        }, "test-key");
        var session = new TestAgentSession();

        // Act
        var state1 = sessionState.GetOrInitializeState(session);
        var state2 = sessionState.GetOrInitializeState(session);

        // Assert - initializer called only once; second call reads from StateBag
        Assert.Equal(1, callCount);
        Assert.Equal("init-1", state1.Value);
        Assert.Equal("init-1", state2.Value);
    }

    [Fact]
    public void GetOrInitializeState_WorksWhenSessionIsNull()
    {
        // Arrange
        var sessionState = new ProviderSessionState<TestState>(_ => new TestState { Value = "no-session" }, "test-key");

        // Act
        var state = sessionState.GetOrInitializeState(null);

        // Assert
        Assert.Equal("no-session", state.Value);
    }

    [Fact]
    public void GetOrInitializeState_ReInitializesWhenSessionIsNull()
    {
        // Arrange - without a session, state can't be cached in StateBag
        var callCount = 0;
        var sessionState = new ProviderSessionState<TestState>(_ =>
        {
            callCount++;
            return new TestState { Value = $"init-{callCount}" };
        }, "test-key");

        // Act
        sessionState.GetOrInitializeState(null);
        sessionState.GetOrInitializeState(null);

        // Assert - initializer called each time since there's no session to cache in
        Assert.Equal(2, callCount);
    }

    #endregion

    #region SaveState Tests

    [Fact]
    public void SaveState_SavesToStateBag()
    {
        // Arrange
        var sessionState = new ProviderSessionState<TestState>(_ => new TestState(), "test-key");
        var session = new TestAgentSession();
        var state = new TestState { Value = "saved" };

        // Act
        sessionState.SaveState(session, state);
        var retrieved = sessionState.GetOrInitializeState(session);

        // Assert
        Assert.Equal("saved", retrieved.Value);
    }

    [Fact]
    public void SaveState_NoOpWhenSessionIsNull()
    {
        // Arrange
        var sessionState = new ProviderSessionState<TestState>(_ => new TestState { Value = "default" }, "test-key");

        // Act - should not throw
        sessionState.SaveState(null, new TestState { Value = "saved" });

        // Assert - no exception; can't verify further without a session
    }

    #endregion

    #region StateKey Tests

    [Fact]
    public void StateKey_UsesProvidedKey()
    {
        // Arrange
        var sessionState = new ProviderSessionState<TestState>(_ => new TestState(), "my-provider-key");

        // Act & Assert
        Assert.Equal("my-provider-key", sessionState.StateKey);
    }

    [Fact]
    public void StateKey_UsesCustomKeyWhenProvided()
    {
        // Arrange
        var sessionState = new ProviderSessionState<TestState>(_ => new TestState(), "custom-key");

        // Act & Assert
        Assert.Equal("custom-key", sessionState.StateKey);
    }

    #endregion

    #region Isolation Tests

    [Fact]
    public void GetOrInitializeState_IsolatesStateBetweenDifferentKeys()
    {
        // Arrange
        var sessionState1 = new ProviderSessionState<TestState>(_ => new TestState { Value = "state-1" }, "key-1");
        var sessionState2 = new ProviderSessionState<TestState>(_ => new TestState { Value = "state-2" }, "key-2");
        var session = new TestAgentSession();

        // Act
        var state1 = sessionState1.GetOrInitializeState(session);
        var state2 = sessionState2.GetOrInitializeState(session);

        // Assert - each key maintains independent state
        Assert.Equal("state-1", state1.Value);
        Assert.Equal("state-2", state2.Value);
    }

    [Fact]
    public void GetOrInitializeState_IsolatesStateBetweenDifferentSessions()
    {
        // Arrange
        var callCount = 0;
        var sessionState = new ProviderSessionState<TestState>(_ =>
        {
            callCount++;
            return new TestState { Value = $"init-{callCount}" };
        }, "test-key");
        var session1 = new TestAgentSession();
        var session2 = new TestAgentSession();

        // Act
        var state1 = sessionState.GetOrInitializeState(session1);
        var state2 = sessionState.GetOrInitializeState(session2);

        // Assert - each session gets its own state
        Assert.Equal(2, callCount);
        Assert.Equal("init-1", state1.Value);
        Assert.Equal("init-2", state2.Value);
    }

    #endregion

    public sealed class TestState
    {
        public string Value { get; set; } = string.Empty;
    }

    private sealed class TestAgentSession : AgentSession;
}
