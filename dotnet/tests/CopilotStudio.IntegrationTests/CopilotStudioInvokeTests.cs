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

    [Fact]
    public virtual async Task RunWithToolReturnsExpectedResultAsync()
    {
        // Arrange
        var agent = this.Fixture.Agent;
        var thread = agent.GetNewThread();

        // Act
        var chatResponse = await agent.RunAsync("Can you send a message to weslie steyn in teams, saying I'll be late for my meeting", thread);

        // Assert
        Assert.NotNull(chatResponse);
        Assert.Single(chatResponse.Messages);
    }
}
