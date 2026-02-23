// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Contains unit tests for the ChatClientAgent.CreateSessionAsync methods.
/// </summary>
public class ChatClientAgent_CreateSessionTests
{
    [Fact]
    public async Task CreateSession_UsesConversationId_FromTypedOverloadAsync()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        const string TestConversationId = "test_conversation_id";
        var agent = new ChatClientAgent(mockChatClient.Object);

        // Act
        var session = await agent.CreateSessionAsync(TestConversationId);

        // Assert
        Assert.IsType<ChatClientAgentSession>(session);
        var typedSession = (ChatClientAgentSession)session;
        Assert.Equal(TestConversationId, typedSession.ConversationId);
    }
}
