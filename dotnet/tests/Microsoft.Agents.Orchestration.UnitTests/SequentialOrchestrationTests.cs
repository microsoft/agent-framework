// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Agents.AI;

namespace Microsoft.Agents.Orchestration.UnitTest;

/// <summary>
/// Tests for the <see cref="SequentialOrchestration"/> class.
/// </summary>
public class SequentialOrchestrationTests
{
    [Fact]
    public async Task SequentialOrchestrationWithSingleAgentAsync()
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
    public async Task SequentialOrchestrationWithMultipleAgentsAsync()
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
        SequentialOrchestration orchestration = new(mockAgents);

        const string InitialInput = "123";
        AgentRunResponse result = await orchestration.RunAsync(InitialInput);

        // Assert
        Assert.NotNull(result);

        // Act
        return result.Text;
    }
}
