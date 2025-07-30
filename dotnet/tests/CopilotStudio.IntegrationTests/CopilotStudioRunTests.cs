// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using AgentConformance.IntegrationTests;

namespace CopilotStudio.IntegrationTests;

public class CopilotStudioRunTests() : RunTests<CopilotStudioFixture>(() => new())
{
    // Set to null to run the tests.
    private const string ManualVerification = "For manual verification";

    [Fact(Skip = "Copilot Studio does not support thread history retrieval, so this test is not applicable.")]
    public override Task ThreadMaintainsHistoryAsync()
    {
        return Task.CompletedTask;
    }

    [Fact(Skip = ManualVerification)]
    public override Task RunWithChatMessageReturnsExpectedResultAsync()
    {
        return base.RunWithChatMessageReturnsExpectedResultAsync();
    }

    [Fact(Skip = ManualVerification)]
    public override Task RunWithChatMessagesReturnsExpectedResultAsync()
    {
        return base.RunWithChatMessagesReturnsExpectedResultAsync();
    }

    [Fact(Skip = ManualVerification)]
    public override Task RunWithNoMessageDoesNotFailAsync()
    {
        return base.RunWithNoMessageDoesNotFailAsync();
    }

    [Fact(Skip = ManualVerification)]
    public override Task RunWithStringReturnsExpectedResultAsync()
    {
        return base.RunWithStringReturnsExpectedResultAsync();
    }
}
