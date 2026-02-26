// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

public partial class ChatClientAgent_StructuredOutput_WithRunAsyncTests
{
    [Fact]
    public async Task RunAsync_WithGenericType_SetsJsonSchemaResponseFormatAndDeserializesResultAsync()
    {
        // Arrange
        ChatResponseFormat? capturedResponseFormat = null;
        ChatResponseFormatJson expectedResponseFormat = ChatResponseFormat.ForJsonSchema<Animal>(JsonContext3.Default.Options);
        Animal expectedSO = new() { Id = 1, FullName = "Tigger", Species = Species.Tiger };

        Mock<IChatClient> mockService = new();
        mockService.Setup(s => s
            .GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((msgs, opts, ct) => capturedResponseFormat = opts?.ResponseFormat)
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, JsonSerializer.Serialize(expectedSO, JsonContext3.Default.Animal)))
            {
                ResponseId = "test",
            });

        ChatClientAgent agent = new(mockService.Object);

        // Act
        AgentResponse<Animal> agentResponse = await agent.RunAsync<Animal>(
            messages: [new(ChatRole.User, "Hello")],
            serializerOptions: JsonContext3.Default.Options);

        // Assert
        Assert.NotNull(capturedResponseFormat);
        Assert.Equal(expectedResponseFormat.Schema?.GetRawText(), ((ChatResponseFormatJson)capturedResponseFormat).Schema?.GetRawText());

        Animal animal = agentResponse.Result;
        Assert.NotNull(animal);
        Assert.Equal(expectedSO.Id, animal.Id);
        Assert.Equal(expectedSO.FullName, animal.FullName);
        Assert.Equal(expectedSO.Species, animal.Species);
    }

    [JsonSourceGenerationOptions(UseStringEnumConverter = true, PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase)]
    [JsonSerializable(typeof(Animal))]
    private sealed partial class JsonContext3 : JsonSerializerContext;
}
