// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

public class AgentRunResponseUpdateTests
{
    [Fact]
    public void ConstructorPropsDefaulted()
    {
        AgentRunResponseUpdate update = new();
        Assert.Null(update.AuthorName);
        Assert.Null(update.Role);
        Assert.Empty(update.Text);
        Assert.Empty(update.Contents);
        Assert.Null(update.RawRepresentation);
        Assert.Null(update.AdditionalProperties);
        Assert.Null(update.ResponseId);
        Assert.Null(update.MessageId);
        Assert.Null(update.CreatedAt);
        Assert.Equal(string.Empty, update.ToString());
        Assert.Null(update.ContinuationToken);
    }

    [Fact]
    public void ConstructorWithChatResponseUpdateRoundtrips()
    {
        ChatResponseUpdate chatResponseUpdate = new()
        {
            AdditionalProperties = [],
            AuthorName = "author",
            Contents = [new TextContent("hello")],
            ConversationId = "conversationId",
            CreatedAt = new DateTimeOffset(2022, 1, 1, 0, 0, 0, TimeSpan.Zero),
            FinishReason = ChatFinishReason.Length,
            MessageId = "messageId",
            ModelId = "modelId",
            RawRepresentation = new object(),
            ResponseId = "responseId",
            Role = ChatRole.Assistant,
            ContinuationToken = ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 }),
        };

        AgentRunResponseUpdate response = new(chatResponseUpdate);
        Assert.Same(chatResponseUpdate.AdditionalProperties, response.AdditionalProperties);
        Assert.Equal(chatResponseUpdate.AuthorName, response.AuthorName);
        Assert.Same(chatResponseUpdate.Contents, response.Contents);
        Assert.Equal(chatResponseUpdate.CreatedAt, response.CreatedAt);
        Assert.Equal(chatResponseUpdate.MessageId, response.MessageId);
        Assert.Same(chatResponseUpdate, response.RawRepresentation as ChatResponseUpdate);
        Assert.Equal(chatResponseUpdate.ResponseId, response.ResponseId);
        Assert.Equal(chatResponseUpdate.Role, response.Role);
        Assert.Same(chatResponseUpdate.ContinuationToken, response.ContinuationToken);
    }

    [Fact]
    public void PropertiesRoundtrip()
    {
        AgentRunResponseUpdate update = new();

        Assert.Null(update.AuthorName);
        update.AuthorName = "author";
        Assert.Equal("author", update.AuthorName);

        Assert.Null(update.Role);
        update.Role = ChatRole.Assistant;
        Assert.Equal(ChatRole.Assistant, update.Role);

        Assert.Empty(update.Contents);
        update.Contents.Add(new TextContent("text"));
        Assert.Single(update.Contents);
        Assert.Equal("text", update.Text);
        Assert.Same(update.Contents, update.Contents);
        IList<AIContent> newList = [new TextContent("text")];
        update.Contents = newList;
        Assert.Same(newList, update.Contents);
        update.Contents = null;
        Assert.NotNull(update.Contents);
        Assert.Empty(update.Contents);

        Assert.Empty(update.Text);

        Assert.Null(update.RawRepresentation);
        object raw = new();
        update.RawRepresentation = raw;
        Assert.Same(raw, update.RawRepresentation);

        Assert.Null(update.AdditionalProperties);
        AdditionalPropertiesDictionary props = new() { ["key"] = "value" };
        update.AdditionalProperties = props;
        Assert.Same(props, update.AdditionalProperties);

        Assert.Null(update.ResponseId);
        update.ResponseId = "id";
        Assert.Equal("id", update.ResponseId);

        Assert.Null(update.MessageId);
        update.MessageId = "messageid";
        Assert.Equal("messageid", update.MessageId);

        Assert.Null(update.CreatedAt);
        update.CreatedAt = new DateTimeOffset(2022, 1, 1, 0, 0, 0, TimeSpan.Zero);
        Assert.Equal(new DateTimeOffset(2022, 1, 1, 0, 0, 0, TimeSpan.Zero), update.CreatedAt);

        Assert.Null(update.ContinuationToken);
        update.ContinuationToken = ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 });
        Assert.Equivalent(ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 }), update.ContinuationToken);
    }

    [Fact]
    public void TextGetUsesAllTextContent()
    {
        AgentRunResponseUpdate update = new()
        {
            Role = ChatRole.User,
            Contents =
            [
                new DataContent("data:image/audio;base64,aGVsbG8="),
                new DataContent("data:image/image;base64,aGVsbG8="),
                new FunctionCallContent("callId1", "fc1"),
                new TextContent("text-1"),
                new TextContent("text-2"),
                new FunctionResultContent("callId1", "result"),
            ],
        };

        TextContent textContent = Assert.IsType<TextContent>(update.Contents[3]);
        Assert.Equal("text-1", textContent.Text);
        Assert.Equal("text-1text-2", update.Text);
        Assert.Equal("text-1text-2", update.ToString());

        ((TextContent)update.Contents[3]).Text = "text-3";
        Assert.Equal("text-3text-2", update.Text);
        Assert.Same(textContent, update.Contents[3]);
        Assert.Equal("text-3text-2", update.ToString());
    }

    [Fact]
    public void JsonSerializationRoundtrips()
    {
        AgentRunResponseUpdate original = new()
        {
            AuthorName = "author",
            Role = ChatRole.Assistant,
            Contents =
            [
                new TextContent("text-1"),
                new DataContent("data:image/png;base64,aGVsbG8="),
                new FunctionCallContent("callId1", "fc1"),
                new DataContent("data"u8.ToArray(), "text/plain"),
                new TextContent("text-2"),
            ],
            RawRepresentation = new object(),
            ResponseId = "id",
            MessageId = "messageid",
            CreatedAt = new DateTimeOffset(2022, 1, 1, 0, 0, 0, TimeSpan.Zero),
            AdditionalProperties = new() { ["key"] = "value" },
            ContinuationToken = ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 })
        };

        string json = JsonSerializer.Serialize(original, AgentAbstractionsJsonUtilities.DefaultOptions);

        AgentRunResponseUpdate? result = JsonSerializer.Deserialize<AgentRunResponseUpdate>(json, AgentAbstractionsJsonUtilities.DefaultOptions);

        Assert.NotNull(result);
        Assert.Equal(5, result.Contents.Count);

        Assert.IsType<TextContent>(result.Contents[0]);
        Assert.Equal("text-1", ((TextContent)result.Contents[0]).Text);

        Assert.IsType<DataContent>(result.Contents[1]);
        Assert.Equal("data:image/png;base64,aGVsbG8=", ((DataContent)result.Contents[1]).Uri);

        Assert.IsType<FunctionCallContent>(result.Contents[2]);
        Assert.Equal("fc1", ((FunctionCallContent)result.Contents[2]).Name);

        Assert.IsType<DataContent>(result.Contents[3]);
        Assert.Equal("data"u8.ToArray(), ((DataContent)result.Contents[3]).Data.ToArray());

        Assert.IsType<TextContent>(result.Contents[4]);
        Assert.Equal("text-2", ((TextContent)result.Contents[4]).Text);

        Assert.Equal("author", result.AuthorName);
        Assert.Equal(ChatRole.Assistant, result.Role);
        Assert.Equal("id", result.ResponseId);
        Assert.Equal("messageid", result.MessageId);
        Assert.Equal(new DateTimeOffset(2022, 1, 1, 0, 0, 0, TimeSpan.Zero), result.CreatedAt);

        Assert.NotNull(result.AdditionalProperties);
        Assert.Single(result.AdditionalProperties);
        Assert.True(result.AdditionalProperties.TryGetValue("key", out object? value));
        Assert.IsType<JsonElement>(value);
        Assert.Equal("value", ((JsonElement)value!).GetString());

        Assert.NotNull(result.ContinuationToken);
        Assert.Equivalent(ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 }), result.ContinuationToken);
    }
}
