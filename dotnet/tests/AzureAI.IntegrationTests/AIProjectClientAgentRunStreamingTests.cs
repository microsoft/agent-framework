// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests;
using Microsoft.Agents.AI;

namespace AzureAI.IntegrationTests;

#pragma warning disable CS0618 // Tests intentionally exercise obsolete AIProjectClientFixture
[Obsolete("Use FoundryVersionedAgentRunTests instead. These tests exercise obsolete AIProjectClient extension methods.")]
public class AIProjectClientAgentRunStreamingPreviousResponseTests() : RunStreamingTests<AIProjectClientFixture>(() => new())
{
    public override Task RunWithNoMessageDoesNotFailAsync()
    {
        Assert.Skip("No messages is not supported");
        return base.RunWithNoMessageDoesNotFailAsync();
    }
}

[Obsolete("Use FoundryVersionedAgentRunTests instead. These tests exercise obsolete AIProjectClient extension methods.")]
public class AIProjectClientAgentRunStreamingConversationTests() : RunStreamingTests<AIProjectClientFixture>(() => new())
{
    public override Func<Task<AgentRunOptions?>> AgentRunOptionsFactory => async () =>
    {
        var conversationId = await this.Fixture.CreateConversationAsync();
        return new ChatClientAgentRunOptions(new() { ConversationId = conversationId });
    };

    public override Task RunWithNoMessageDoesNotFailAsync()
    {
        Assert.Skip("No messages is not supported");
        return base.RunWithNoMessageDoesNotFailAsync();
    }
}
