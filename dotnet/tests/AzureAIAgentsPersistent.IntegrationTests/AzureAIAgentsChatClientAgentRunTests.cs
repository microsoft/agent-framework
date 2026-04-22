// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using AgentConformance.IntegrationTests;

namespace AzureAIAgentsPersistent.IntegrationTests;

[Trait("Category", "Integration")]
public class AzureAIAgentsChatClientAgentRunTests() : ChatClientAgentRunTests<AzureAIAgentsPersistentFixture>(() => new())
{
    private const string SkipReason = "Flaky integration test";

    public override Task RunWithInstructionsAndNoMessageReturnsExpectedResultAsync()
    {
        Assert.SkipWhen(SkipReason is not null, SkipReason ?? string.Empty);
        return base.RunWithInstructionsAndNoMessageReturnsExpectedResultAsync();
    }

    public override Task RunWithFunctionsInvokesFunctionsAndReturnsExpectedResultsAsync()
    {
        Assert.SkipWhen(SkipReason is not null, SkipReason ?? string.Empty);
        return base.RunWithFunctionsInvokesFunctionsAndReturnsExpectedResultsAsync();
    }
}
