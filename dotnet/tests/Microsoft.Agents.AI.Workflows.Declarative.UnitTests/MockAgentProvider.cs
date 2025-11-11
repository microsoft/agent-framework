// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Moq;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests;

/// <summary>
/// Mock implementation of <see cref="WorkflowAgentProvider"/> for unit testing purposes.
/// </summary>
internal sealed class MockAgentProvider : Mock<WorkflowAgentProvider>
{
    public IList<string> ExistingConversationIds { get; } = [];

    public MockAgentProvider()
    {
        this.Setup(provider => provider.CreateConversationAsync(It.IsAny<CancellationToken>()))
            .Returns(() => Task.FromResult(this.CreateConversationId()));
    }

    private string CreateConversationId()
    {
        string newConversationId = Guid.NewGuid().ToString("N");
        this.ExistingConversationIds.Add(newConversationId);

        return newConversationId;
    }
}
