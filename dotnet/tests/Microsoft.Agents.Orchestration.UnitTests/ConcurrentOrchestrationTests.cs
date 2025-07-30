// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using System.Threading.Tasks;
using Microsoft.Extensions.AI.Agents;

namespace Microsoft.Agents.Orchestration.UnitTest;

/// <summary>
/// Tests for the <see cref="ConcurrentOrchestration"/> class.
/// </summary>
public class ConcurrentOrchestrationTests
{
    [Fact]
    public async Task ConcurrentOrchestrationWithSingleAgentAsync()
    {
        // Arrange
        MockAgent mockAgent1 = MockAgent.CreateWithResponse(1, "xyz");

        // Act: Create and execute the orchestration
        string[] response = await ExecuteOrchestrationAsync(mockAgent1);

        // Assert
        Assert.Equal(1, mockAgent1.InvokeCount);
        Assert.Contains("xyz", response);
    }

    [Fact]
    public async Task ConcurrentOrchestrationWithMultipleAgentsAsync()
    {
        // Arrange
        MockAgent mockAgent1 = MockAgent.CreateWithResponse(1, "abc");
        MockAgent mockAgent2 = MockAgent.CreateWithResponse(2, "xyz");
        MockAgent mockAgent3 = MockAgent.CreateWithResponse(3, "lmn");

        // Act: Create and execute the orchestration
        string[] response = await ExecuteOrchestrationAsync(mockAgent1, mockAgent2, mockAgent3);

        // Assert
        Assert.Equal(1, mockAgent1.InvokeCount);
        Assert.Equal(1, mockAgent2.InvokeCount);
        Assert.Equal(1, mockAgent3.InvokeCount);
        Assert.Contains("lmn", response);
        Assert.Contains("xyz", response);
        Assert.Contains("abc", response);
    }

    private static async Task<string[]> ExecuteOrchestrationAsync(params AIAgent[] mockAgents)
    {
        // Act
        ConcurrentOrchestration orchestration = new(mockAgents);

        const string InitialInput = "123";
        AgentRunResponse result = await orchestration.RunAsync(InitialInput);

        // Assert
        Assert.NotNull(result);

        // Act
        return result.Messages.Select(m => m.Text).ToArray();
    }
}
