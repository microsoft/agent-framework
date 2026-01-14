// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Microsoft.Agents.AI.Abstractions.UnitTests.Models;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

public class AgentResponseTests
{
    [Fact]
    public void ConstructorWithNullEmptyArgsIsValid()
    {
        AgentResponse response;

        response = new();
        Assert.Empty(response.Messages);
        Assert.Empty(response.Text);
        Assert.Null(response.ContinuationToken);

        response = new((IList<ChatMessage>?)null);
        Assert.Empty(response.Messages);
        Assert.Empty(response.Text);
        Assert.Null(response.ContinuationToken);

        Assert.Throws<ArgumentNullException>("message", () => new AgentResponse((ChatMessage)null!));
    }

    [Fact]
    public void ConstructorWithMessagesRoundtrips()
    {
        AgentResponse response = new();
        Assert.NotNull(response.Messages);
        Assert.Same(response.Messages, response.Messages);

        List<ChatMessage> messages = [];
        response = new(messages);
        Assert.Same(messages, response.Messages);

        messages = [];
        Assert.NotSame(messages, response.Messages);
        response.Messages = messages;
        Assert.Same(messages, response.Messages);
    }

    [Fact]
    public void ConstructorWithChatResponseRoundtrips()
    {
        ChatResponse chatResponse = new()
        {
            AdditionalProperties = [],
            CreatedAt = new DateTimeOffset(2022, 1, 1, 0, 0, 0, TimeSpan.Zero),
            Messages = [new(ChatRole.Assistant, "This is a test message.")],
            RawRepresentation = new object(),
            ResponseId = "responseId",
            Usage = new UsageDetails(),
            ContinuationToken = ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 })
        };

        AgentResponse response = new(chatResponse);
        Assert.Same(chatResponse.AdditionalProperties, response.AdditionalProperties);
        Assert.Equal(chatResponse.CreatedAt, response.CreatedAt);
        Assert.Same(chatResponse.Messages, response.Messages);
        Assert.Equal(chatResponse.ResponseId, response.ResponseId);
        Assert.Same(chatResponse, response.RawRepresentation as ChatResponse);
        Assert.Same(chatResponse.Usage, response.Usage);
        Assert.Equivalent(ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 }), response.ContinuationToken);
    }

    [Fact]
    public void PropertiesRoundtrip()
    {
        AgentResponse response = new();

        Assert.Null(response.AgentId);
        response.AgentId = "agentId";
        Assert.Equal("agentId", response.AgentId);

        Assert.Null(response.ResponseId);
        response.ResponseId = "id";
        Assert.Equal("id", response.ResponseId);

        Assert.Null(response.CreatedAt);
        response.CreatedAt = new DateTimeOffset(2022, 1, 1, 0, 0, 0, TimeSpan.Zero);
        Assert.Equal(new DateTimeOffset(2022, 1, 1, 0, 0, 0, TimeSpan.Zero), response.CreatedAt);

        Assert.Null(response.Usage);
        UsageDetails usage = new();
        response.Usage = usage;
        Assert.Same(usage, response.Usage);

        Assert.Null(response.RawRepresentation);
        object raw = new();
        response.RawRepresentation = raw;
        Assert.Same(raw, response.RawRepresentation);

        Assert.Null(response.AdditionalProperties);
        AdditionalPropertiesDictionary additionalProps = [];
        response.AdditionalProperties = additionalProps;
        Assert.Same(additionalProps, response.AdditionalProperties);

        Assert.Null(response.ContinuationToken);
        response.ContinuationToken = ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 });
        Assert.Equivalent(ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 }), response.ContinuationToken);
    }

    [Fact]
    public void JsonSerializationRoundtrips()
    {
        AgentResponse original = new(new ChatMessage(ChatRole.Assistant, "the message"))
        {
            AgentId = "agentId",
            ResponseId = "id",
            CreatedAt = new DateTimeOffset(2022, 1, 1, 0, 0, 0, TimeSpan.Zero),
            Usage = new UsageDetails(),
            RawRepresentation = new(),
            AdditionalProperties = new() { ["key"] = "value" },
            ContinuationToken = ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 }),
        };

        string json = JsonSerializer.Serialize(original, AgentAbstractionsJsonUtilities.DefaultOptions);

        AgentResponse? result = JsonSerializer.Deserialize<AgentResponse>(json, AgentAbstractionsJsonUtilities.DefaultOptions);

        Assert.NotNull(result);
        Assert.Equal(ChatRole.Assistant, result.Messages.Single().Role);
        Assert.Equal("the message", result.Messages.Single().Text);

        Assert.Equal("agentId", result.AgentId);
        Assert.Equal("id", result.ResponseId);
        Assert.Equal(new DateTimeOffset(2022, 1, 1, 0, 0, 0, TimeSpan.Zero), result.CreatedAt);
        Assert.NotNull(result.Usage);

        Assert.NotNull(result.AdditionalProperties);
        Assert.Single(result.AdditionalProperties);
        Assert.True(result.AdditionalProperties.TryGetValue("key", out object? value));
        Assert.IsType<JsonElement>(value);
        Assert.Equal("value", ((JsonElement)value!).GetString());
        Assert.Equivalent(ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 }), result.ContinuationToken);
    }

    [Fact]
    public void ToStringOutputsText()
    {
        AgentResponse response = new(new ChatMessage(ChatRole.Assistant, $"This is a test.{Environment.NewLine}It's multiple lines."));

        Assert.Equal(response.Text, response.ToString());
    }

    [Fact]
    public void TextGetConcatenatesAllTextContent()
    {
        AgentResponse response = new(
        [
            new ChatMessage(
                ChatRole.Assistant,
                [
                    new DataContent("data:image/audio;base64,aGVsbG8="),
                    new DataContent("data:image/image;base64,aGVsbG8="),
                    new FunctionCallContent("callId1", "fc1"),
                    new TextContent("message1-text-1"),
                    new TextContent("message1-text-2"),
                    new FunctionResultContent("callId1", "result"),
                ]),
            new ChatMessage(ChatRole.Assistant, "message2")
        ]);

        Assert.Equal($"message1-text-1message1-text-2{Environment.NewLine}message2", response.Text);
    }

    [Fact]
    public void TextGetReturnsEmptyStringWithNoMessages()
    {
        AgentResponse response = new();

        Assert.Equal(string.Empty, response.Text);
    }

    [Fact]
    public void ToAgentResponseUpdatesProducesUpdates()
    {
        AgentResponse response = new(new ChatMessage(new ChatRole("customRole"), "Text") { MessageId = "someMessage" })
        {
            AgentId = "agentId",
            ResponseId = "12345",
            CreatedAt = new DateTimeOffset(2024, 11, 10, 9, 20, 0, TimeSpan.Zero),
            AdditionalProperties = new() { ["key1"] = "value1", ["key2"] = 42 },
            Usage = new UsageDetails
            {
                TotalTokenCount = 100
            },
        };

        AgentResponseUpdate[] updates = response.ToAgentResponseUpdates();
        Assert.NotNull(updates);
        Assert.Equal(2, updates.Length);

        AgentResponseUpdate update0 = updates[0];
        Assert.Equal("agentId", update0.AgentId);
        Assert.Equal("12345", update0.ResponseId);
        Assert.Equal("someMessage", update0.MessageId);
        Assert.Equal(new DateTimeOffset(2024, 11, 10, 9, 20, 0, TimeSpan.Zero), update0.CreatedAt);
        Assert.Equal("customRole", update0.Role?.Value);
        Assert.Equal("Text", update0.Text);

        AgentResponseUpdate update1 = updates[1];
        Assert.Equal("value1", update1.AdditionalProperties?["key1"]);
        Assert.Equal(42, update1.AdditionalProperties?["key2"]);
        Assert.IsType<UsageContent>(update1.Contents[0]);
        UsageContent usageContent = (UsageContent)update1.Contents[0];
        Assert.Equal(100, usageContent.Details.TotalTokenCount);
    }

#if NETFRAMEWORK
    /// <summary>
    /// Since Json Serialization using reflection is disabled in .net core builds, and we are using a custom type here that wouldn't
    /// be registered with the default source generated serializer, this test will only pass in .net framework builds where reflection-based
    /// serialization is available.
    /// </summary>
    [Fact]
    public void ParseAsStructuredOutputSuccess()
    {
        // Arrange.
        var expectedResult = new Animal { Id = 1, FullName = "Tigger", Species = Species.Tiger };
        var response = new AgentResponse(new ChatMessage(ChatRole.Assistant, JsonSerializer.Serialize(expectedResult, TestJsonSerializerContext.Default.Animal)));

        // Act.
        var animal = response.Deserialize<Animal>();

        // Assert.
        Assert.NotNull(animal);
        Assert.Equal(expectedResult.Id, animal.Id);
        Assert.Equal(expectedResult.FullName, animal.FullName);
        Assert.Equal(expectedResult.Species, animal.Species);
    }
#endif

    [Fact]
    public void ParseAsStructuredOutputWithJSOSuccess()
    {
        // Arrange.
        var expectedResult = new Animal { Id = 1, FullName = "Tigger", Species = Species.Tiger };
        var response = new AgentResponse(new ChatMessage(ChatRole.Assistant, JsonSerializer.Serialize(expectedResult, TestJsonSerializerContext.Default.Animal)));

        // Act.
        var animal = response.Deserialize<Animal>(TestJsonSerializerContext.Default.Options);

        // Assert.
        Assert.NotNull(animal);
        Assert.Equal(expectedResult.Id, animal.Id);
        Assert.Equal(expectedResult.FullName, animal.FullName);
        Assert.Equal(expectedResult.Species, animal.Species);
    }

    [Fact]
    public void ParseAsStructuredOutputFailsWithEmptyString()
    {
        // Arrange.
        var response = new AgentResponse(new ChatMessage(ChatRole.Assistant, string.Empty));

        // Act & Assert.
        var exception = Assert.Throws<InvalidOperationException>(() => response.Deserialize<Animal>(TestJsonSerializerContext.Default.Options));
        Assert.Equal("The response did not contain JSON to be deserialized.", exception.Message);
    }

    [Fact]
    public void ParseAsStructuredOutputFailsWithInvalidJson()
    {
        // Arrange.
        var response = new AgentResponse(new ChatMessage(ChatRole.Assistant, "invalid json"));

        // Act & Assert.
        Assert.Throws<JsonException>(() => response.Deserialize<Animal>(TestJsonSerializerContext.Default.Options));
    }

    [Fact]
    public void ParseAsStructuredOutputFailsWithIncorrectTypedJson()
    {
        // Arrange.
        var response = new AgentResponse(new ChatMessage(ChatRole.Assistant, "[]"));

        // Act & Assert.
        Assert.Throws<JsonException>(() => response.Deserialize<Animal>(TestJsonSerializerContext.Default.Options));
    }

#if NETFRAMEWORK
    /// <summary>
    /// Since Json Serialization using reflection is disabled in .net core builds, and we are using a custom type here that wouldn't
    /// be registered with the default source generated serializer, this test will only pass in .net framework builds where reflection-based
    /// serialization is available.
    /// </summary>
    [Fact]
    public void TryParseAsStructuredOutputSuccess()
    {
        // Arrange.
        var expectedResult = new Animal { Id = 1, FullName = "Tigger", Species = Species.Tiger };
        var response = new AgentResponse(new ChatMessage(ChatRole.Assistant, JsonSerializer.Serialize(expectedResult, TestJsonSerializerContext.Default.Animal)));

        // Act.
        response.TryDeserialize(out Animal? animal);

        // Assert.
        Assert.NotNull(animal);
        Assert.Equal(expectedResult.Id, animal.Id);
        Assert.Equal(expectedResult.FullName, animal.FullName);
        Assert.Equal(expectedResult.Species, animal.Species);
    }
#endif

    [Fact]
    public void TryParseAsStructuredOutputWithJSOSuccess()
    {
        // Arrange.
        var expectedResult = new Animal { Id = 1, FullName = "Tigger", Species = Species.Tiger };
        var response = new AgentResponse(new ChatMessage(ChatRole.Assistant, JsonSerializer.Serialize(expectedResult, TestJsonSerializerContext.Default.Animal)));

        // Act.
        response.TryDeserialize(TestJsonSerializerContext.Default.Options, out Animal? animal);

        // Assert.
        Assert.NotNull(animal);
        Assert.Equal(expectedResult.Id, animal.Id);
        Assert.Equal(expectedResult.FullName, animal.FullName);
        Assert.Equal(expectedResult.Species, animal.Species);
    }

    [Fact]
    public void TryParseAsStructuredOutputFailsWithEmptyText()
    {
        // Arrange.
        var response = new AgentResponse(new ChatMessage(ChatRole.Assistant, string.Empty));

        // Act & Assert.
        Assert.False(response.TryDeserialize<Animal>(TestJsonSerializerContext.Default.Options, out _));
    }

    [Fact]
    public void TryParseAsStructuredOutputFailsWithIncorrectTypedJson()
    {
        // Arrange.
        var response = new AgentResponse(new ChatMessage(ChatRole.Assistant, "[]"));

        // Act & Assert.
        Assert.False(response.TryDeserialize<Animal>(TestJsonSerializerContext.Default.Options, out _));
    }
}
