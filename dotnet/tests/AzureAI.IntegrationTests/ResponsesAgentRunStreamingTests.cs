// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests;
using Microsoft.Agents.AI;

namespace AzureAI.IntegrationTests;

public class ResponsesAgentRunStreamingPreviousResponseTests() : RunStreamingTests<ResponsesAgentFixture>(() => new())
{
    public override Task RunWithNoMessageDoesNotFailAsync()
    {
        Assert.Skip("No messages is not supported");
        return base.RunWithNoMessageDoesNotFailAsync();
    }
}

public class ResponsesAgentRunStreamingConversationTests() : RunStreamingTests<ResponsesAgentFixture>(() => new())
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
