// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using AgentConformance.IntegrationTests;

namespace AzureAIAgentsPersistent.IntegrationTests;

[Trait("Category", "Integration")]
public class AzureAIAgentsPersistentRunStreamingTests() : RunStreamingTests<AzureAIAgentsPersistentFixture>(() => new())
{
    private const string SkipReason = "Flaky integration test";

    public override Task RunWithNoMessageDoesNotFailAsync()
    {
        Assert.SkipWhen(SkipReason is not null, SkipReason ?? string.Empty);
        return base.RunWithNoMessageDoesNotFailAsync();
    }

    public override Task RunWithStringReturnsExpectedResultAsync()
    {
        Assert.SkipWhen(SkipReason is not null, SkipReason ?? string.Empty);
        return base.RunWithStringReturnsExpectedResultAsync();
    }

    public override Task RunWithChatMessageReturnsExpectedResultAsync()
    {
        Assert.SkipWhen(SkipReason is not null, SkipReason ?? string.Empty);
        return base.RunWithChatMessageReturnsExpectedResultAsync();
    }

    public override Task RunWithChatMessagesReturnsExpectedResultAsync()
    {
        Assert.SkipWhen(SkipReason is not null, SkipReason ?? string.Empty);
        return base.RunWithChatMessagesReturnsExpectedResultAsync();
    }

    public override Task SessionMaintainsHistoryAsync()
    {
        Assert.SkipWhen(SkipReason is not null, SkipReason ?? string.Empty);
        return base.SessionMaintainsHistoryAsync();
    }
}
