// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
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

    private static AgentResponseUpdate[] UpdatesWithUsage(int call, UsageDetails usage) =>
    [
        new AgentResponseUpdate(ChatRole.Assistant, $"chunk {call}"),
        new AgentResponseUpdate(ChatRole.Assistant, [new UsageContent(usage)]),
    ];

    private static async Task<List<AgentResponseUpdate>> CollectAsync(IAsyncEnumerable<AgentResponseUpdate> stream)
    {
        List<AgentResponseUpdate> updates = [];
        await foreach (AgentResponseUpdate update in stream)
        {
            updates.Add(update);
        }

        return updates;
    }

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
        var agent = new LoopAgent(inner.Agent, LoopTestHelpers.While(_ => true), new LoopAgentOptions { MaxDuration = TimeSpan.FromTicks(1), MaxIterations = 10 });

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

    /// <summary>
    /// Verify that a slow evaluator which exhausts the duration budget does not start another iteration.
    /// </summary>
    [Fact]
    public async Task RunAsync_TimeBudgetExceededDuringEvaluation_DoesNotStartAnotherIterationAsync()
    {
        // Arrange
        int evaluatorCalls = 0;
        var inner = new InnerAgentCapture(_ => ResponseWithTokens(1));
        var evaluator = new DelegateLoopEvaluator(async (_, ct) =>
        {
            evaluatorCalls++;
            await Task.Delay(TimeSpan.FromMilliseconds(1200), ct);
            return LoopEvaluation.Continue();
        });
        var agent = new LoopAgent(inner.Agent, evaluator, new LoopAgentOptions { MaxDuration = TimeSpan.FromSeconds(1), MaxIterations = 10 });

        // Act
        AgentResponse response = await agent.RunAsync("task", new ChatClientAgentSession());

        // Assert: the evaluator ran once and asked to continue, but the budget expired while it ran.
        Assert.Equal(1, evaluatorCalls);
        Assert.Equal(1, inner.CallCount);
        Assert.Equal(LoopExitReason.TimeBudgetExceeded, response.AdditionalProperties![LoopExitReason.AdditionalPropertiesKey]);
    }

    /// <summary>
    /// Verify that the streaming loop stops once cumulative token spend across iterations reaches MaxTokens, without
    /// consulting the evaluators or starting another iteration after the budget is exhausted.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_TokenBudgetReachedCumulatively_StopsWithoutEvaluatingAsync()
    {
        // Arrange
        int evaluatorCalls = 0;
        var inner = new InnerStreamingCapture(call => UpdatesWithUsage(call, new UsageDetails { TotalTokenCount = 30 }));
        var agent = new LoopAgent(
            inner.Agent,
            LoopTestHelpers.While(_ =>
            {
                evaluatorCalls++;
                return true;
            }),
            new LoopAgentOptions { MaxTokens = 50, MaxIterations = 10 });

        // Act
        List<AgentResponseUpdate> updates = await CollectAsync(agent.RunStreamingAsync("task", new ChatClientAgentSession()));

        // Assert: 30 < 50 after call 1 (evaluator consulted), 60 >= 50 after call 2 (evaluator skipped, loop stops).
        Assert.Equal(2, inner.CallCount);
        Assert.Equal(1, evaluatorCalls);
        Assert.Contains(updates, u => u.Text == "chunk 1");
        Assert.Contains(updates, u => u.Text == "chunk 2");
    }

    /// <summary>
    /// Verify that the streaming loop counts InputTokenCount + OutputTokenCount when TotalTokenCount is absent.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_TotalTokenCountAbsent_FallsBackToInputPlusOutputAsync()
    {
        // Arrange
        int evaluatorCalls = 0;
        var inner = new InnerStreamingCapture(call => UpdatesWithUsage(call, new UsageDetails { InputTokenCount = 20, OutputTokenCount = 15 }));
        var agent = new LoopAgent(
            inner.Agent,
            LoopTestHelpers.While(_ =>
            {
                evaluatorCalls++;
                return true;
            }),
            new LoopAgentOptions { MaxTokens = 70, MaxIterations = 10 });

        // Act
        List<AgentResponseUpdate> updates = await CollectAsync(agent.RunStreamingAsync("task", new ChatClientAgentSession()));

        // Assert: 35 < 70 after call 1, 70 >= 70 after call 2. Without the fallback the loop would run to the cap.
        Assert.Equal(2, inner.CallCount);
        Assert.Equal(1, evaluatorCalls);
        Assert.DoesNotContain(updates, u => u.Text == "chunk 3");
    }

    /// <summary>
    /// Verify that the streaming loop stops after the first iteration, without consulting evaluators, when that
    /// iteration alone exhausts the token budget.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_TokenBudgetExhaustedByFirstIteration_SkipsEvaluatorsAsync()
    {
        // Arrange
        int evaluatorCalls = 0;
        var inner = new InnerStreamingCapture(call => UpdatesWithUsage(call, new UsageDetails { TotalTokenCount = 60 }));
        var agent = new LoopAgent(
            inner.Agent,
            LoopTestHelpers.While(_ =>
            {
                evaluatorCalls++;
                return true;
            }),
            new LoopAgentOptions { MaxTokens = 50, MaxIterations = 10 });

        // Act
        List<AgentResponseUpdate> updates = await CollectAsync(agent.RunStreamingAsync("task", new ChatClientAgentSession()));

        // Assert
        Assert.Equal(1, inner.CallCount);
        Assert.Equal(0, evaluatorCalls);
        Assert.Equal(2, updates.Count);
    }

    /// <summary>
    /// Verify that in streaming mode a slow evaluator which exhausts the duration budget does not start another iteration.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_TimeBudgetExceededDuringEvaluation_DoesNotStartAnotherIterationAsync()
    {
        // Arrange
        int evaluatorCalls = 0;
        var inner = new InnerStreamingCapture(call => UpdatesWithUsage(call, new UsageDetails { TotalTokenCount = 1 }));
        var evaluator = new DelegateLoopEvaluator(async (_, ct) =>
        {
            evaluatorCalls++;
            await Task.Delay(TimeSpan.FromMilliseconds(1200), ct);
            return LoopEvaluation.Continue();
        });
        var agent = new LoopAgent(inner.Agent, evaluator, new LoopAgentOptions { MaxDuration = TimeSpan.FromSeconds(1), MaxIterations = 10 });

        // Act
        List<AgentResponseUpdate> updates = await CollectAsync(agent.RunStreamingAsync("task", new ChatClientAgentSession()));

        // Assert
        Assert.Equal(1, evaluatorCalls);
        Assert.Equal(1, inner.CallCount);
        Assert.DoesNotContain(updates, u => u.Text == "chunk 2");
    }
}
