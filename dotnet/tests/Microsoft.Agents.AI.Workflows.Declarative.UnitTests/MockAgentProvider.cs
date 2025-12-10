// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests;

/// <summary>
/// Mock implementation of <see cref="WorkflowAgentProvider"/> for unit testing purposes.
/// </summary>
internal sealed class MockAgentProvider : Mock<WorkflowAgentProvider>
{
    public IList<string> ExistingConversationIds { get; } = [];

    public List<ChatMessage>? TestMessages { get; set; }

    public MockAgentProvider()
    {
        this.Setup(provider => provider.CreateConversationAsync(It.IsAny<CancellationToken>()))
            .Returns(() => Task.FromResult(this.CreateConversationId()));

        List<ChatMessage> testMessages = this.CreateMessages();
        this.Setup(provider => provider.GetMessageAsync(
                It.IsAny<string>(),
                It.IsAny<string>(),
                It.IsAny<CancellationToken>()))
            .Returns(Task.FromResult(testMessages.First()));

        // Setup GetMessagesAsync to return test messages
        this.Setup(provider => provider.GetMessagesAsync(
                It.IsAny<string>(),
                It.IsAny<int?>(),
                It.IsAny<string?>(),
                It.IsAny<string?>(),
                It.IsAny<bool>(),
                It.IsAny<CancellationToken>()))
            .Returns(ToAsyncEnumerableAsync(testMessages));

        this.Setup(provider => provider.CreateMessageAsync(
                It.IsAny<string>(),
                It.IsAny<ChatMessage>(),
                It.IsAny<CancellationToken>()))
            .Returns(Task.FromResult(testMessages.First()));
    }

    private string CreateConversationId()
    {
        string newConversationId = Guid.NewGuid().ToString("N");
        this.ExistingConversationIds.Add(newConversationId);

        return newConversationId;
    }

    private List<ChatMessage> CreateMessages()
    {
        // Create test messages
        List<ChatMessage> messages = [];
        const int MessageCount = 5;
        for (int i = 0; i < MessageCount; i++)
        {
            messages.Add(new ChatMessage(ChatRole.User, $"Test message {i + 1}") { MessageId = Guid.NewGuid().ToString("N") });
        }
        this.TestMessages = messages;

        return this.TestMessages;
    }

    private static async IAsyncEnumerable<ChatMessage> ToAsyncEnumerableAsync(IEnumerable<ChatMessage> messages)
    {
        foreach (ChatMessage message in messages)
        {
            yield return message;
        }

        await Task.CompletedTask;
    }
}
