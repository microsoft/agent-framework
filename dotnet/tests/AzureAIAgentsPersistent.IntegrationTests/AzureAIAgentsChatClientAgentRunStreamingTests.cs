// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using AgentConformance.IntegrationTests;

namespace AzureAIAgentsPersistent.IntegrationTests;

[Trait("Category", "Integration")]
public class AzureAIAgentsChatClientAgentRunStreamingTests() : ChatClientAgentRunStreamingTests<AzureAIAgentsPersistentFixture>(() => new())
{
    private const string SkipReason = "Flaky integration test";

    public override Task RunWithInstructionsAndNoMessageReturnsExpectedResultAsync()
    {
        Assert.Skip(SkipReason);
        return Task.CompletedTask;
    }

    public override Task RunWithFunctionsInvokesFunctionsAndReturnsExpectedResultsAsync()
    {
        Assert.Skip(SkipReason);
        return Task.CompletedTask;
    }
}
