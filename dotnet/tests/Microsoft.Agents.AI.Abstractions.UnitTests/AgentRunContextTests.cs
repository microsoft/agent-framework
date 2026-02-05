// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Unit tests for the <see cref="AgentRunContext"/> class.
/// </summary>
public sealed class AgentRunContextTests
{
    #region Constructor Validation Tests

    /// <summary>
    /// Verifies that passing null for agent throws ArgumentNullException.
    /// </summary>
    [Fact]
    public void Constructor_NullAgent_ThrowsArgumentNullException()
    {
        // Arrange
        AgentSession session = new TestAgentSession();
        IReadOnlyCollection<ChatMessage> messages = new List<ChatMessage>();
        AgentRunOptions options = new();

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new AgentRunContext(null!, session, messages, options));
    }

    /// <summary>
    /// Verifies that passing null for session does not throw
    /// </summary>
    [Fact]
    public void Constructor_NullSession_DoesNotThrow()
    {
        // Arrange
        AIAgent agent = new TestAgent();
        IReadOnlyCollection<ChatMessage> messages = new List<ChatMessage>();
        AgentRunOptions options = new();

        // Act
        AgentRunContext context = new(agent, null, messages, options);

        // Assert
        Assert.NotNull(context);
        Assert.Null(context.Session);
    }

    /// <summary>
    /// Verifies that passing null for requestMessages throws ArgumentNullException.
    /// </summary>
    [Fact]
    public void Constructor_NullRequestMessages_ThrowsArgumentNullException()
    {
        // Arrange
        AIAgent agent = new TestAgent();
        AgentSession session = new TestAgentSession();
        AgentRunOptions options = new();

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new AgentRunContext(agent, session, null!, options));
    }

    /// <summary>
    /// Verifies that passing null for agentRunOptions does not throw.
    /// </summary>
    [Fact]
    public void Constructor_NullAgentRunOptions_DoesNotThrow()
    {
        // Arrange
        AIAgent agent = new TestAgent();
        AgentSession session = new TestAgentSession();
        IReadOnlyCollection<ChatMessage> messages = new List<ChatMessage>();

        // Act
        AgentRunContext context = new(agent, session, messages, null);

        // Assert
        Assert.NotNull(context);
        Assert.Null(context.RunOptions);
    }

    #endregion

    #region Property Roundtrip Tests

    /// <summary>
    /// Verifies that the Agent property returns the value passed to the constructor.
    /// </summary>
    [Fact]
    public void Agent_ReturnsValueFromConstructor()
    {
        // Arrange
        AIAgent agent = new TestAgent();
        AgentSession session = new TestAgentSession();
        IReadOnlyCollection<ChatMessage> messages = new List<ChatMessage>();
        AgentRunOptions options = new();

        // Act
        AgentRunContext context = new(agent, session, messages, options);

        // Assert
        Assert.Same(agent, context.Agent);
    }

    /// <summary>
    /// Verifies that the Session property returns the value passed to the constructor.
    /// </summary>
    [Fact]
    public void Session_ReturnsValueFromConstructor()
    {
        // Arrange
        AIAgent agent = new TestAgent();
        AgentSession session = new TestAgentSession();
        IReadOnlyCollection<ChatMessage> messages = new List<ChatMessage>();
        AgentRunOptions options = new();

        // Act
        AgentRunContext context = new(agent, session, messages, options);

        // Assert
        Assert.Same(session, context.Session);
    }

    /// <summary>
    /// Verifies that the RequestMessages property returns the value passed to the constructor.
    /// </summary>
    [Fact]
    public void RequestMessages_ReturnsValueFromConstructor()
    {
        // Arrange
        AIAgent agent = new TestAgent();
        AgentSession session = new TestAgentSession();
        IReadOnlyCollection<ChatMessage> messages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "Hi there!")
        };
        AgentRunOptions options = new();

        // Act
        AgentRunContext context = new(agent, session, messages, options);

        // Assert
        Assert.Same(messages, context.RequestMessages);
        Assert.Equal(2, context.RequestMessages.Count);
    }

    /// <summary>
    /// Verifies that the RunOptions property returns the value passed to the constructor.
    /// </summary>
    [Fact]
    public void RunOptions_ReturnsValueFromConstructor()
    {
        // Arrange
        AIAgent agent = new TestAgent();
        AgentSession session = new TestAgentSession();
        IReadOnlyCollection<ChatMessage> messages = new List<ChatMessage>();
        AgentRunOptions options = new()
        {
            AllowBackgroundResponses = true,
            AdditionalProperties = new AdditionalPropertiesDictionary
            {
                ["key1"] = "value1"
            }
        };

        // Act
        AgentRunContext context = new(agent, session, messages, options);

        // Assert
        Assert.Same(options, context.RunOptions);
        Assert.True(context.RunOptions!.AllowBackgroundResponses);
    }

    /// <summary>
    /// Verifies that an empty messages collection is handled correctly.
    /// </summary>
    [Fact]
    public void RequestMessages_EmptyCollection_ReturnsEmptyCollection()
    {
        // Arrange
        AIAgent agent = new TestAgent();
        AgentSession session = new TestAgentSession();
        IReadOnlyCollection<ChatMessage> messages = new List<ChatMessage>();
        AgentRunOptions options = new();

        // Act
        AgentRunContext context = new(agent, session, messages, options);

        // Assert
        Assert.NotNull(context.RequestMessages);
        Assert.Empty(context.RequestMessages);
    }

    #endregion

    #region Test Helpers

    private sealed class TestAgentSession : AgentSession;

    private sealed class TestAgent : AIAgent
    {
        public override ValueTask<AgentSession> CreateSessionAsync(CancellationToken cancellationToken = default)
            => throw new NotImplementedException();

        public override ValueTask<AgentSession> DeserializeSessionAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
            => throw new NotImplementedException();

        public override JsonElement SerializeSession(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null)
            => throw new NotImplementedException();

        protected override Task<AgentResponse> RunCoreAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();

        protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();
    }

    #endregion
}
