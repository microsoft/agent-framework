// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using AgentConformance.IntegrationTests;

namespace CopilotStudio.IntegrationTests;

public class CopilotStudioRunTests() : RunTests<CopilotStudioFixture>(() => new())
{
    // Set to null to run the tests.
    private const string ManualVerification = "For manual verification";

    public override Task SessionMaintainsHistoryAsync()
    {
        Assert.Skip("Copilot Studio does not support session history retrieval, so this test is not applicable.");
        return base.SessionMaintainsHistoryAsync();
    }

    public override Task RunWithChatMessageReturnsExpectedResultAsync()
    {
        Assert.SkipWhen(ManualVerification is not null, ManualVerification ?? string.Empty);
        return base.RunWithChatMessageReturnsExpectedResultAsync();
    }

    public override Task RunWithChatMessagesReturnsExpectedResultAsync()
    {
        Assert.SkipWhen(ManualVerification is not null, ManualVerification ?? string.Empty);
        return base.RunWithChatMessagesReturnsExpectedResultAsync();
    }

    public override Task RunWithNoMessageDoesNotFailAsync()
    {
        Assert.SkipWhen(ManualVerification is not null, ManualVerification ?? string.Empty);
        return base.RunWithNoMessageDoesNotFailAsync();
    }

    public override Task RunWithStringReturnsExpectedResultAsync()
    {
        Assert.SkipWhen(ManualVerification is not null, ManualVerification ?? string.Empty);
        return base.RunWithStringReturnsExpectedResultAsync();
    }
}
