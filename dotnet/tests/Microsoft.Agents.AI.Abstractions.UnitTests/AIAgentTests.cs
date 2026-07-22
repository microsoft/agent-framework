// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;
using Moq.Protected;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Unit tests for the <see cref="AIAgent"/> class.
/// </summary>
public class AIAgentTests
{
    private readonly Mock<AIAgent> _agentMock;
    private readonly Mock<AgentSession> _agentSessionMock;
    private readonly AgentResponse _invokeResponse;
    private readonly List<AgentResponseUpdate> _invokeStreamingResponses = [];

    /// <summary>
    /// Initializes a new instance of the <see cref="AIAgentTests"/> class.
    /// </summary>
    public AIAgentTests()
    {
        this._agentSessionMock = new Mock<AgentSession>(MockBehavior.Strict);

        this._invokeResponse = new AgentResponse(new ChatMessage(ChatRole.Assistant, "Hi"));
        this._invokeStreamingResponses.Add(new AgentResponseUpdate(ChatRole.Assistant, "Hi"));

        this._agentMock = new Mock<AIAgent> { CallBase = true };
        this._agentMock
            .Protected()
            .Setup<Task<AgentResponse>>("RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.Is<AgentSession?>(t => t == this._agentSessionMock.Object),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(this._invokeResponse);
        this._agentMock
            .Protected()
            .Setup<IAsyncEnumerable<AgentResponseUpdate>>("RunCoreStreamingAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.Is<AgentSession?>(t => t == this._agentSessionMock.Object),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .Returns(ToAsyncEnumerableAsync(this._invokeStreamingResponses));
    }

    /// <summary>
    /// Tests that invoking without a message calls the mocked invoke method with an empty array.
    /// </summary>
    /// <returns>A task that represents the asynchronous operation.</returns>
    [Fact]
    public async Task InvokeWithoutMessageCallsMockedInvokeWithEmptyArrayAsync()
    {
        // Arrange
        var options = new AgentRunOptions();
        var cancellationToken = default(CancellationToken);

        // Act
        var response = await this._agentMock.Object.RunAsync(this._agentSessionMock.Object, options, cancellationToken);
        Assert.Equal(this._invokeResponse, response);

        // Verify that the mocked method was called with the expected parameters
        this._agentMock
            .Protected()
            .Verify<Task<AgentResponse>>("RunCoreAsync",
                Times.Once(),
                ItExpr.Is<IEnumerable<ChatMessage>>(messages => !messages.Any()),
                ItExpr.Is<AgentSession?>(t => t == this._agentSessionMock.Object),
                ItExpr.Is<AgentRunOptions?>(o => o == options),
                ItExpr.Is<CancellationToken>(ct => ct == cancellationToken));
    }

    /// <summary>
    /// Tests that invoking with a string message calls the mocked invoke method with the message in the ICollection of messages.
    /// </summary>
    /// <returns>A task that represents the asynchronous operation.</returns>
    [Fact]
    public async Task InvokeWithStringMessageCallsMockedInvokeWithMessageInCollectionAsync()
    {
        // Arrange
        const string Message = "Hello, Agent!";
        var options = new AgentRunOptions();
        var cancellationToken = default(CancellationToken);

        // Act
        var response = await this._agentMock.Object.RunAsync(Message, this._agentSessionMock.Object, options, cancellationToken);
        Assert.Equal(this._invokeResponse, response);

        // Verify that the mocked method was called with the expected parameters
        this._agentMock
            .Protected()
            .Verify<Task<AgentResponse>>("RunCoreAsync",
                Times.Once(),
                ItExpr.Is<IEnumerable<ChatMessage>>(messages => messages.Count() == 1 && messages.First().Text == Message),
                ItExpr.Is<AgentSession?>(t => t == this._agentSessionMock.Object),
                ItExpr.Is<AgentRunOptions?>(o => o == options),
                ItExpr.Is<CancellationToken>(ct => ct == cancellationToken));
    }

    /// <summary>
    /// Tests that invoking with a single message calls the mocked invoke method with the message in the ICollection of messages.
    /// </summary>
    /// <returns>A task that represents the asynchronous operation.</returns>
    [Fact]
    public async Task InvokeWithSingleMessageCallsMockedInvokeWithMessageInCollectionAsync()
    {
        // Arrange
        var message = new ChatMessage(ChatRole.User, "Hello, Agent!");
        var options = new AgentRunOptions();
        var cancellationToken = default(CancellationToken);

        // Act
        var response = await this._agentMock.Object.RunAsync(message, this._agentSessionMock.Object, options, cancellationToken);
        Assert.Equal(this._invokeResponse, response);

        // Verify that the mocked method was called with the expected parameters
        this._agentMock
            .Protected()
            .Verify<Task<AgentResponse>>("RunCoreAsync",
                Times.Once(),
                ItExpr.Is<IEnumerable<ChatMessage>>(messages => messages.Count() == 1 && messages.First() == message),
                ItExpr.Is<AgentSession?>(t => t == this._agentSessionMock.Object),
                ItExpr.Is<AgentRunOptions?>(o => o == options),
                ItExpr.Is<CancellationToken>(ct => ct == cancellationToken));
    }

    /// <summary>
    /// Tests that invoking streaming without a message calls the mocked invoke method with an empty array.
    /// </summary>
    /// <returns>A task that represents the asynchronous operation.</returns>
    [Fact]
    public async Task InvokeStreamingWithoutMessageCallsMockedInvokeWithEmptyArrayAsync()
    {
        // Arrange
        var options = new AgentRunOptions();
        var cancellationToken = default(CancellationToken);

        // Act
        await foreach (var response in this._agentMock.Object.RunStreamingAsync(this._agentSessionMock.Object, options, cancellationToken))
        {
            // Assert
            Assert.Contains(response, this._invokeStreamingResponses);
        }

        // Verify that the mocked method was called with the expected parameters
        this._agentMock
            .Protected()
            .Verify<IAsyncEnumerable<AgentResponseUpdate>>("RunCoreStreamingAsync",
                Times.Once(),
                ItExpr.Is<IEnumerable<ChatMessage>>(messages => !messages.Any()),
                ItExpr.Is<AgentSession?>(t => t == this._agentSessionMock.Object),
                ItExpr.Is<AgentRunOptions?>(o => o == options),
                ItExpr.Is<CancellationToken>(ct => ct == cancellationToken));
    }

    /// <summary>
    /// Tests that invoking streaming with a string message calls the mocked invoke method with the message in the ICollection of messages.
    /// </summary>
    /// <returns>A task that represents the asynchronous operation.</returns>
    [Fact]
    public async Task InvokeStreamingWithStringMessageCallsMockedInvokeWithMessageInCollectionAsync()
    {
        // Arrange
        const string Message = "Hello, Agent!";
        var options = new AgentRunOptions();
        var cancellationToken = default(CancellationToken);

        // Act
        await foreach (var response in this._agentMock.Object.RunStreamingAsync(Message, this._agentSessionMock.Object, options, cancellationToken))
        {
            // Assert
            Assert.Contains(response, this._invokeStreamingResponses);
        }

        // Verify that the mocked method was called with the expected parameters
        this._agentMock
            .Protected()
            .Verify<IAsyncEnumerable<AgentResponseUpdate>>("RunCoreStreamingAsync",
                Times.Once(),
                ItExpr.Is<IEnumerable<ChatMessage>>(messages => messages.Count() == 1 && messages.First().Text == Message),
                ItExpr.Is<AgentSession?>(t => t == this._agentSessionMock.Object),
                ItExpr.Is<AgentRunOptions?>(o => o == options),
                ItExpr.Is<CancellationToken>(ct => ct == cancellationToken));
    }

    /// <summary>
    /// Tests that invoking streaming with a single message calls the mocked invoke method with the message in the ICollection of messages.
    /// </summary>
    /// <returns>A task that represents the asynchronous operation.</returns>
    [Fact]
    public async Task InvokeStreamingWithSingleMessageCallsMockedInvokeWithMessageInCollectionAsync()
    {
        // Arrange
        var message = new ChatMessage(ChatRole.User, "Hello, Agent!");
        var options = new AgentRunOptions();
        var cancellationToken = default(CancellationToken);

        // Act
        await foreach (var response in this._agentMock.Object.RunStreamingAsync(message, this._agentSessionMock.Object, options, cancellationToken))
        {
            // Assert
            Assert.Contains(response, this._invokeStreamingResponses);
        }

        // Verify that the mocked method was called with the expected parameters
        this._agentMock
            .Protected()
            .Verify<IAsyncEnumerable<AgentResponseUpdate>>("RunCoreStreamingAsync",
                Times.Once(),
                ItExpr.Is<IEnumerable<ChatMessage>>(messages => messages.Count() == 1 && messages.First() == message),
                ItExpr.Is<AgentSession?>(t => t == this._agentSessionMock.Object),
                ItExpr.Is<AgentRunOptions?>(o => o == options),
                ItExpr.Is<CancellationToken>(ct => ct == cancellationToken));
    }

    /// <summary>
    /// Theory data for RunAsync overloads.
    /// </summary>
    public static TheoryData<string> RunAsyncOverloads => new()
    {
        "NoMessage",
        "StringMessage",
        "ChatMessage",
        "MessagesCollection"
    };

    /// <summary>
    /// Verifies that CurrentRunContext is properly set and accessible from RunCoreAsync for all RunAsync overloads.
    /// </summary>
    [Theory]
    [MemberData(nameof(RunAsyncOverloads))]
    public async Task RunAsync_SetsCurrentRunContext_AccessibleFromRunCoreAsync(string overload)
    {
        // Arrange
        AgentRunContext? capturedContext = null;
        var session = new TestAgentSession();
        var options = new AgentRunOptions();

        var agentMock = new Mock<AIAgent> { CallBase = true };
        agentMock
            .Protected()
            .Setup<Task<AgentResponse>>("RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .Returns((IEnumerable<ChatMessage> _, AgentSession? _, AgentRunOptions? _, CancellationToken _) =>
            {
                capturedContext = AIAgent.CurrentRunContext;
                return Task.FromResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "Response")));
            });

        // Act
        switch (overload)
        {
            case "NoMessage":
                await agentMock.Object.RunAsync(session, options);
                break;
            case "StringMessage":
                await agentMock.Object.RunAsync("Hello", session, options);
                break;
            case "ChatMessage":
                await agentMock.Object.RunAsync(new ChatMessage(ChatRole.User, "Hello"), session, options);
                break;
            case "MessagesCollection":
                await agentMock.Object.RunAsync([new ChatMessage(ChatRole.User, "Hello")], session, options);
                break;
        }

        // Assert
        Assert.NotNull(capturedContext);
        Assert.Same(agentMock.Object, capturedContext!.Agent);
        Assert.Same(session, capturedContext.Session);
        Assert.Same(options, capturedContext.RunOptions);

        if (overload == "NoMessage")
        {
            Assert.Empty(capturedContext.RequestMessages);
        }
        else
        {
            Assert.Single(capturedContext.RequestMessages);
        }
    }

    /// <summary>
    /// Verifies that CurrentRunContext is properly set and accessible from RunCoreStreamingAsync for all RunStreamingAsync overloads.
    /// </summary>
    [Theory]
    [MemberData(nameof(RunAsyncOverloads))]
    public async Task RunStreamingAsync_SetsCurrentRunContext_AccessibleFromRunCoreStreamingAsync(string overload)
    {
        // Arrange
        AgentRunContext? capturedContext = null;
        var session = new TestAgentSession();
        var options = new AgentRunOptions();

        var agentMock = new Mock<AIAgent> { CallBase = true };
        agentMock
            .Protected()
            .Setup<IAsyncEnumerable<AgentResponseUpdate>>("RunCoreStreamingAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .Returns((IEnumerable<ChatMessage> _, AgentSession? _, AgentRunOptions? _, CancellationToken _) =>
            {
                capturedContext = AIAgent.CurrentRunContext;
                return ToAsyncEnumerableAsync([new AgentResponseUpdate(ChatRole.Assistant, "Response")]);
            });

        // Act
        IAsyncEnumerable<AgentResponseUpdate> stream = overload switch
        {
            "NoMessage" => agentMock.Object.RunStreamingAsync(session, options),
            "StringMessage" => agentMock.Object.RunStreamingAsync("Hello", session, options),
            "ChatMessage" => agentMock.Object.RunStreamingAsync(new ChatMessage(ChatRole.User, "Hello"), session, options),
            "MessagesCollection" => agentMock.Object.RunStreamingAsync(new[] { new ChatMessage(ChatRole.User, "Hello") }, session, options),
            _ => throw new InvalidOperationException($"Unknown overload: {overload}")
        };

        await foreach (AgentResponseUpdate _ in stream)
        {
            // Consume the stream
        }

        // Assert
        Assert.NotNull(capturedContext);
        Assert.Same(agentMock.Object, capturedContext!.Agent);
        Assert.Same(session, capturedContext.Session);
        Assert.Same(options, capturedContext.RunOptions);

        if (overload == "NoMessage")
        {
            Assert.Empty(capturedContext.RequestMessages);
        }
        else
        {
            Assert.Single(capturedContext.RequestMessages);
        }
    }

    [Fact]
    public void ValidateAgentIDIsIdempotent()
    {
        // Arrange
        var agent = new MockAgent();

        // Act
        string id = agent.Id;

        // Assert
        Assert.NotNull(id);
        Assert.Equal(id, agent.Id);
    }

    [Fact]
    public void ValidateAgentIDCanBeProvidedByDerivedAgentClass()
    {
        // Arrange
        var agent = new MockAgent(id: "test-agent-id");

        // Act
        string id = agent.Id;

        // Assert
        Assert.NotNull(id);
        Assert.Equal("test-agent-id", id);
    }

    #region GetService Method Tests

    /// <summary>
    /// Verify that GetService returns the agent itself when requesting the exact agent type.
    /// </summary>
    [Fact]
    public void GetService_RequestingExactAgentType_ReturnsAgent()
    {
        // Arrange
        var agent = new MockAgent();

        // Act
        var result = agent.GetService(typeof(MockAgent));

        // Assert
        Assert.NotNull(result);
        Assert.Same(agent, result);
    }

    /// <summary>
    /// Verify that GetService returns the agent itself when requesting the base AIAgent type.
    /// </summary>
    [Fact]
    public void GetService_RequestingAIAgentType_ReturnsAgent()
    {
        // Arrange
        var agent = new MockAgent();

        // Act
        var result = agent.GetService(typeof(AIAgent));

        // Assert
        Assert.NotNull(result);
        Assert.Same(agent, result);
    }

    /// <summary>
    /// Verify that GetService returns null when requesting an unrelated type.
    /// </summary>
    [Fact]
    public void GetService_RequestingUnrelatedType_ReturnsNull()
    {
        // Arrange
        var agent = new MockAgent();

        // Act
        var result = agent.GetService(typeof(string));

        // Assert
        Assert.Null(result);
    }

    /// <summary>
    /// Verify that GetService returns null when a service key is provided, even for matching types.
    /// </summary>
    [Fact]
    public void GetService_WithServiceKey_ReturnsNull()
    {
        // Arrange
        var agent = new MockAgent();

        // Act
        var result = agent.GetService(typeof(MockAgent), "some-key");

        // Assert
        Assert.Null(result);
    }

    /// <summary>
    /// Verify that GetService throws ArgumentNullException when serviceType is null.
    /// </summary>
    [Fact]
    public void GetService_WithNullServiceType_ThrowsArgumentNullException()
    {
        // Arrange
        var agent = new MockAgent();

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => agent.GetService(null!));
    }

    /// <summary>
    /// Verify that GetService generic method works correctly.
    /// </summary>
    [Fact]
    public void GetService_Generic_ReturnsCorrectType()
    {
        // Arrange
        var agent = new MockAgent();

        // Act
        var result = agent.GetService<MockAgent>();

        // Assert
        Assert.NotNull(result);
        Assert.Same(agent, result);
    }

    /// <summary>
    /// Verify that GetService generic method returns null for unrelated types.
    /// </summary>
    [Fact]
    public void GetService_Generic_ReturnsNullForUnrelatedType()
    {
        // Arrange
        var agent = new MockAgent();

        // Act
        var result = agent.GetService<string>();

        // Assert
        Assert.Null(result);
    }

    #endregion

    #region Name and Description Property Tests

    /// <summary>
    /// Verify that Name property returns the value from the derived class.
    /// </summary>
    [Fact]
    public void Name_ReturnsValueFromDerivedClass()
    {
        // Arrange
        var agent = new MockAgentWithName("TestAgentName", "TestAgentDescription");

        // Act
        string? name = agent.Name;

        // Assert
        Assert.Equal("TestAgentName", name);
    }

    /// <summary>
    /// Verify that Description property returns the value from the derived class.
    /// </summary>
    [Fact]
    public void Description_ReturnsValueFromDerivedClass()
    {
        // Arrange
        var agent = new MockAgentWithName("TestAgentName", "TestAgentDescription");

        // Act
        string? description = agent.Description;

        // Assert
        Assert.Equal("TestAgentDescription", description);
    }

    /// <summary>
    /// Verify that Name property returns null when not overridden.
    /// </summary>
    [Fact]
    public void Name_ReturnsNullByDefault()
    {
        // Arrange
        var agent = new MockAgent();

        // Act
        string? name = agent.Name;

        // Assert
        Assert.Null(name);
    }

    /// <summary>
    /// Verify that Description property returns null when not overridden.
    /// </summary>
    [Fact]
    public void Description_ReturnsNullByDefault()
    {
        // Arrange
        var agent = new MockAgent();

        // Act
        string? description = agent.Description;

        // Assert
        Assert.Null(description);
    }

    #endregion

    /// <summary>
    /// Typed mock session for testing purposes.
    /// </summary>
    private sealed class TestAgentSession : AgentSession;

    private sealed class MockAgent : AIAgent
    {
        public MockAgent(string? id = null)
        {
            this.IdCore = id;
        }

        protected override string? IdCore { get; }

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
            => throw new NotImplementedException();

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
            => throw new NotImplementedException();

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
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

    private sealed class MockAgentWithName : AIAgent
    {
        private readonly string? _name;
        private readonly string? _description;

        public MockAgentWithName(string? name, string? description)
        {
            this._name = name;
            this._description = description;
        }

        public override string? Name => this._name;
        public override string? Description => this._description;

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
            => throw new NotImplementedException();

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
            => throw new NotImplementedException();

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
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

    private static async IAsyncEnumerable<T> ToAsyncEnumerableAsync<T>(IEnumerable<T> values)
    {
        await Task.Yield();
        foreach (var update in values)
        {
            yield return update;
        }
    }
}
