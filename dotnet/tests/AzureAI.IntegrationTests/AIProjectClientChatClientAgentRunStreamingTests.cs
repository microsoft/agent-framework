// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests;

namespace AzureAI.IntegrationTests;

#pragma warning disable CS0618 // Tests intentionally exercise obsolete AIProjectClientFixture
[Obsolete("Use FoundryVersionedAgentRunTests instead. These tests exercise obsolete AIProjectClient extension methods.")]
public class AIProjectClientChatClientAgentRunStreamingTests() : ChatClientAgentRunStreamingTests<AIProjectClientFixture>(() => new())
{
    public override Task RunWithInstructionsAndNoMessageReturnsExpectedResultAsync()
    {
        Assert.Skip("No messages is not supported");
        return base.RunWithInstructionsAndNoMessageReturnsExpectedResultAsync();
    }
}
