// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Abstractions.UnitTests.Models;
using Microsoft.Extensions.AI;
using Moq;
using Moq.Protected;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Unit tests for the structured output functionality in <see cref="AIAgent"/>.
/// </summary>
public class AIAgentStructuredOutputTests
{
    private readonly Mock<AIAgent> _agentMock;

    public AIAgentStructuredOutputTests()
    {
        this._agentMock = new Mock<AIAgent> { CallBase = true };
    }

    #region Schema Wrapping Tests

    /// <summary>
    /// Verifies that when requesting an object type, the schema is NOT wrapped.
    /// </summary>
    [Fact]
    public async Task RunAsyncGeneric_WithObjectType_DoesNotWrapSchemaAsync()
    {
        // Arrange
        Animal expectedAnimal = new() { Id = 1, FullName = "Test", Species = Species.Tiger };
        string responseJson = JsonSerializer.Serialize(expectedAnimal, TestJsonSerializerContext.Default.Animal);
        AgentResponse response = new(new ChatMessage(ChatRole.Assistant, responseJson));

        this._agentMock
            .Protected()
            .Setup<Task<AgentResponse>>("RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(response);

        // Act
        AgentResponse<Animal> result = await this._agentMock.Object.RunAsync<Animal>(
            "Get me an animal",
            serializerOptions: TestJsonSerializerContext.Default.Options);

        // Assert - Verify the result is NOT marked as wrapped
        Assert.False(result.IsWrappedInObject);
    }

    /// <summary>
    /// Verifies that when requesting a primitive type (int), the schema IS wrapped.
    /// </summary>
    [Fact]
    public async Task RunAsyncGeneric_WithPrimitiveType_WrapsSchemaAsync()
    {
        // Arrange
        const string ResponseJson = "{\"data\":42}";
        AgentResponse response = new(new ChatMessage(ChatRole.Assistant, ResponseJson));

        this._agentMock
            .Protected()
            .Setup<Task<AgentResponse>>("RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(response);

        // Act
        AgentResponse<int> result = await this._agentMock.Object.RunAsync<int>(
            "Give me a number",
            serializerOptions: TestJsonSerializerContext.Default.Options);

        // Assert - Verify the result is marked as wrapped
        Assert.True(result.IsWrappedInObject);
    }

    /// <summary>
    /// Verifies that when requesting an array type, the schema IS wrapped.
    /// </summary>
    [Fact]
    public async Task RunAsyncGeneric_WithArrayType_WrapsSchemaAsync()
    {
        // Arrange
        const string ResponseJson = "{\"data\":[\"a\",\"b\",\"c\"]}";
        AgentResponse response = new(new ChatMessage(ChatRole.Assistant, ResponseJson));

        this._agentMock
            .Protected()
            .Setup<Task<AgentResponse>>("RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(response);

        // Act
        AgentResponse<string[]> result = await this._agentMock.Object.RunAsync<string[]>(
            "Give me an array of strings",
            serializerOptions: TestJsonSerializerContext.Default.Options);

        // Assert - Verify the result is marked as wrapped
        Assert.True(result.IsWrappedInObject);
    }

    /// <summary>
    /// Verifies that when requesting an enum type, the schema IS wrapped.
    /// </summary>
    [Fact]
    public async Task RunAsyncGeneric_WithEnumType_WrapsSchemaAsync()
    {
        // Arrange
        const string ResponseJson = "{\"data\":\"Tiger\"}";
        AgentResponse response = new(new ChatMessage(ChatRole.Assistant, ResponseJson));

        this._agentMock
            .Protected()
            .Setup<Task<AgentResponse>>("RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(response);

        // Act
        AgentResponse<Species> result = await this._agentMock.Object.RunAsync<Species>(
            "Give me a species",
            serializerOptions: TestJsonSerializerContext.Default.Options);

        // Assert - Verify the result is marked as wrapped
        Assert.True(result.IsWrappedInObject);
    }

    #endregion

    #region AgentResponse<T>.Result Unwrapping Tests

    /// <summary>
    /// Verifies that AgentResponse{T}.Result correctly deserializes an object without unwrapping.
    /// </summary>
    [Fact]
    public void AgentResponseGeneric_Result_DeserializesObjectWithoutUnwrapping()
    {
        // Arrange
        Animal expectedAnimal = new() { Id = 1, FullName = "Tigger", Species = Species.Tiger };
        string responseJson = JsonSerializer.Serialize(expectedAnimal, TestJsonSerializerContext.Default.Animal);
        AgentResponse response = new(new ChatMessage(ChatRole.Assistant, responseJson));
        AgentResponse<Animal> typedResponse = new(response, TestJsonSerializerContext.Default.Options);

        // Act
        Animal result = typedResponse.Result;

        // Assert
        Assert.Equal(expectedAnimal.Id, result.Id);
        Assert.Equal(expectedAnimal.FullName, result.FullName);
        Assert.Equal(expectedAnimal.Species, result.Species);
    }

    /// <summary>
    /// Verifies that AgentResponse{T}.Result correctly unwraps and deserializes a primitive value.
    /// </summary>
    [Fact]
    public void AgentResponseGeneric_Result_UnwrapsPrimitiveFromDataProperty()
    {
        // Arrange
        const string ResponseJson = "{\"data\":42}";
        AgentResponse response = new(new ChatMessage(ChatRole.Assistant, ResponseJson));
        AgentResponse<int> typedResponse = new(response, TestJsonSerializerContext.Default.Options) { IsWrappedInObject = true };

        // Act
        int result = typedResponse.Result;

        // Assert
        Assert.Equal(42, result);
    }

    /// <summary>
    /// Verifies that AgentResponse{T}.Result correctly unwraps and deserializes an array.
    /// </summary>
    [Fact]
    public void AgentResponseGeneric_Result_UnwrapsArrayFromDataProperty()
    {
        // Arrange
        const string ResponseJson = "{\"data\":[\"apple\",\"banana\",\"cherry\"]}";
        AgentResponse response = new(new ChatMessage(ChatRole.Assistant, ResponseJson));
        AgentResponse<string[]> typedResponse = new(response, TestJsonSerializerContext.Default.Options) { IsWrappedInObject = true };

        // Act
        string[] result = typedResponse.Result;

        // Assert
        Assert.Equal(["apple", "banana", "cherry"], result);
    }

    /// <summary>
    /// Verifies that AgentResponse{T}.Result correctly unwraps and deserializes an enum.
    /// </summary>
    [Fact]
    public void AgentResponseGeneric_Result_UnwrapsEnumFromDataProperty()
    {
        // Arrange
        const string ResponseJson = "{\"data\":\"Walrus\"}";
        AgentResponse response = new(new ChatMessage(ChatRole.Assistant, ResponseJson));
        AgentResponse<Species> typedResponse = new(response, TestJsonSerializerContext.Default.Options) { IsWrappedInObject = true };

        // Act
        Species result = typedResponse.Result;

        // Assert
        Assert.Equal(Species.Walrus, result);
    }

    /// <summary>
    /// Verifies that AgentResponse{T}.Result falls back to original JSON when data property is missing.
    /// </summary>
    [Fact]
    public void AgentResponseGeneric_Result_FallsBackWhenDataPropertyMissing()
    {
        // Arrange - simulate a case where wrapping was expected but response does not have data
        const string ResponseJson = "42";
        AgentResponse response = new(new ChatMessage(ChatRole.Assistant, ResponseJson));
        AgentResponse<int> typedResponse = new(response, TestJsonSerializerContext.Default.Options) { IsWrappedInObject = true };

        // Act
        int result = typedResponse.Result;

        // Assert - should still work by falling back to original JSON
        Assert.Equal(42, result);
    }

    /// <summary>
    /// Verifies that AgentResponse{T}.Result throws when response text is empty.
    /// </summary>
    [Fact]
    public void AgentResponseGeneric_Result_ThrowsWhenTextIsEmpty()
    {
        // Arrange
        AgentResponse response = new(new ChatMessage(ChatRole.Assistant, string.Empty));
        AgentResponse<int> typedResponse = new(response, TestJsonSerializerContext.Default.Options);

        // Act and Assert
        Assert.Throws<System.InvalidOperationException>(() => typedResponse.Result);
    }

    /// <summary>
    /// Verifies that AgentResponse{T}.Result throws when deserialized value is null.
    /// </summary>
    [Fact]
    public void AgentResponseGeneric_Result_ThrowsWhenDeserializedValueIsNull()
    {
        // Arrange
        const string ResponseJson = "null";
        AgentResponse response = new(new ChatMessage(ChatRole.Assistant, ResponseJson));
        AgentResponse<Animal> typedResponse = new(response, TestJsonSerializerContext.Default.Options);

        // Act and Assert
        Assert.Throws<System.InvalidOperationException>(() => typedResponse.Result);
    }

    #endregion

    #region End-to-End Tests

    /// <summary>
    /// End-to-end test: Request a primitive type, verify wrapping, and verify correct deserialization.
    /// </summary>
    [Fact]
    public async Task RunAsyncGeneric_PrimitiveEndToEnd_WrapsAndDeserializesCorrectlyAsync()
    {
        // Arrange
        const string ResponseJson = "{\"data\":123}";
        AgentResponse response = new(new ChatMessage(ChatRole.Assistant, ResponseJson));

        this._agentMock
            .Protected()
            .Setup<Task<AgentResponse>>("RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(response);

        // Act
        AgentResponse<int> result = await this._agentMock.Object.RunAsync<int>(
            "Give me a number",
            serializerOptions: TestJsonSerializerContext.Default.Options);

        // Assert
        Assert.True(result.IsWrappedInObject);
        Assert.Equal(123, result.Result);
    }

    /// <summary>
    /// End-to-end test: Request an array type, verify wrapping, and verify correct deserialization.
    /// </summary>
    [Fact]
    public async Task RunAsyncGeneric_ArrayEndToEnd_WrapsAndDeserializesCorrectlyAsync()
    {
        // Arrange
        const string ResponseJson = "{\"data\":[\"one\",\"two\",\"three\"]}";
        AgentResponse response = new(new ChatMessage(ChatRole.Assistant, ResponseJson));

        this._agentMock
            .Protected()
            .Setup<Task<AgentResponse>>("RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(response);

        // Act
        AgentResponse<string[]> result = await this._agentMock.Object.RunAsync<string[]>(
            "Give me an array of strings",
            serializerOptions: TestJsonSerializerContext.Default.Options);

        // Assert
        Assert.True(result.IsWrappedInObject);
        Assert.Equal(["one", "two", "three"], result.Result);
    }

    /// <summary>
    /// End-to-end test: Request an object type, verify no wrapping, and verify correct deserialization.
    /// </summary>
    [Fact]
    public async Task RunAsyncGeneric_ObjectEndToEnd_NoWrappingAndDeserializesCorrectlyAsync()
    {
        // Arrange
        Animal expectedAnimal = new() { Id = 99, FullName = "Leo", Species = Species.Bear };
        string responseJson = JsonSerializer.Serialize(expectedAnimal, TestJsonSerializerContext.Default.Animal);
        AgentResponse response = new(new ChatMessage(ChatRole.Assistant, responseJson));

        this._agentMock
            .Protected()
            .Setup<Task<AgentResponse>>("RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(response);

        // Act
        AgentResponse<Animal> result = await this._agentMock.Object.RunAsync<Animal>(
            "Give me an animal",
            serializerOptions: TestJsonSerializerContext.Default.Options);

        // Assert
        Assert.False(result.IsWrappedInObject);
        Assert.Equal(expectedAnimal.Id, result.Result.Id);
        Assert.Equal(expectedAnimal.FullName, result.Result.FullName);
        Assert.Equal(expectedAnimal.Species, result.Result.Species);
    }

    /// <summary>
    /// End-to-end test: Request an enum type, verify wrapping, and verify correct deserialization.
    /// </summary>
    [Fact]
    public async Task RunAsyncGeneric_EnumEndToEnd_WrapsAndDeserializesCorrectlyAsync()
    {
        // Arrange
        const string ResponseJson = "{\"data\":\"Bear\"}";
        AgentResponse response = new(new ChatMessage(ChatRole.Assistant, ResponseJson));

        this._agentMock
            .Protected()
            .Setup<Task<AgentResponse>>("RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(response);

        // Act
        AgentResponse<Species> result = await this._agentMock.Object.RunAsync<Species>(
            "Give me a species",
            serializerOptions: TestJsonSerializerContext.Default.Options);

        // Assert
        Assert.True(result.IsWrappedInObject);
        Assert.Equal(Species.Bear, result.Result);
    }

    #endregion
}
