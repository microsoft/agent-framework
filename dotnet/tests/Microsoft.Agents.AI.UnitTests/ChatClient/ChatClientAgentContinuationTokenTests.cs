// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.UnitTests.ChatClient;

public class ChatClientAgentContinuationTokenTests
{
    [Fact]
    public void ToBytes_Roundtrip()
    {
        // Arrange
        ResponseContinuationToken originalToken = ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3, 4, 5 });

        ChatClientAgentContinuationToken chatClientToken = new(originalToken)
        {
            InputMessages =
            [
                new ChatMessage(ChatRole.User, "Hello!"),
                new ChatMessage(ChatRole.User, "How are you?")
            ],
            ResponseUpdates =
            [
                new ChatResponseUpdate(ChatRole.Assistant, "I'm fine, thank you."),
                new ChatResponseUpdate(ChatRole.Assistant, "How can I assist you today?")
            ]
        };

        // Act
        ReadOnlyMemory<byte> bytes = chatClientToken.ToBytes();

        ChatClientAgentContinuationToken tokenFromBytes = ChatClientAgentContinuationToken.FromToken(ResponseContinuationToken.FromBytes(bytes));

        // Assert
        Assert.NotNull(tokenFromBytes);
        Assert.Equal(chatClientToken.ToBytes().ToArray(), tokenFromBytes.ToBytes().ToArray());

        // Verify InnerToken
        Assert.Equal(chatClientToken.InnerToken.ToBytes().ToArray(), tokenFromBytes.InnerToken.ToBytes().ToArray());

        // Verify InputMessages
        Assert.NotNull(tokenFromBytes.InputMessages);
        Assert.Equal(chatClientToken.InputMessages.Count(), tokenFromBytes.InputMessages.Count());
        for (int i = 0; i < chatClientToken.InputMessages.Count(); i++)
        {
            Assert.Equal(chatClientToken.InputMessages.ElementAt(i).Role, tokenFromBytes.InputMessages.ElementAt(i).Role);
            Assert.Equal(chatClientToken.InputMessages.ElementAt(i).Text, tokenFromBytes.InputMessages.ElementAt(i).Text);
        }

        // Verify ResponseUpdates
        Assert.NotNull(tokenFromBytes.ResponseUpdates);
        Assert.Equal(chatClientToken.ResponseUpdates.Count, tokenFromBytes.ResponseUpdates.Count);
        for (int i = 0; i < chatClientToken.ResponseUpdates.Count; i++)
        {
            Assert.Equal(chatClientToken.ResponseUpdates.ElementAt(i).Role, tokenFromBytes.ResponseUpdates.ElementAt(i).Role);
            Assert.Equal(chatClientToken.ResponseUpdates.ElementAt(i).Text, tokenFromBytes.ResponseUpdates.ElementAt(i).Text);
        }
    }

    [Fact]
    public void Serialization_Roundtrip()
    {
        // Arrange
        ResponseContinuationToken originalToken = ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3, 4, 5 });

        ChatClientAgentContinuationToken chatClientToken = new(originalToken)
        {
            InputMessages =
            [
                new ChatMessage(ChatRole.User, "Hello!"),
                new ChatMessage(ChatRole.User, "How are you?")
            ],
            ResponseUpdates =
            [
                new ChatResponseUpdate(ChatRole.Assistant, "I'm fine, thank you."),
                new ChatResponseUpdate(ChatRole.Assistant, "How can I assist you today?")
            ]
        };

        // Act
        string json = JsonSerializer.Serialize(chatClientToken, AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(ResponseContinuationToken)));

        ResponseContinuationToken? deserializedToken = (ResponseContinuationToken?)JsonSerializer.Deserialize(json, AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(ResponseContinuationToken)));

        ChatClientAgentContinuationToken deserializedChatClientToken = ChatClientAgentContinuationToken.FromToken(deserializedToken!);

        // Assert
        Assert.NotNull(deserializedChatClientToken);
        Assert.Equal(chatClientToken.ToBytes().ToArray(), deserializedChatClientToken.ToBytes().ToArray());

        // Verify InnerToken
        Assert.Equal(chatClientToken.InnerToken.ToBytes().ToArray(), deserializedChatClientToken.InnerToken.ToBytes().ToArray());

        // Verify InputMessages
        Assert.NotNull(deserializedChatClientToken.InputMessages);
        Assert.Equal(chatClientToken.InputMessages.Count(), deserializedChatClientToken.InputMessages.Count());
        for (int i = 0; i < chatClientToken.InputMessages.Count(); i++)
        {
            Assert.Equal(chatClientToken.InputMessages.ElementAt(i).Role, deserializedChatClientToken.InputMessages.ElementAt(i).Role);
            Assert.Equal(chatClientToken.InputMessages.ElementAt(i).Text, deserializedChatClientToken.InputMessages.ElementAt(i).Text);
        }

        // Verify ResponseUpdates
        Assert.NotNull(deserializedChatClientToken.ResponseUpdates);
        Assert.Equal(chatClientToken.ResponseUpdates.Count, deserializedChatClientToken.ResponseUpdates.Count);
        for (int i = 0; i < chatClientToken.ResponseUpdates.Count; i++)
        {
            Assert.Equal(chatClientToken.ResponseUpdates.ElementAt(i).Role, deserializedChatClientToken.ResponseUpdates.ElementAt(i).Role);
            Assert.Equal(chatClientToken.ResponseUpdates.ElementAt(i).Text, deserializedChatClientToken.ResponseUpdates.ElementAt(i).Text);
        }
    }

    [Fact]
    public void FromToken_WithChatClientAgentContinuationToken_ReturnsSameInstance()
    {
        // Arrange
        ChatClientAgentContinuationToken originalToken = new(ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3, 4, 5 }));

        // Act
        ChatClientAgentContinuationToken fromToken = ChatClientAgentContinuationToken.FromToken(originalToken);

        // Assert
        Assert.Same(originalToken, fromToken);
    }
}
