// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Extensions.AI.Agents;

namespace Microsoft.Agents.Orchestration.UnitTest;

/// <summary>
/// Tests for the <see cref="GroupChatOrchestration"/> class.
/// </summary>
public class GroupChatOrchestrationTests
{
    [Fact]
    public async Task GroupChatOrchestrationWithSingleAgentAsync()
    {
        // Arrange
        MockAgent mockAgent1 = MockAgent.CreateWithResponse(2, "xyz");

        // Act: Create and execute the orchestration
        string response = await ExecuteOrchestrationAsync(mockAgent1);

        // Assert
        Assert.Equal(1, mockAgent1.InvokeCount);
        Assert.Equal("xyz", response);
    }

    [Fact]
    public async Task GroupChatOrchestrationWithMultipleAgentsAsync()
    {
        // Arrange
        MockAgent mockAgent1 = MockAgent.CreateWithResponse(1, "abc");
        MockAgent mockAgent2 = MockAgent.CreateWithResponse(2, "xyz");
        MockAgent mockAgent3 = MockAgent.CreateWithResponse(3, "lmn");

        // Act: Create and execute the orchestration
        string response = await ExecuteOrchestrationAsync(mockAgent1, mockAgent2, mockAgent3);

        // Assert
        Assert.Equal(1, mockAgent1.InvokeCount);
        Assert.Equal(1, mockAgent2.InvokeCount);
        Assert.Equal(1, mockAgent3.InvokeCount);
        Assert.Equal("lmn", response);
    }

    private static async Task<string> ExecuteOrchestrationAsync(params AIAgent[] mockAgents)
    {
        // Act
        GroupChatOrchestration orchestration = new(new RoundRobinGroupChatManager() { MaximumInvocationCount = mockAgents.Length }, mockAgents);

        const string InitialInput = "123";
        OrchestrationResult<string> result = await orchestration.InvokeAsync(InitialInput);

        // Assert
        Assert.NotNull(result);

        // Act
        return await result.Task;
    }
}
