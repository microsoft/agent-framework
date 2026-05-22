// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using AgentConformance.IntegrationTests;

namespace Foundry.IntegrationTests;

public class FoundryVersionedAgentChatClientRunTests() : ChatClientAgentRunTests<FoundryVersionedAgentFixture>(() => new())
{
    public override Task RunWithInstructionsAndNoMessageReturnsExpectedResultAsync()
    {
        Assert.Skip("No messages is not supported");
        return base.RunWithInstructionsAndNoMessageReturnsExpectedResultAsync();
    }
}
