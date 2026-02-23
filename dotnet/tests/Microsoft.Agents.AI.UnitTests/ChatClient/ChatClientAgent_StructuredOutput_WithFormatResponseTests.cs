// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

public partial class ChatClientAgent_StructuredOutput_WithFormatResponseTests
{
    [Fact]
    public async Task RunAsync_ResponseFormatProvidedAtAgentInitialization_IsPropagatedToChatClientAsync()
    {
        // Arrange
        ChatResponseFormat? capturedResponseFormat = null;

        Mock<IChatClient> mockService = new();
        mockService.Setup(s => s
            .GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((msgs, opts, ct) => capturedResponseFormat = opts?.ResponseFormat)
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "test"))
            {
                ResponseId = "test",
            });

        ChatResponseFormatJson responseFormat = ChatResponseFormat.ForJsonSchema<Animal>(JsonContext4.Default.Options);

        ChatClientAgent agent = new(mockService.Object, options: new ChatClientAgentOptions
        {
            ChatOptions = new ChatOptions()
            {
                ResponseFormat = responseFormat
            }
        });

        // Act
        await agent.RunAsync(messages: [new(ChatRole.User, "Hello")]);

        // Assert
        Assert.NotNull(capturedResponseFormat);
        Assert.Same(responseFormat, capturedResponseFormat);
    }

    [Fact]
    public async Task RunAsync_ResponseFormatProvidedAtAgentInvocation_IsPropagatedToChatClientAsync()
    {
        // Arrange
        ChatResponseFormat? capturedResponseFormat = null;

        Mock<IChatClient> mockService = new();
        mockService.Setup(s => s
            .GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((msgs, opts, ct) => capturedResponseFormat = opts?.ResponseFormat)
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "test"))
            {
                ResponseId = "test",
            });

        ChatResponseFormatJson responseFormat = ChatResponseFormat.ForJsonSchema<Animal>(JsonContext4.Default.Options);

        ChatClientAgent agent = new(mockService.Object);

        ChatClientAgentRunOptions runOptions = new()
        {
            ResponseFormat = responseFormat
        };

        // Act
        await agent.RunAsync(messages: [new(ChatRole.User, "Hello")], options: runOptions);

        // Assert
        Assert.NotNull(capturedResponseFormat);
        Assert.Same(responseFormat, capturedResponseFormat);
    }

    [Fact]
    public async Task RunAsync_ResponseFormatProvidedAtAgentInvocation_OverridesOneProvidedAtAgentInitializationAsync()
    {
        // Arrange
        ChatResponseFormat? capturedResponseFormat = null;

        Mock<IChatClient> mockService = new();
        mockService.Setup(s => s
            .GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((msgs, opts, ct) => capturedResponseFormat = opts?.ResponseFormat)
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "test"))
            {
                ResponseId = "test",
            });

        ChatResponseFormatJson initializationResponseFormat = ChatResponseFormat.ForJsonSchema<Animal>(JsonContext4.Default.Options);
        ChatResponseFormatJson invocationResponseFormat = ChatResponseFormat.ForJsonSchema<Animal>(JsonContext4.Default.Options);

        ChatClientAgent agent = new(mockService.Object, options: new ChatClientAgentOptions
        {
            ChatOptions = new ChatOptions()
            {
                ResponseFormat = initializationResponseFormat
            },
        });

        ChatClientAgentRunOptions runOptions = new()
        {
            ResponseFormat = invocationResponseFormat
        };

        // Act
        await agent.RunAsync(messages: [new(ChatRole.User, "Hello")], options: runOptions);

        // Assert
        Assert.NotNull(capturedResponseFormat);
        Assert.Same(invocationResponseFormat, capturedResponseFormat);
        Assert.NotSame(initializationResponseFormat, capturedResponseFormat);
    }

    [Fact]
    public async Task RunAsync_ResponseFormatProvidedAtAgentRunOptions_OverridesOneProvidedViaChatOptionsAsync()
    {
        // Arrange
        ChatResponseFormat? capturedResponseFormat = null;

        Mock<IChatClient> mockService = new();
        mockService.Setup(s => s
            .GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((msgs, opts, ct) => capturedResponseFormat = opts?.ResponseFormat)
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "test"))
            {
                ResponseId = "test",
            });

        ChatResponseFormatJson chatOptionsResponseFormat = ChatResponseFormat.ForJsonSchema<Animal>(JsonContext4.Default.Options);
        ChatResponseFormatJson runOptionsResponseFormat = ChatResponseFormat.ForJsonSchema<Animal>(JsonContext4.Default.Options);

        ChatClientAgent agent = new(mockService.Object);

        ChatClientAgentRunOptions runOptions = new()
        {
            ChatOptions = new ChatOptions
            {
                ResponseFormat = chatOptionsResponseFormat
            },
            ResponseFormat = runOptionsResponseFormat
        };

        // Act
        await agent.RunAsync(messages: [new(ChatRole.User, "Hello")], options: runOptions);

        // Assert
        Assert.NotNull(capturedResponseFormat);
        Assert.Same(runOptionsResponseFormat, capturedResponseFormat);
        Assert.NotSame(chatOptionsResponseFormat, capturedResponseFormat);
    }

    [Fact]
    public async Task RunAsync_StructuredOutputResponse_IsAvailableAsTextOnAgentResponseAsync()
    {
        // Arrange
        Animal expectedAnimal = new() { FullName = "Wally the Walrus", Id = 1, Species = Species.Walrus };

        Mock<IChatClient> mockService = new();
        mockService.Setup(s => s
            .GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, JsonSerializer.Serialize(expectedAnimal, JsonContext4.Default.Animal)))
            {
                ResponseId = "test",
            });

        ChatResponseFormatJson responseFormat = ChatResponseFormat.ForJsonSchema<Animal>(JsonContext4.Default.Options);

        ChatClientAgent agent = new(mockService.Object, options: new ChatClientAgentOptions
        {
            ChatOptions = new ChatOptions()
            {
                ResponseFormat = responseFormat
            },
        });

        // Act
        AgentResponse agentResponse = await agent.RunAsync(messages: [new(ChatRole.User, "Hello")]);

        // Assert
        Assert.NotNull(agentResponse?.Text);

        Animal? deserialised = JsonSerializer.Deserialize(agentResponse.Text, JsonContext4.Default.Animal);
        Assert.NotNull(deserialised);
        Assert.Equal(expectedAnimal.Id, deserialised.Id);
        Assert.Equal(expectedAnimal.FullName, deserialised.FullName);
        Assert.Equal(expectedAnimal.Species, deserialised.Species);
    }

    [JsonSerializable(typeof(Animal))]
    private sealed partial class JsonContext4 : JsonSerializerContext;
}
