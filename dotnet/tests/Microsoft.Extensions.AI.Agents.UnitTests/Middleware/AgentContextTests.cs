// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Moq;

namespace Microsoft.Extensions.AI.Agents.UnitTests.Middleware;

/// <summary>
/// Unit tests for AgentRunContext and AgentFunctionInvocationContext classes.
/// </summary>
public sealed class AgentContextTests
{
    #region AgentRunContext Tests

    /// <summary>
    /// Tests AgentRunContext constructor with valid parameters.
    /// </summary>
    [Fact]
    public void AgentRunContext_Constructor_ValidParameters_SetsPropertiesCorrectly()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };
        var thread = new AgentThread();
        var options = new AgentRunOptions();
        var cancellationToken = new CancellationToken();

        // Act
        var context = new AgentRunContext(mockAgent.Object, messages, thread, options, isStreaming: false, cancellationToken);

        // Assert
        Assert.Same(mockAgent.Object, context.Agent);
        Assert.Equal(messages, context.Messages);
        Assert.Same(thread, context.Thread);
        Assert.Same(options, context.Options);
        Assert.False(context.IsStreaming);
        Assert.Equal(cancellationToken, context.CancellationToken);
        Assert.Null(context.RunResponse);
        Assert.Null(context.RunStreamingResponse);
        Assert.Null(context.RawResponse);
    }

    /// <summary>
    /// Tests AgentRunContext constructor with null agent throws ArgumentNullException.
    /// </summary>
    [Fact]
    public void AgentRunContext_Constructor_NullAgent_ThrowsArgumentNullException()
    {
        // Arrange
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };

        // Act & Assert
        Assert.Throws<ArgumentNullException>("agent", () =>
            new AgentRunContext(null!, messages, null, null, false, CancellationToken.None));
    }

    /// <summary>
    /// Tests AgentRunContext constructor with null messages throws ArgumentNullException.
    /// </summary>
    [Fact]
    public void AgentRunContext_Constructor_NullMessages_ThrowsArgumentNullException()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();

        // Act & Assert
        Assert.Throws<ArgumentNullException>("messages", () =>
            new AgentRunContext(mockAgent.Object, null!, null, null, false, CancellationToken.None));
    }

    /// <summary>
    /// Tests AgentRunContext constructor with streaming=true sets IsStreaming correctly.
    /// </summary>
    [Fact]
    public void AgentRunContext_Constructor_StreamingTrue_SetsIsStreamingCorrectly()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };

        // Act
        var context = new AgentRunContext(mockAgent.Object, messages, null, null, isStreaming: true, CancellationToken.None);

        // Assert
        Assert.True(context.IsStreaming);
    }

    /// <summary>
    /// Tests SetRunResponse with valid response for non-streaming context.
    /// </summary>
    [Fact]
    public void AgentRunContext_SetRunResponse_NonStreaming_SetsResponseCorrectly()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };
        var context = new AgentRunContext(mockAgent.Object, messages, null, null, isStreaming: false, CancellationToken.None);
        var response = new AgentRunResponse([new(ChatRole.Assistant, "Response")]);

        // Act
        context.SetRunResponse(response);

        // Assert
        Assert.Same(response, context.RunResponse);
        Assert.Same(response, context.RawResponse);
        Assert.Null(context.RunStreamingResponse);
    }

    /// <summary>
    /// Tests SetRunResponse throws InvalidOperationException for streaming context.
    /// </summary>
    [Fact]
    public void AgentRunContext_SetRunResponse_Streaming_ThrowsInvalidOperationException()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };
        var context = new AgentRunContext(mockAgent.Object, messages, null, null, isStreaming: true, CancellationToken.None);
        var response = new AgentRunResponse([new(ChatRole.Assistant, "Response")]);

        // Act & Assert
        var exception = Assert.Throws<InvalidOperationException>(() => context.SetRunResponse(response));
        Assert.Contains("non-streaming response", exception.Message);
        Assert.Contains("streaming invocation", exception.Message);
    }

    /// <summary>
    /// Tests SetRunStreamingResponse with valid response for streaming context.
    /// </summary>
    [Fact]
    public async Task SetRunStreamingResponse_Streaming_SetsResponseCorrectlyAsync()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };
        var context = new AgentRunContext(mockAgent.Object, messages, null, null, isStreaming: true, CancellationToken.None);
        var updates = new List<AgentRunResponseUpdate>
        {
            new(ChatRole.Assistant, "Update 1")
        };

        // Act
        var asyncEnumerable = updates.ToAsyncEnumerable();
        context.SetRunStreamingResponse(asyncEnumerable);

        // Assert
        Assert.NotNull(context.RunStreamingResponse);
        Assert.Same(asyncEnumerable, context.RunStreamingResponse);
        Assert.Null(context.RunResponse);

        // Verify the streaming response contains expected updates
        var resultUpdates = new List<AgentRunResponseUpdate>();
        await foreach (var update in context.RunStreamingResponse)
        {
            resultUpdates.Add(update);
        }
        Assert.Single(resultUpdates);
        Assert.Equal("Update 1", resultUpdates[0].Text);
    }

    /// <summary>
    /// Tests SetRunStreamingResponse throws InvalidOperationException for non-streaming context.
    /// </summary>
    [Fact]
    public void AgentRunContext_SetRunStreamingResponse_NonStreaming_ThrowsInvalidOperationException()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };
        var context = new AgentRunContext(mockAgent.Object, messages, null, null, isStreaming: false, CancellationToken.None);
        var updates = new List<AgentRunResponseUpdate>().ToAsyncEnumerable();

        // Act & Assert
        var exception = Assert.Throws<InvalidOperationException>(() => context.SetRunStreamingResponse(updates));
        Assert.Contains("streaming response", exception.Message);
        Assert.Contains("non-streaming invocation", exception.Message);
    }

    /// <summary>
    /// Tests that Messages property can be modified after construction.
    /// </summary>
    [Fact]
    public void AgentRunContext_Messages_CanBeModified()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var originalMessages = new List<ChatMessage> { new(ChatRole.User, "Original") };
        var context = new AgentRunContext(mockAgent.Object, originalMessages, null, null, false, CancellationToken.None);

        // Act
        context.Messages.Add(new ChatMessage(ChatRole.User, "Added"));
        context.Messages[0] = new ChatMessage(ChatRole.System, "Modified");

        // Assert
        Assert.Equal(2, context.Messages.Count);
        Assert.Equal("Modified", context.Messages[0].Text);
        Assert.Equal("Added", context.Messages[1].Text);
    }

    /// <summary>
    /// Tests that Options property can be replaced after construction.
    /// </summary>
    [Fact]
    public void AgentRunContext_Options_CanBeReplaced()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test") };
        var originalOptions = new AgentRunOptions();
        var newOptions = new AgentRunOptions();
        var context = new AgentRunContext(mockAgent.Object, messages, null, originalOptions, false, CancellationToken.None);

        // Act
        context.Options = newOptions;

        // Assert
        Assert.Same(newOptions, context.Options);
        Assert.NotSame(originalOptions, context.Options);
    }

    #endregion

    #region AgentFunctionInvocationContext Tests

    /// <summary>
    /// Tests AgentFunctionInvocationContext constructor and property access.
    /// </summary>
    [Fact]
    public void AgentFunctionInvocationContext_Constructor_SetsPropertiesCorrectly()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var function = AIFunctionFactory.Create(() => "result", "TestFunction");
        var arguments = new AIFunctionArguments { ["param"] = "value" };
        var cancellationToken = new CancellationToken();

        // Create a FunctionInvocationContext (this is typically created by the framework)
        var functionInvocationContext = new FunctionInvocationContext
        {
            Function = function,
            Arguments = arguments
        };

        // Act
        var context = new AgentFunctionInvocationContext(mockAgent.Object, functionInvocationContext, cancellationToken);

        // Assert
        Assert.Same(mockAgent.Object, context.Agent);
        Assert.Same(function, context.Function);
        Assert.Same(arguments, context.Arguments);
        Assert.Equal(cancellationToken, context.CancellationToken);
        Assert.Null(context.FunctionResult);
    }

    /// <summary>
    /// Tests AgentFunctionInvocationContext constructor with null agent throws ArgumentNullException.
    /// </summary>
    [Fact]
    public void AgentFunctionInvocationContext_Constructor_NullAgent_ThrowsArgumentNullException()
    {
        // Arrange
        var function = AIFunctionFactory.Create(() => "result", "TestFunction");
        var arguments = new AIFunctionArguments();
        var functionInvocationContext = new FunctionInvocationContext
        {
            Function = function,
            Arguments = arguments
        };

        // Act & Assert
        Assert.Throws<ArgumentNullException>("agent", () =>
            new AgentFunctionInvocationContext(null!, functionInvocationContext, CancellationToken.None));
    }

    /// <summary>
    /// Tests that Function property can be modified.
    /// </summary>
    [Fact]
    public void AgentFunctionInvocationContext_Function_CanBeModified()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var originalFunction = AIFunctionFactory.Create(() => "result1", "Function1");
        var newFunction = AIFunctionFactory.Create(() => "result2", "Function2");
        var arguments = new AIFunctionArguments();
        var functionInvocationContext = new FunctionInvocationContext
        {
            Function = originalFunction,
            Arguments = arguments
        };
        var context = new AgentFunctionInvocationContext(mockAgent.Object, functionInvocationContext, CancellationToken.None);

        // Act
        context.Function = newFunction;

        // Assert
        Assert.Same(newFunction, context.Function);
        Assert.NotSame(originalFunction, context.Function);
    }

    /// <summary>
    /// Tests that Arguments property can be modified.
    /// </summary>
    [Fact]
    public void AgentFunctionInvocationContext_Arguments_CanBeModified()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var function = AIFunctionFactory.Create(() => "result", "TestFunction");
        var originalArguments = new AIFunctionArguments { ["param1"] = "value1" };
        var newArguments = new AIFunctionArguments { ["param2"] = "value2" };
        var functionInvocationContext = new FunctionInvocationContext
        {
            Function = function,
            Arguments = originalArguments
        };
        var context = new AgentFunctionInvocationContext(mockAgent.Object, functionInvocationContext, CancellationToken.None);

        // Act
        context.Arguments = newArguments;

        // Assert
        Assert.Same(newArguments, context.Arguments);
        Assert.NotSame(originalArguments, context.Arguments);
    }

    /// <summary>
    /// Tests that FunctionResult property can be set and retrieved.
    /// </summary>
    [Fact]
    public void AgentFunctionInvocationContext_FunctionResult_CanBeSetAndRetrieved()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var function = AIFunctionFactory.Create(() => "result", "TestFunction");
        var arguments = new AIFunctionArguments();
        var functionInvocationContext = new FunctionInvocationContext
        {
            Function = function,
            Arguments = arguments
        };
        var context = new AgentFunctionInvocationContext(mockAgent.Object, functionInvocationContext, CancellationToken.None);
        const string ExpectedResult = "Test result";

        // Act
        context.FunctionResult = ExpectedResult;

        // Assert
        Assert.Equal(ExpectedResult, context.FunctionResult);
    }

    #endregion
}
