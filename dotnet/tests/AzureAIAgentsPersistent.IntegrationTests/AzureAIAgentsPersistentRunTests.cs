// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using AgentConformance.IntegrationTests;

namespace AzureAIAgentsPersistent.IntegrationTests;

[Trait("Category", "Integration")]
public class AzureAIAgentsPersistentRunTests() : RunTests<AzureAIAgentsPersistentFixture>(() => new())
{
    private const string SkipReason = "Flaky integration test";

    public override Task RunWithNoMessageDoesNotFailAsync()
    {
        Assert.Skip(SkipReason);
        return Task.CompletedTask;
    }

    public override Task RunWithStringReturnsExpectedResultAsync()
    {
        Assert.Skip(SkipReason);
        return Task.CompletedTask;
    }

    public override Task RunWithChatMessageReturnsExpectedResultAsync()
    {
        Assert.Skip(SkipReason);
        return Task.CompletedTask;
    }

    public override Task RunWithChatMessagesReturnsExpectedResultAsync()
    {
        Assert.Skip(SkipReason);
        return Task.CompletedTask;
    }

    public override Task SessionMaintainsHistoryAsync()
    {
        Assert.Skip(SkipReason);
        return Task.CompletedTask;
    }
}
