// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;
using Moq.Protected;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="BackgroundTaskCompletionLoopEvaluator"/> class.
/// </summary>
public class BackgroundTaskCompletionLoopEvaluatorTests
{
    /// <summary>
    /// Verify that the constructor succeeds with no options and with a custom template.
    /// </summary>
    [Fact]
    public void BackgroundTaskCompletionLoopEvaluator_ValidConstruction_Succeeds()
    {
        // Act & Assert
        _ = new BackgroundTaskCompletionLoopEvaluator();
        _ = new BackgroundTaskCompletionLoopEvaluator(new BackgroundTaskCompletionLoopEvaluatorOptions { FeedbackMessageTemplate = "custom" });
    }

    /// <summary>
    /// Verify that evaluation throws when no <see cref="BackgroundAgentsProvider"/> can be resolved from the agent.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_NoBackgroundAgentsProvider_ThrowsAsync()
    {
        // Arrange — a bare agent that resolves no providers.
        var evaluator = new BackgroundTaskCompletionLoopEvaluator();
        var context = CreateContext(new Mock<AIAgent>().Object, new ChatClientAgentSession());

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await evaluator.EvaluateAsync(context));
    }

    /// <summary>
    /// Verify that the evaluator continues while a background task is still running and that the feedback lists the
    /// running task and its count.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_RunningTask_ContinuesWithFeedbackAsync()
    {
        // Arrange
        var tcs = new TaskCompletionSource<AgentResponse>();
        var backgroundAgent = CreateMockAgentWithRunResult("Research", tcs.Task);
        var provider = new BackgroundAgentsProvider(new[] { backgroundAgent });
        var session = new ChatClientAgentSession();
        IEnumerable<AITool> tools = await CreateToolsForSessionAsync(provider, session);
        await StartTaskAsync(tools, "Research", "Find information about AI", "Research AI topics");

        AIAgent agent = CreateAgent(provider);
        var evaluator = new BackgroundTaskCompletionLoopEvaluator();
        LoopContext context = CreateContext(agent, session);

        // Act
        LoopEvaluation evaluation = await evaluator.EvaluateAsync(context);

        // Assert
        Assert.True(evaluation.ShouldReinvoke);
        Assert.NotNull(evaluation.Feedback);
        Assert.Contains("1 background task(s)", evaluation.Feedback!);
        Assert.Contains("#1", evaluation.Feedback!);
        Assert.Contains("Research", evaluation.Feedback!);
        Assert.Contains("Research AI topics", evaluation.Feedback!);

        // Cleanup — complete the in-flight task to avoid leaking a pending task.
        tcs.SetResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "done")));
    }

    /// <summary>
    /// Verify that the evaluator stops once every background task has reached a terminal state.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_AllTasksTerminal_StopsAsync()
    {
        // Arrange
        var tcs = new TaskCompletionSource<AgentResponse>();
        var backgroundAgent = CreateMockAgentWithRunResult("Research", tcs.Task);
        var provider = new BackgroundAgentsProvider(new[] { backgroundAgent });
        var session = new ChatClientAgentSession();
        IEnumerable<AITool> tools = await CreateToolsForSessionAsync(provider, session);
        await StartTaskAsync(tools, "Research", "Task 1", "First task");

        // Complete the task and wait for it to be finalized.
        tcs.SetResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "Result 1")));
        await WaitForCompletionAsync(tools, 1);

        AIAgent agent = CreateAgent(provider);
        var evaluator = new BackgroundTaskCompletionLoopEvaluator();
        LoopContext context = CreateContext(agent, session);

        // Act
        LoopEvaluation evaluation = await evaluator.EvaluateAsync(context);

        // Assert
        Assert.False(evaluation.ShouldReinvoke);
        Assert.Null(evaluation.Feedback);
    }

    /// <summary>
    /// Verify that the evaluator stops when no background tasks have been started.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_NoTasks_StopsAsync()
    {
        // Arrange
        var backgroundAgent = CreateMockAgent("Research", "Research agent");
        var provider = new BackgroundAgentsProvider(new[] { backgroundAgent });
        var session = new ChatClientAgentSession();
        _ = await CreateToolsForSessionAsync(provider, session);

        AIAgent agent = CreateAgent(provider);
        var evaluator = new BackgroundTaskCompletionLoopEvaluator();
        LoopContext context = CreateContext(agent, session);

        // Act
        LoopEvaluation evaluation = await evaluator.EvaluateAsync(context);

        // Assert
        Assert.False(evaluation.ShouldReinvoke);
        Assert.Null(evaluation.Feedback);
    }

    /// <summary>
    /// Verify that a custom feedback template is honored, including the running task list placeholder.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_CustomTemplate_IsHonoredAsync()
    {
        // Arrange
        var tcs = new TaskCompletionSource<AgentResponse>();
        var backgroundAgent = CreateMockAgentWithRunResult("Research", tcs.Task);
        var provider = new BackgroundAgentsProvider(new[] { backgroundAgent });
        var session = new ChatClientAgentSession();
        IEnumerable<AITool> tools = await CreateToolsForSessionAsync(provider, session);
        await StartTaskAsync(tools, "Research", "Task 1", "First task");

        AIAgent agent = CreateAgent(provider);
        var options = new BackgroundTaskCompletionLoopEvaluatorOptions
        {
            FeedbackMessageTemplate = "Pending:\n" + BackgroundTaskCompletionLoopEvaluator.IncompleteTasksPlaceholder,
        };
        var evaluator = new BackgroundTaskCompletionLoopEvaluator(options);
        LoopContext context = CreateContext(agent, session);

        // Act
        LoopEvaluation evaluation = await evaluator.EvaluateAsync(context);

        // Assert
        Assert.True(evaluation.ShouldReinvoke);
        Assert.StartsWith("Pending:", evaluation.Feedback);
        Assert.Contains("#1", evaluation.Feedback!);
        Assert.Contains("First task", evaluation.Feedback!);

        // Cleanup.
        tcs.SetResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "done")));
    }

    /// <summary>
    /// Verify that <see cref="BackgroundAgentsProvider.GetIncompleteTasks"/> returns only the tasks that are still
    /// running, excluding completed ones.
    /// </summary>
    [Fact]
    public async Task GetIncompleteTasks_ReturnsOnlyRunningTasksAsync()
    {
        // Arrange — two tasks, one of which completes.
        var tcs1 = new TaskCompletionSource<AgentResponse>();
        var tcs2 = new TaskCompletionSource<AgentResponse>();
        var agent1 = CreateMockAgentWithRunResult("Research", tcs1.Task);
        var agent2 = CreateMockAgentWithRunResult("Writer", tcs2.Task);
        var provider = new BackgroundAgentsProvider(new[] { agent1, agent2 });
        var session = new ChatClientAgentSession();
        IEnumerable<AITool> tools = await CreateToolsForSessionAsync(provider, session);
        await StartTaskAsync(tools, "Research", "Task 1", "First task");
        await StartTaskAsync(tools, "Writer", "Task 2", "Second task");

        // Complete only the first task and wait for it to be finalized.
        tcs1.SetResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "Result 1")));
        await WaitForCompletionAsync(tools, 1);

        // Act
        IReadOnlyList<BackgroundTaskInfo> incomplete = provider.GetIncompleteTasks(session);

        // Assert — only the still-running second task remains.
        BackgroundTaskInfo task = Assert.Single(incomplete);
        Assert.Equal(2, task.Id);
        Assert.Equal("Writer", task.AgentName);
        Assert.Equal(BackgroundTaskStatus.Running, task.Status);

        // Cleanup.
        tcs2.SetResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "done")));
    }

    /// <summary>
    /// Verify that a task persisted as <see cref="BackgroundTaskStatus.Running"/> but with no corresponding in-flight
    /// runtime reference (as happens after a session is serialized and restored) is treated as
    /// <see cref="BackgroundTaskStatus.Lost"/> and excluded from the incomplete set, so the loop does not spin forever.
    /// </summary>
    [Fact]
    public async Task GetIncompleteTasks_TaskWithNoInFlightReference_IsTreatedAsLostAndExcludedAsync()
    {
        // Arrange — seed a Running task into session state without any runtime in-flight reference, simulating a restore.
        var backgroundAgent = CreateMockAgent("Research", "Research agent");
        var provider = new BackgroundAgentsProvider(new[] { backgroundAgent });
        var session = new ChatClientAgentSession();
        SeedRunningTaskWithoutInFlight(session, 1, "Research", "First task");

        // Act — querying refreshes task state, which finalizes the orphaned task to Lost.
        IReadOnlyList<BackgroundTaskInfo> incomplete = provider.GetIncompleteTasks(session);

        // Assert — the lost task is not returned, and the evaluator stops rather than looping forever.
        Assert.Empty(incomplete);

        AIAgent agent = CreateAgent(provider);
        var evaluator = new BackgroundTaskCompletionLoopEvaluator();
        LoopEvaluation evaluation = await evaluator.EvaluateAsync(CreateContext(agent, session));
        Assert.False(evaluation.ShouldReinvoke);
        Assert.Null(evaluation.Feedback);
    }

    private static ChatClientAgent CreateAgent(params AIContextProvider[] providers)
    {
        var chatClient = new Mock<IChatClient>().Object;
        return new ChatClientAgent(chatClient, new ChatClientAgentOptions { AIContextProviders = providers });
    }

    private static LoopContext CreateContext(AIAgent agent, AgentSession session) => new(
        agent,
        session,
        [new ChatMessage(ChatRole.User, "do the work")],
        new AgentResponse([new ChatMessage(ChatRole.Assistant, "in progress")]));

    private static async Task<IEnumerable<AITool>> CreateToolsForSessionAsync(BackgroundAgentsProvider provider, AgentSession session)
    {
        var mockAgent = new Mock<AIAgent>().Object;
#pragma warning disable MAAI001
        var context = new AIContextProvider.InvokingContext(mockAgent, session, new AIContext());
#pragma warning restore MAAI001
        AIContext result = await provider.InvokingAsync(context);
        return result.Tools!;
    }

    private static async Task StartTaskAsync(IEnumerable<AITool> tools, string agentName, string input, string description)
    {
        AIFunction startTask = GetTool(tools, "background_agents_start_task");
        await startTask.InvokeAsync(new AIFunctionArguments
        {
            ["agentName"] = agentName,
            ["input"] = input,
            ["description"] = description,
        });
    }

    private static async Task WaitForCompletionAsync(IEnumerable<AITool> tools, int taskId)
    {
        AIFunction waitForFirst = GetTool(tools, "background_agents_wait_for_first_completion");
        await waitForFirst.InvokeAsync(new AIFunctionArguments
        {
            ["taskIds"] = new List<int> { taskId },
        });
    }

    private static void SeedRunningTaskWithoutInFlight(AgentSession session, int id, string agentName, string description)
    {
        var state = new BackgroundAgentState { NextTaskId = id + 1 };
        state.Tasks.Add(new BackgroundTaskInfo
        {
            Id = id,
            AgentName = agentName,
            Description = description,
            Status = BackgroundTaskStatus.Running,
        });

        // Persist under the BackgroundAgentsProvider's state key with no runtime in-flight entry, mirroring a restored
        // session whose in-flight task references have been lost.
        session.StateBag.SetValue(nameof(BackgroundAgentsProvider), state, AgentJsonUtilities.DefaultOptions);
    }

    private static AIAgent CreateMockAgent(string? name, string? description)
    {
        var mock = new Mock<AIAgent>();
        mock.SetupGet(a => a.Name).Returns(name!);
        mock.SetupGet(a => a.Description).Returns(description);
        return mock.Object;
    }

    private static AIAgent CreateMockAgentWithRunResult(string name, Task<AgentResponse> result)
    {
        var mock = new Mock<AIAgent>();
        mock.SetupGet(a => a.Name).Returns(name);
        mock.Protected()
            .Setup<ValueTask<AgentSession>>(
                "CreateSessionCoreAsync",
                ItExpr.IsAny<CancellationToken>())
            .Returns(new ValueTask<AgentSession>(new ChatClientAgentSession()));
        mock.Protected()
            .Setup<Task<AgentResponse>>(
                "RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession>(),
                ItExpr.IsAny<AgentRunOptions>(),
                ItExpr.IsAny<CancellationToken>())
            .Returns(result);
        return mock.Object;
    }

    private static AIFunction GetTool(IEnumerable<AITool> tools, string name)
    {
        return (AIFunction)tools.First(t => t is AIFunction f && f.Name == name);
    }
}
