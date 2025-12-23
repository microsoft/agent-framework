// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests;
using Microsoft.Agents.AI;

namespace AzureAI.IntegrationTests;

public class AIProjectClientAgentRunStreamingPreviousResponseTests() : RunStreamingTests<AIProjectClientFixture>(() => new())
{
    [Fact(Skip = "No messages is not supported")]
    public override Task RunWithNoMessageDoesNotFailAsync()
    {
        return Task.CompletedTask;
    }
}

public class AIProjectClientAgentRunStreamingConversationTests() : RunTests<AIProjectClientFixture>(() => new())
{
    public override Func<Task<AgentRunOptions?>> AgentRunOptionsFactory => async () =>
    {
        var conversationId = await this.Fixture.CreateConversationAsync();
        return new ChatClientAgentRunOptions(new() { ConversationId = conversationId });
    };

    [Fact(Skip = "No messages is not supported")]
    public override Task RunWithNoMessageDoesNotFailAsync()
    {
        return Task.CompletedTask;
    }
}
