// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using AgentConformance.IntegrationTests;

namespace CopilotStudio.IntegrationTests;

public class CopilotStudioInvokeTests() : RunAsyncTests<CopilotStudioFixture>(() => new())
{
    [Fact(Skip = "Copilot Studio does not support additional instructions, so this test is not applicable.")]
    public override Task RunWithAdditionalInstructionsAndNoMessageReturnsExpectedResultAsync()
    {
        return Task.CompletedTask;
    }

    [Fact(Skip = "Copilot Studio does not support thread history retrieval, so this test is not applicable.")]
    public override Task ThreadMaintainsHistoryAsync()
    {
        return Task.CompletedTask;
    }
}
