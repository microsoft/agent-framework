// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests for the token and wall-clock budget support of <see cref="LoopAgent"/>.
/// </summary>
public class LoopAgentBudgetTests
{
    private static AgentResponse ResponseWithTokens(long totalTokens) =>
        new(new ChatMessage(ChatRole.Assistant, "working")) { Usage = new UsageDetails { TotalTokenCount = totalTokens } };

    /// <summary>
    /// Verify that the loop stops once cumulative token spend reaches MaxTokens and stamps the exit reason.
    /// </summary>
    [Fact]
    public async Task RunAsync_TokenBudgetExceeded_StopsAndStampsReasonAsync()
    {
        // Arrange
        var inner = new InnerAgentCapture(_ => ResponseWithTokens(30));
        var agent = new LoopAgent(inner.Agent, LoopTestHelpers.While(_ => true), new LoopAgentOptions { MaxTokens = 50, MaxIterations = 10 });

        // Act
        AgentResponse response = await agent.RunAsync("task", new ChatClientAgentSession());

        // Assert: 30 < 50 after call 1, 60 >= 50 after call 2.
        Assert.Equal(2, inner.CallCount);
        Assert.NotNull(response.AdditionalProperties);
        Assert.Equal(LoopExitReason.TokenBudgetExceeded, response.AdditionalProperties![LoopExitReason.AdditionalPropertiesKey]);
        Assert.Equal("token_budget_exceeded", response.AdditionalProperties[LoopExitReason.AdditionalPropertiesKey]);
    }

    /// <summary>
    /// Verify that the loop stops after the first iteration when the duration budget is already exhausted.
    /// </summary>
    [Fact]
    public async Task RunAsync_TimeBudgetExceeded_StopsAndStampsReasonAsync()
    {
        // Arrange
        var inner = new InnerAgentCapture(_ => ResponseWithTokens(1));
        var agent = new LoopAgent(inner.Agent, LoopTestHelpers.While(_ => true), new LoopAgentOptions { MaxDuration = TimeSpan.Zero, MaxIterations = 10 });

        // Act
        AgentResponse response = await agent.RunAsync("task", new ChatClientAgentSession());

        // Assert
        Assert.Equal(1, inner.CallCount);
        Assert.NotNull(response.AdditionalProperties);
        Assert.Equal(LoopExitReason.TimeBudgetExceeded, response.AdditionalProperties![LoopExitReason.AdditionalPropertiesKey]);
    }

    /// <summary>
    /// Verify that without a budget the loop runs to the iteration cap.
    /// </summary>
    [Fact]
    public async Task RunAsync_NoBudget_RunsToCapAsync()
    {
        // Arrange
        var inner = new InnerAgentCapture(_ => ResponseWithTokens(1_000_000));
        var agent = new LoopAgent(inner.Agent, LoopTestHelpers.While(_ => true), new LoopAgentOptions { MaxIterations = 3 });

        // Act
        AgentResponse response = await agent.RunAsync("task", new ChatClientAgentSession());

        // Assert
        Assert.Equal(3, inner.CallCount);
        Assert.Equal(LoopExitReason.IterationCapReached, response.AdditionalProperties![LoopExitReason.AdditionalPropertiesKey]);
    }

    /// <summary>
    /// Verify that the budget stop fires before evaluators are consulted.
    /// </summary>
    [Fact]
    public async Task RunAsync_BudgetCheckBeforeEvaluatorsAsync()
    {
        // Arrange
        int evaluatorCalls = 0;
        var inner = new InnerAgentCapture(_ => ResponseWithTokens(60));
        var agent = new LoopAgent(
            inner.Agent,
            LoopTestHelpers.While(_ =>
            {
                evaluatorCalls++;
                return true;
            }),
            new LoopAgentOptions { MaxTokens = 50, MaxIterations = 10 });

        // Act
        AgentResponse response = await agent.RunAsync("task", new ChatClientAgentSession());

        // Assert
        Assert.Equal(1, inner.CallCount);
        Assert.Equal(0, evaluatorCalls);
        Assert.Equal(LoopExitReason.TokenBudgetExceeded, response.AdditionalProperties![LoopExitReason.AdditionalPropertiesKey]);
    }
}
