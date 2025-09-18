// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Moq;

namespace Microsoft.Extensions.AI.Agents.Abstractions.UnitTests;

/// <summary>
/// Unit tests for the <see cref="DelegatingAIAgent"/> class.
/// </summary>
public class DelegatingAIAgentTests
{
    private readonly Mock<AIAgent> _innerAgentMock;
    private readonly TestDelegatingAIAgent _delegatingAgent;
    private readonly AgentRunResponse _testResponse;
    private readonly List<AgentRunResponseUpdate> _testStreamingResponses;
    private readonly AgentThread _testThread;

    /// <summary>
    /// Initializes a new instance of the <see cref="DelegatingAIAgentTests"/> class.
    /// </summary>
    public DelegatingAIAgentTests()
    {
        this._innerAgentMock = new Mock<AIAgent>();
        this._testResponse = new AgentRunResponse(new ChatMessage(ChatRole.Assistant, "Test response"));
        this._testStreamingResponses = [new AgentRunResponseUpdate(ChatRole.Assistant, "Test streaming response")];
        this._testThread = new TestAgentThread();

        // Setup inner agent mock
        this._innerAgentMock.Setup(x => x.Id).Returns("test-agent-id");
        this._innerAgentMock.Setup(x => x.Name).Returns("Test Agent");
        this._innerAgentMock.Setup(x => x.Description).Returns("Test Description");
        this._innerAgentMock.Setup(x => x.GetNewThread()).Returns(this._testThread);

        this._innerAgentMock
            .Setup(x => x.RunAsync(
                It.IsAny<IReadOnlyCollection<ChatMessage>>(),
                It.IsAny<AgentThread?>(),
                It.IsAny<AgentRunOptions?>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(this._testResponse);

        this._innerAgentMock
            .Setup(x => x.RunStreamingAsync(
                It.IsAny<IReadOnlyCollection<ChatMessage>>(),
                It.IsAny<AgentThread?>(),
                It.IsAny<AgentRunOptions?>(),
                It.IsAny<CancellationToken>()))
            .Returns(ToAsyncEnumerableAsync(this._testStreamingResponses));

        this._delegatingAgent = new TestDelegatingAIAgent(this._innerAgentMock.Object);
    }

    #region Constructor Tests

    /// <summary>
    /// Verify that constructor throws ArgumentNullException when innerAgent is null.
    /// </summary>
    [Fact]
    public void RequiresInnerAgent() =>
        // Act & Assert
        Assert.Throws<ArgumentNullException>("innerAgent", () => new TestDelegatingAIAgent(null!));

    /// <summary>
    /// Verify that constructor sets the inner agent correctly.
    /// </summary>
    [Fact]
    public void Constructor_WithValidInnerAgent_SetsInnerAgent()
    {
        // Act
        var delegatingAgent = new TestDelegatingAIAgent(this._innerAgentMock.Object);

        // Assert
        Assert.Same(this._innerAgentMock.Object, delegatingAgent.InnerAgent);
    }

    #endregion

    #region Property Delegation Tests

    /// <summary>
    /// Verify that Id property delegates to inner agent.
    /// </summary>
    [Fact]
    public void Id_DelegatesToInnerAgent()
    {
        // Act
        var id = this._delegatingAgent.Id;

        // Assert
        Assert.Equal("test-agent-id", id);
        this._innerAgentMock.Verify(x => x.Id, Times.Once);
    }

    /// <summary>
    /// Verify that Name property delegates to inner agent.
    /// </summary>
    [Fact]
    public void Name_DelegatesToInnerAgent()
    {
        // Act
        var name = this._delegatingAgent.Name;

        // Assert
        Assert.Equal("Test Agent", name);
        this._innerAgentMock.Verify(x => x.Name, Times.Once);
    }

    /// <summary>
    /// Verify that Description property delegates to inner agent.
    /// </summary>
    [Fact]
    public void Description_DelegatesToInnerAgent()
    {
        // Act
        var description = this._delegatingAgent.Description;

        // Assert
        Assert.Equal("Test Description", description);
        this._innerAgentMock.Verify(x => x.Description, Times.Once);
    }

    #endregion

    #region Method Delegation Tests

    /// <summary>
    /// Verify that GetNewThread delegates to inner agent.
    /// </summary>
    [Fact]
    public void GetNewThread_DelegatesToInnerAgent()
    {
        // Act
        var thread = this._delegatingAgent.GetNewThread();

        // Assert
        Assert.Same(this._testThread, thread);
        this._innerAgentMock.Verify(x => x.GetNewThread(), Times.Once);
    }

    /// <summary>
    /// Verify that RunAsync delegates to inner agent with correct parameters.
    /// </summary>
    [Fact]
    public async Task RunAsyncDefaultsToInnerAgentAsync()
    {
        // Arrange
        var expectedMessages = new[] { new ChatMessage(ChatRole.User, "Test message") };
        var expectedThread = new TestAgentThread();
        var expectedOptions = new AgentRunOptions();
        var expectedCancellationToken = new CancellationToken();
        var expectedResult = new TaskCompletionSource<AgentRunResponse>();
        var expectedResponse = new AgentRunResponse();

        var innerAgentMock = new Mock<AIAgent>();
        innerAgentMock
            .Setup(x => x.RunAsync(expectedMessages, expectedThread, expectedOptions, expectedCancellationToken))
            .Returns(expectedResult.Task);

        var delegatingAgent = new TestDelegatingAIAgent(innerAgentMock.Object);

        // Act
        var resultTask = delegatingAgent.RunAsync(expectedMessages, expectedThread, expectedOptions, expectedCancellationToken);

        // Assert
        Assert.False(resultTask.IsCompleted);
        expectedResult.SetResult(expectedResponse);
        Assert.True(resultTask.IsCompleted);
        Assert.Same(expectedResponse, await resultTask);
    }

    /// <summary>
    /// Verify that RunStreamingAsync delegates to inner agent with correct parameters.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsyncDefaultsToInnerAgentAsync()
    {
        // Arrange
        var expectedMessages = new[] { new ChatMessage(ChatRole.User, "Test message") };
        var expectedThread = new TestAgentThread();
        var expectedOptions = new AgentRunOptions();
        var expectedCancellationToken = new CancellationToken();
        AgentRunResponseUpdate[] expectedResults =
        [
            new(ChatRole.Assistant, "Message 1"),
            new(ChatRole.Assistant, "Message 2")
        ];

        var innerAgentMock = new Mock<AIAgent>();
        innerAgentMock
            .Setup(x => x.RunStreamingAsync(expectedMessages, expectedThread, expectedOptions, expectedCancellationToken))
            .Returns(ToAsyncEnumerableAsync(expectedResults));

        var delegatingAgent = new TestDelegatingAIAgent(innerAgentMock.Object);

        // Act
        var resultAsyncEnumerable = delegatingAgent.RunStreamingAsync(expectedMessages, expectedThread, expectedOptions, expectedCancellationToken);

        // Assert
        var enumerator = resultAsyncEnumerable.GetAsyncEnumerator();
        Assert.True(await enumerator.MoveNextAsync());
        Assert.Same(expectedResults[0], enumerator.Current);
        Assert.True(await enumerator.MoveNextAsync());
        Assert.Same(expectedResults[1], enumerator.Current);
        Assert.False(await enumerator.MoveNextAsync());
    }

    #endregion

    #region GetService Tests

    /// <summary>
    /// Verify that GetService throws ArgumentNullException when serviceType is null.
    /// </summary>
    [Fact]
    public void GetServiceThrowsForNullType() =>
        // Act & Assert
        Assert.Throws<ArgumentNullException>("serviceType", () => this._delegatingAgent.GetService(null!));

    /// <summary>
    /// Verify that GetService returns the delegating agent itself when requesting compatible type and key is null.
    /// </summary>
    [Fact]
    public void GetServiceReturnsSelfIfCompatibleWithRequestAndKeyIsNull()
    {
        // Act
        var agent = this._delegatingAgent.GetService<DelegatingAIAgent>();

        // Assert
        Assert.Same(this._delegatingAgent, agent);
    }

    /// <summary>
    /// Verify that GetService delegates to inner agent when service key is not null.
    /// </summary>
    [Fact]
    public void GetServiceDelegatesToInnerIfKeyIsNotNull()
    {
        // Arrange
        var expectedKey = new object();
        var expectedResult = new Mock<AIAgent>().Object;
        var innerAgentMock = new Mock<AIAgent>();
        innerAgentMock.Setup(x => x.GetService(typeof(AIAgent), expectedKey)).Returns(expectedResult);
        var delegatingAgent = new TestDelegatingAIAgent(innerAgentMock.Object);

        // Act
        var agent = delegatingAgent.GetService<AIAgent>(expectedKey);

        // Assert
        Assert.Same(expectedResult, agent);
    }

    /// <summary>
    /// Verify that GetService delegates to inner agent when not compatible with request.
    /// </summary>
    [Fact]
    public void GetServiceDelegatesToInnerIfNotCompatibleWithRequest()
    {
        // Arrange
        var expectedResult = TimeZoneInfo.Local;
        var expectedKey = new object();
        var innerAgentMock = new Mock<AIAgent>();
        innerAgentMock
            .Setup(x => x.GetService(typeof(TimeZoneInfo), expectedKey))
            .Returns(expectedResult);
        var delegatingAgent = new TestDelegatingAIAgent(innerAgentMock.Object);

        // Act
        var tzi = delegatingAgent.GetService<TimeZoneInfo>(expectedKey);

        // Assert
        Assert.Same(expectedResult, tzi);
    }

    #endregion

    #region Helper Methods

    private static async IAsyncEnumerable<T> ToAsyncEnumerableAsync<T>(IEnumerable<T> values)
    {
        await Task.Yield();
        foreach (var value in values)
        {
            yield return value;
        }
    }

    #endregion

    #region Test Implementation

    /// <summary>
    /// Test implementation of DelegatingAIAgent for testing purposes.
    /// </summary>
    private sealed class TestDelegatingAIAgent(AIAgent innerAgent) : DelegatingAIAgent(innerAgent)
    {
        public new AIAgent InnerAgent => base.InnerAgent;
    }

    private sealed class TestAgentThread : AgentThread
    {
    }

    #endregion
}
