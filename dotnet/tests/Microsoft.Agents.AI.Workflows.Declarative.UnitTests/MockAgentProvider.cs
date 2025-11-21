// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
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

    public ChatMessage? TestChatMessage { get; set; }

    public MockAgentProvider()
    {
        this.Setup(provider => provider.CreateConversationAsync(It.IsAny<CancellationToken>()))
            .Returns(() => Task.FromResult(this.CreateConversationId()));

        this.Setup(provider => provider.GetMessageAsync(
                It.IsAny<string>(),
                It.IsAny<string>(),
                It.IsAny<CancellationToken>()))
            .Returns(Task.FromResult(this.CreateChatMessage()));
    }

    private string CreateConversationId()
    {
        string newConversationId = Guid.NewGuid().ToString("N");
        this.ExistingConversationIds.Add(newConversationId);

        return newConversationId;
    }

    private ChatMessage CreateChatMessage()
    {
        this.TestChatMessage = new ChatMessage(ChatRole.User, Guid.NewGuid().ToString("N"))
        {
            MessageId = Guid.NewGuid().ToString("N"),
        };
        return this.TestChatMessage;
    }
}
