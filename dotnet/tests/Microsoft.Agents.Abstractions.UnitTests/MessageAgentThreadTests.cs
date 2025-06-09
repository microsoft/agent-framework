// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.Abstractions.UnitTests;

/// <summary>
/// Contains tests for the <see cref="MessageAgentThread"/> class.
/// </summary>
public class MessageAgentThreadTests
{
    /// <summary>
    /// Tests that the GetService method returns the correct instance or null as expected.
    /// </summary>
    [Fact]
    public void GetServiceShouldReturnSelfOrNull()
    {
        // Arrange
        var thread = new TestMessageAgentThread();

        // Should return itself when type matches MessageAgentThread and serviceKey is null
        var result = thread.GetService(typeof(MessageAgentThread));
        Assert.Same(thread, result);

        // Should return null for unrelated type
        var unrelated = thread.GetService(typeof(string));
        Assert.Null(unrelated);

        // Should return null if serviceKey is not null
        var withKey = thread.GetService(typeof(MessageAgentThread), serviceKey: "key");
        Assert.Null(withKey);

        // Should call base for AgentThread (returns itself, since base does)
        var baseResult = thread.GetService(typeof(AgentThread));
        Assert.Same(thread, baseResult);
    }

    private sealed class TestMessageAgentThread : MessageAgentThread
    {
        protected override Task<string?> CreateCoreAsync(CancellationToken cancellationToken)
            => Task.FromResult<string?>("test-thread-id");

        protected override Task DeleteCoreAsync(CancellationToken cancellationToken)
            => Task.CompletedTask;

        protected override Task OnNewMessageCoreAsync(ChatMessage newMessage, CancellationToken cancellationToken = default)
            => Task.CompletedTask;

        public override IAsyncEnumerable<ChatMessage> GetMessagesAsync(CancellationToken cancellationToken = default)
        {
            return Array.Empty<ChatMessage>().ToAsyncEnumerable();
        }
    }
}
