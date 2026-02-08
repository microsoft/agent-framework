// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using AgentConformance.IntegrationTests;

namespace AzureAI.IntegrationTests;

public class AIProjectClientChatClientAgentRunStreamingTests() : ChatClientAgentRunStreamingTests<AIProjectClientFixture>(() => new())
{
    [Fact(Skip = "No messages is not supported")]
    public override Task RunWithInstructionsAndNoMessageReturnsExpectedResultAsync()
    {
        return Task.CompletedTask;
    }
}
