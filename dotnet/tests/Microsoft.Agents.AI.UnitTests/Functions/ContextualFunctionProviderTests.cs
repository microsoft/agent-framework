// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Functions;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.VectorData;
using Moq;

namespace Microsoft.Agents.AI.UnitTests.Functions;

/// <summary>
/// Contains unit tests for the <see cref="ContextualFunctionProvider"/> class.
/// </summary>
public sealed class ContextualFunctionProviderTests
{
    private readonly Mock<VectorStore> _vectorStoreMock;
    private readonly Mock<VectorStoreCollection<object, Dictionary<string, object?>>> _collectionMock;

    public ContextualFunctionProviderTests()
    {
        this._vectorStoreMock = new Mock<VectorStore>(MockBehavior.Strict);
        this._collectionMock = new Mock<VectorStoreCollection<object, Dictionary<string, object?>>>(MockBehavior.Strict);

        this._vectorStoreMock
            .Setup(vs => vs.GetDynamicCollection(It.IsAny<string>(), It.IsAny<VectorStoreCollectionDefinition>()))
            .Returns(this._collectionMock.Object);

        this._collectionMock
            .Setup(c => c.CollectionExistsAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(true);

        this._collectionMock
            .Setup(c => c.EnsureCollectionExistsAsync(It.IsAny<CancellationToken>()))
            .Returns(Task.CompletedTask);

        this._collectionMock
            .Setup(c => c.UpsertAsync(It.IsAny<IEnumerable<Dictionary<string, object?>>>(), It.IsAny<CancellationToken>()))
            .Returns(Task.CompletedTask);

        this._collectionMock
            .Setup(c => c.SearchAsync(It.IsAny<string>(), It.IsAny<int>(), null, It.IsAny<CancellationToken>()))
            .Returns(AsyncEnumerable.Empty<VectorSearchResult<Dictionary<string, object?>>>());
    }

    [Fact]
    public void Constructor_ShouldThrow_OnInvalidArguments()
    {
        // Arrange
        var vectorStore = new Mock<VectorStore>().Object;
        var functions = new List<AIFunction> { CreateFunction("f1") };

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new ContextualFunctionProvider(null!, 1, functions, 3));
        Assert.Throws<ArgumentOutOfRangeException>(() => new ContextualFunctionProvider(vectorStore, 0, functions, 3));
        Assert.Throws<ArgumentNullException>(() => new ContextualFunctionProvider(vectorStore, 1, null!, 3));
    }

    [Fact]
    public async Task Invoking_ShouldVectorizeFunctions_Once_Async()
    {
        // Arrange
        var function = CreateFunction("f1", "desc");
        var functions = new List<AIFunction> { function };

        this._collectionMock
            .Setup(c => c.UpsertAsync(It.IsAny<IEnumerable<Dictionary<string, object?>>>(), It.IsAny<CancellationToken>()))
            .Returns(Task.CompletedTask);

        var provider = new ContextualFunctionProvider(
            vectorStore: this._vectorStoreMock.Object,
            vectorDimensions: 1536,
            functions: functions,
            maxNumberOfFunctions: 5);

        var messages = new List<ChatMessage> { new() { Contents = [new TextContent("hello")] } };
        var context = new AIContextProvider.InvokingContext(messages);

        // Act
        await provider.InvokingAsync(context);
        await provider.InvokingAsync(context);

        // Assert
        this._collectionMock.Verify(
            c => c.UpsertAsync(It.IsAny<IEnumerable<Dictionary<string, object?>>>(), It.IsAny<CancellationToken>()),
            Times.Once);
    }

    [Fact]
    public async Task Invoking_ShouldReturnRelevantFunctions_Async()
    {
        // Arrange
        var function = CreateFunction("f1", "desc");
        var functions = new List<AIFunction> { function };

        var searchResult = new VectorSearchResult<Dictionary<string, object?>>(
            new Dictionary<string, object?>
            {
                ["Name"] = function.Name,
                ["Description"] = function.Description
            },
            0.99f
        );

        this._collectionMock
            .Setup(c => c.SearchAsync(It.IsAny<string>(), It.IsAny<int>(), null, It.IsAny<CancellationToken>()))
            .Returns(new[] { searchResult }.ToAsyncEnumerable());

        var provider = new ContextualFunctionProvider(
            vectorStore: this._vectorStoreMock.Object,
            vectorDimensions: 1536,
            functions: functions,
            maxNumberOfFunctions: 5);

        var messages = new List<ChatMessage> { new() { Contents = [new TextContent("context")] } };
        var context = new AIContextProvider.InvokingContext(messages);

        // Act
        var result = await provider.InvokingAsync(context);

        // Assert
        Assert.NotNull(result);
        Assert.NotNull(result.Tools);
        Assert.Single(result.Tools);
        Assert.Equal("f1", result.Tools[0].Name);
        this._collectionMock.Verify(
            c => c.SearchAsync("context", 5, null, It.IsAny<CancellationToken>()),
            Times.Once);
    }

    [Fact]
    public async Task BuildContext_ShouldUseContextEmbeddingValueProvider_Async()
    {
        // Arrange
        var functions = new List<AIFunction> { CreateFunction("f1") };
        var options = new ContextualFunctionProviderOptions
        {
            NumberOfRecentMessagesInContext = 3,
            ContextEmbeddingValueProvider = (recentMessages, newMessages, _) =>
            {
                Assert.Equal(3, recentMessages.Count());
                Assert.Single(newMessages);
                return Task.FromResult("custom context");
            }
        };

        var provider = new ContextualFunctionProvider(
            vectorStore: this._vectorStoreMock.Object,
            vectorDimensions: 1536,
            functions: functions,
            maxNumberOfFunctions: 5,
            options: options);

        var message1 = new ChatMessage() { Contents = [new TextContent("msg1")] };
        var message2 = new ChatMessage() { Contents = [new TextContent("msg2")] };
        var message3 = new ChatMessage() { Contents = [new TextContent("msg3")] };
        var message4 = new ChatMessage() { Contents = [new TextContent("msg4")] };
        var message5 = new ChatMessage() { Contents = [new TextContent("msg5")] };

        // Simulate previous invocations to populate recent messages
        await provider.InvokedAsync(new AIContextProvider.InvokedContext([message1], null) { ResponseMessages = [] });
        await provider.InvokedAsync(new AIContextProvider.InvokedContext([message2], null) { ResponseMessages = [] });
        await provider.InvokedAsync(new AIContextProvider.InvokedContext([message3], null) { ResponseMessages = [] });
        await provider.InvokedAsync(new AIContextProvider.InvokedContext([message4], null) { ResponseMessages = [] });

        var messages = new List<ChatMessage> { message5 };
        var context = new AIContextProvider.InvokingContext(messages);

        // Act
        await provider.InvokingAsync(context);

        // Assert
        this._collectionMock.Verify(
            c => c.SearchAsync("custom context", It.IsAny<int>(), null, It.IsAny<CancellationToken>()),
            Times.Once);
    }

    [Fact]
    public async Task BuildContext_ShouldConcatenateMessages_Async()
    {
        // Arrange
        var functions = new List<AIFunction> { CreateFunction("f1") };
        var options = new ContextualFunctionProviderOptions
        {
            NumberOfRecentMessagesInContext = 3
        };

        var provider = new ContextualFunctionProvider(
            vectorStore: this._vectorStoreMock.Object,
            vectorDimensions: 1536,
            functions: functions,
            maxNumberOfFunctions: 5,
            options: options);

        var message1 = new ChatMessage() { Contents = [new TextContent("msg1")] };
        var message2 = new ChatMessage() { Contents = [new TextContent("msg2")] };
        var message3 = new ChatMessage() { Contents = [new TextContent("msg3")] };
        var message4 = new ChatMessage() { Contents = [new TextContent("msg4")] };
        var message5 = new ChatMessage() { Contents = [new TextContent("msg5")] };

        // Simulate previous invocations to populate recent messages
        await provider.InvokedAsync(new AIContextProvider.InvokedContext([message1], null) { ResponseMessages = [] });
        await provider.InvokedAsync(new AIContextProvider.InvokedContext([message2], null) { ResponseMessages = [] });
        await provider.InvokedAsync(new AIContextProvider.InvokedContext([message3], null) { ResponseMessages = [] });
        await provider.InvokedAsync(new AIContextProvider.InvokedContext([message4], null) { ResponseMessages = [] });

        // Act
        var invokingContext = new AIContextProvider.InvokingContext([message5]);
        var context = await provider.InvokingAsync(invokingContext);

        // Assert
        var expected = string.Join(Environment.NewLine, ["msg2", "msg3", "msg4", "msg5"]);
        this._collectionMock.Verify(c => c.SearchAsync(expected, It.IsAny<int>(), null, It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task BuildContext_ShouldUseEmbeddingValueProvider_Async()
    {
        // Arrange
        List<Dictionary<string, object?>>? upsertedRecords = null;
        this._collectionMock
            .Setup(c => c.UpsertAsync(It.IsAny<IEnumerable<Dictionary<string, object?>>>(), It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<Dictionary<string, object?>>, CancellationToken>((records, _) => upsertedRecords = records.ToList())
            .Returns(Task.CompletedTask);

        var functions = new List<AIFunction> { CreateFunction("f1", "desc1") };
        var options = new ContextualFunctionProviderOptions
        {
            EmbeddingValueProvider = (func, ct) => Task.FromResult($"custom embedding for {func.Name}:{func.Description}")
        };

        var provider = new ContextualFunctionProvider(
            vectorStore: this._vectorStoreMock.Object,
            vectorDimensions: 1536,
            functions: functions,
            maxNumberOfFunctions: 5,
            options: options);

        var messages = new List<ChatMessage>
        {
            new() { Contents = [new TextContent("ignored")] }
        };
        var context = new AIContextProvider.InvokingContext(messages);

        // Act
        await provider.InvokingAsync(context);

        // Assert
        Assert.NotNull(upsertedRecords);
        var embeddingSource = upsertedRecords!.SelectMany(r => r).FirstOrDefault(kv => kv.Key == "Embedding").Value as string;
        Assert.Equal("custom embedding for f1:desc1", embeddingSource);
    }

    [Fact]
    public async Task ContextEmbeddingValueProvider_ReceivesRecentAndNewMessages_Async()
    {
        // Arrange
        var functions = new List<AIFunction> { CreateFunction("f1") };

        IEnumerable<ChatMessage>? capturedRecentMessages = null;
        IEnumerable<ChatMessage>? capturedNewMessages = null;

        var options = new ContextualFunctionProviderOptions
        {
            NumberOfRecentMessagesInContext = 2,
            ContextEmbeddingValueProvider = (recentMessages, newMessages, ct) =>
            {
                capturedRecentMessages = recentMessages;
                capturedNewMessages = newMessages;

                return Task.FromResult("context");
            }
        };

        var provider = new ContextualFunctionProvider(
            vectorStore: this._vectorStoreMock.Object,
            vectorDimensions: 1536,
            functions: functions,
            maxNumberOfFunctions: 5,
            options: options);

        // Add more messages than the number of messages to keep
        await provider.InvokedAsync(new AIContextProvider.InvokedContext([new() { Contents = [new TextContent("msg1")] }], null) { ResponseMessages = [] });
        await provider.InvokedAsync(new AIContextProvider.InvokedContext([new() { Contents = [new TextContent("msg2")] }], null) { ResponseMessages = [] });
        await provider.InvokedAsync(new AIContextProvider.InvokedContext([new() { Contents = [new TextContent("msg3")] }], null) { ResponseMessages = [] });

        // Act
        var invokingContext = new AIContextProvider.InvokingContext([
            new() { Contents = [new TextContent("msg4")] },
            new() { Contents = [new TextContent("msg5")] }
        ]);
        await provider.InvokingAsync(invokingContext);

        // Assert
        Assert.NotNull(capturedRecentMessages);
        Assert.Equal("msg2", capturedRecentMessages.ElementAt(0).Text);
        Assert.Equal("msg3", capturedRecentMessages.ElementAt(1).Text);

        Assert.NotNull(capturedNewMessages);
        Assert.Equal("msg4", capturedNewMessages.ElementAt(0).Text);
        Assert.Equal("msg5", capturedNewMessages.ElementAt(1).Text);
    }

    [Fact]
    public async Task Serialize_WithNoRecentMessages_ShouldReturnEmptyStateAsync()
    {
        // Arrange
        var functions = new List<AIFunction> { CreateFunction("f1") };
        var options = new ContextualFunctionProviderOptions
        {
            NumberOfRecentMessagesInContext = 5
        };

        var provider = new ContextualFunctionProvider(
            vectorStore: this._vectorStoreMock.Object,
            vectorDimensions: 1536,
            functions: functions,
            maxNumberOfFunctions: 5,
            options: options);
        var message1 = new ChatMessage() { Contents = [new TextContent("msg1")] };
        var message2 = new ChatMessage() { Contents = [new TextContent("msg2")] };
        var message3 = new ChatMessage() { Contents = [new TextContent("msg3")] };

        // Add successful invocations first
        await provider.InvokedAsync(new AIContextProvider.InvokedContext([message1], null) { ResponseMessages = [] });
        await provider.InvokedAsync(new AIContextProvider.InvokedContext([message2], null) { ResponseMessages = [] });

        // Act - Add an invocation with an exception
        await provider.InvokedAsync(new AIContextProvider.InvokedContext([message3], null)
        {
            ResponseMessages = [],
            InvokeException = new InvalidOperationException("Test exception")
        });

        // Assert - The exception-causing message should not be added to recent messages
        var invokingContext = new AIContextProvider.InvokingContext([new() { Contents = [new TextContent("new message")] }]);
        await provider.InvokingAsync(invokingContext);

        var expected = string.Join(Environment.NewLine, ["msg1", "msg2", "new message"]);
        this._collectionMock.Verify(c => c.SearchAsync(expected, It.IsAny<int>(), null, It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task InvokedAsync_ShouldNotAddMessages_WhenExceptionIsPresent_Async()
    {
        // Arrange
        var functions = new List<AIFunction> { CreateFunction("f1") };
        var options = new ContextualFunctionProviderOptions
        {
            NumberOfRecentMessagesInContext = 3
        };

        var provider = new ContextualFunctionProvider(
            vectorStore: this._vectorStoreMock.Object,
            vectorDimensions: 1536,
            functions: functions,
            maxNumberOfFunctions: 5,
            options: options);

        // Act
        JsonElement state = provider.Serialize();

        // Assert
        Assert.Equal(JsonValueKind.Object, state.ValueKind);
        Assert.False(state.TryGetProperty("recentMessages", out _));
    }

    [Fact]
    public async Task Serialize_WithRecentMessages_ShouldPersistMessagesUpToLimitAsync()
    {
        // Arrange
        var functions = new List<AIFunction> { CreateFunction("f1") };
        var options = new ContextualFunctionProviderOptions
        {
            NumberOfRecentMessagesInContext = 2
        };

        var provider = new ContextualFunctionProvider(
            vectorStore: this._vectorStoreMock.Object,
            vectorDimensions: 1536,
            functions: functions,
            maxNumberOfFunctions: 5,
            options: options);

        var messages = new[]
        {
            new ChatMessage() { Contents = [new TextContent("M1")] },
            new ChatMessage() { Contents = [new TextContent("M2")] },
            new ChatMessage() { Contents = [new TextContent("M3")] }
        };

        // Act
        await provider.InvokedAsync(new AIContextProvider.InvokedContext(messages, aiContextProviderMessages: null));
        JsonElement state = provider.Serialize();

        // Assert
        Assert.True(state.TryGetProperty("recentMessages", out JsonElement recentProperty));
        Assert.Equal(JsonValueKind.Array, recentProperty.ValueKind);
        int count = recentProperty.GetArrayLength();
        Assert.Equal(2, count);
    }

    [Fact]
    public async Task SerializeAndDeserialize_RoundtripRestoresMessagesAsync()
    {
        // Arrange
        var functions = new List<AIFunction> { CreateFunction("f1") };
        var options = new ContextualFunctionProviderOptions
        {
            NumberOfRecentMessagesInContext = 4
        };

        var provider = new ContextualFunctionProvider(
            vectorStore: this._vectorStoreMock.Object,
            vectorDimensions: 1536,
            functions: functions,
            maxNumberOfFunctions: 5,
            options: options);

        var messages = new[]
        {
            new ChatMessage() { Contents = [new TextContent("A")] },
            new ChatMessage() { Contents = [new TextContent("B")] },
            new ChatMessage() { Contents = [new TextContent("C")] },
            new ChatMessage() { Contents = [new TextContent("D")] }
        };

        await provider.InvokedAsync(new AIContextProvider.InvokedContext(messages, aiContextProviderMessages: null));

        // Act
        JsonElement state = provider.Serialize();
        var roundTrippedProvider = new ContextualFunctionProvider(
            vectorStore: this._vectorStoreMock.Object,
            vectorDimensions: 1536,
            functions: functions,
            maxNumberOfFunctions: 5,
            serializedState: state,
            options: new ContextualFunctionProviderOptions
            {
                NumberOfRecentMessagesInContext = 4
            });

        // Trigger search to verify messages are used
        var invokingContext = new AIContextProvider.InvokingContext(Array.Empty<ChatMessage>());
        await roundTrippedProvider.InvokingAsync(invokingContext);

        // Assert
        string expected = string.Join(Environment.NewLine, ["A", "B", "C", "D"]);
        this._collectionMock.Verify(c => c.SearchAsync(expected, It.IsAny<int>(), null, It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task Deserialize_WithChangedLowerLimit_ShouldTruncateToNewLimitAsync()
    {
        // Arrange
        var functions = new List<AIFunction> { CreateFunction("f1") };
        var initialProvider = new ContextualFunctionProvider(
            vectorStore: this._vectorStoreMock.Object,
            vectorDimensions: 1536,
            functions: functions,
            maxNumberOfFunctions: 5,
            options: new ContextualFunctionProviderOptions
            {
                NumberOfRecentMessagesInContext = 5
            });

        var messages = new[]
        {
            new ChatMessage() { Contents = [new TextContent("L1")] },
            new ChatMessage() { Contents = [new TextContent("L2")] },
            new ChatMessage() { Contents = [new TextContent("L3")] },
            new ChatMessage() { Contents = [new TextContent("L4")] },
            new ChatMessage() { Contents = [new TextContent("L5")] }
        };

        await initialProvider.InvokedAsync(new AIContextProvider.InvokedContext(messages, aiContextProviderMessages: null));
        JsonElement state = initialProvider.Serialize();

        // Act
        var restoredProvider = new ContextualFunctionProvider(
            vectorStore: this._vectorStoreMock.Object,
            vectorDimensions: 1536,
            functions: functions,
            maxNumberOfFunctions: 5,
            serializedState: state,
            options: new ContextualFunctionProviderOptions
            {
                NumberOfRecentMessagesInContext = 3 // Lower limit
            });

        var invokingContext = new AIContextProvider.InvokingContext(Array.Empty<ChatMessage>());
        await restoredProvider.InvokingAsync(invokingContext);

        // Assert
        string expected = string.Join(Environment.NewLine, ["L1", "L2", "L3"]);
        this._collectionMock.Verify(c => c.SearchAsync(expected, It.IsAny<int>(), null, It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task Deserialize_WithEmptyState_ShouldHaveNoMessagesAsync()
    {
        // Arrange
        var functions = new List<AIFunction> { CreateFunction("f1") };
        JsonElement emptyState = JsonSerializer.Deserialize("{}", TestJsonSerializerContext.Default.JsonElement);

        // Act
        var provider = new ContextualFunctionProvider(
            vectorStore: this._vectorStoreMock.Object,
            vectorDimensions: 1536,
            functions: functions,
            maxNumberOfFunctions: 5,
            serializedState: emptyState,
            options: new ContextualFunctionProviderOptions
            {
                NumberOfRecentMessagesInContext = 3
            });

        var invokingContext = new AIContextProvider.InvokingContext(Array.Empty<ChatMessage>());
        await provider.InvokingAsync(invokingContext);

        // Assert
        this._collectionMock.Verify(c => c.SearchAsync(string.Empty, It.IsAny<int>(), null, It.IsAny<CancellationToken>()), Times.Once);
    }

    private static AIFunction CreateFunction(string name, string description = "")
    {
        return AIFunctionFactory.Create(() => { }, name, description);
    }
}
