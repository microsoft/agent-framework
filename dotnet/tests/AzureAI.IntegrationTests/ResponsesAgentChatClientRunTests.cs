// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using AgentConformance.IntegrationTests;

namespace AzureAI.IntegrationTests;

public class ResponsesAgentChatClientRunTests() : ChatClientAgentRunTests<ResponsesAgentFixture>(() => new())
{
    public override Task RunWithInstructionsAndNoMessageReturnsExpectedResultAsync()
    {
        Assert.Skip("No messages is not supported");
        return base.RunWithInstructionsAndNoMessageReturnsExpectedResultAsync();
    }
}
