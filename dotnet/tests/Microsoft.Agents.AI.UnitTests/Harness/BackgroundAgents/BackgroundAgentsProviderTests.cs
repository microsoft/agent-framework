// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;
using Moq.Protected;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="BackgroundAgentsProvider"/> class.
/// </summary>
public class BackgroundAgentsProviderTests
{
    #region Constructor Tests

    /// <summary>
    /// Verify that the constructor throws when agents is null.
    /// </summary>
    [Fact]
    public void Constructor_NullAgents_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new BackgroundAgentsProvider(null!));
    }

    /// <summary>
    /// Verify that the constructor throws when agents collection is empty.
    /// </summary>
    [Fact]
    public void Constructor_EmptyAgents_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentException>(() => new BackgroundAgentsProvider(Array.Empty<AIAgent>()));
    }

    /// <summary>
    /// Verify that the constructor throws when an agent has a null name.
    /// </summary>
    [Fact]
    public void Constructor_AgentWithNullName_Throws()
    {
        // Arrange
        var agent = CreateMockAgent(null!, "desc");

        // Act & Assert
        Assert.Throws<ArgumentException>(() => new BackgroundAgentsProvider(new[] { agent }));
    }

    /// <summary>
    /// Verify that the constructor throws when an agent has an empty name.
    /// </summary>
    [Fact]
    public void Constructor_AgentWithEmptyName_Throws()
    {
        // Arrange
        var agent = CreateMockAgent("", "desc");

        // Act & Assert
        Assert.Throws<ArgumentException>(() => new BackgroundAgentsProvider(new[] { agent }));
    }

    /// <summary>
    /// Verify that the constructor throws when duplicate agent names are provided (case-insensitive).
    /// </summary>
    [Fact]
    public void Constructor_DuplicateNames_Throws()
    {
        // Arrange
        var agent1 = CreateMockAgent("Research", "Agent 1");
        var agent2 = CreateMockAgent("research", "Agent 2");

        // Act & Assert
        Assert.Throws<ArgumentException>(() => new BackgroundAgentsProvider(new[] { agent1, agent2 }));
    }

    /// <summary>
    /// Verify that the constructor succeeds with valid agents.
    /// </summary>
    [Fact]
    public void Constructor_ValidAgents_Succeeds()
    {
        // Arrange
        var agent1 = CreateMockAgent("Research", "Research agent");
        var agent2 = CreateMockAgent("Writer", "Writer agent");

        // Act
        var provider = new BackgroundAgentsProvider(new[] { agent1, agent2 });

        // Assert
        Assert.NotNull(provider);
    }

    #endregion

    #region ProvideAIContextAsync Tests

    /// <summary>
    /// Verify that the provider returns tools and instructions.
    /// </summary>
    [Fact]
    public async Task ProvideAIContextAsync_ReturnsToolsAndInstructionsAsync()
    {
        // Arrange
        var agent = CreateMockAgent("Research", "Research agent");
        var provider = new BackgroundAgentsProvider(new[] { agent });
        var context = CreateInvokingContext();

        // Act
        AIContext result = await provider.InvokingAsync(context);

        // Assert
        Assert.NotNull(result.Instructions);
        Assert.NotNull(result.Tools);
        Assert.Equal(6, result.Tools!.Count());
    }

    /// <summary>
    /// Verify that the instructions include agent names and descriptions.
    /// </summary>
    [Fact]
    public async Task ProvideAIContextAsync_InstructionsIncludeAgentInfoAsync()
    {
        // Arrange
        var agent1 = CreateMockAgent("Research", "Performs research");
        var agent2 = CreateMockAgent("Writer", "Writes content");
        var provider = new BackgroundAgentsProvider(new[] { agent1, agent2 });
        var context = CreateInvokingContext();

        // Act
        AIContext result = await provider.InvokingAsync(context);

        // Assert — agent info is appended to instructions
        Assert.Contains("Research", result.Instructions);
        Assert.Contains("Performs research", result.Instructions);
        Assert.Contains("Writer", result.Instructions);
        Assert.Contains("Writes content", result.Instructions);
    }

    #endregion

    #region StartBackgroundTask Tests

    /// <summary>
    /// Verify that StartBackgroundTask returns a task ID.
    /// </summary>
    [Fact]
    public async Task StartBackgroundTask_ReturnsTaskIdAsync()
    {
        // Arrange
        var tcs = new TaskCompletionSource<AgentResponse>();
        var agent = CreateMockAgentWithRunResult("Research", tcs.Task);
        var (tools, _) = await CreateToolsWithProviderAsync(agent);
        AIFunction startBackgroundTask = GetTool(tools, "background_agents_start_task");

        // Act
        object? result = await startBackgroundTask.InvokeAsync(new AIFunctionArguments
        {
            ["agentName"] = "Research",
            ["input"] = "Find information about AI",
            ["description"] = "Research AI topics",
        });

        // Assert
        string text = GetStringResult(result);
        Assert.Contains("1", text);
        Assert.Contains("started", text);

        tcs.SetResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "done")));
    }

    /// <summary>
    /// Verify that StartBackgroundTask with invalid agent name returns an error.
    /// </summary>
    [Fact]
    public async Task StartBackgroundTask_InvalidAgentName_ReturnsErrorAsync()
    {
        // Arrange
        var agent = CreateMockAgent("Research", "Research agent");
        var (tools, _) = await CreateToolsWithProviderAsync(agent);
        AIFunction startBackgroundTask = GetTool(tools, "background_agents_start_task");

        // Act
        object? result = await startBackgroundTask.InvokeAsync(new AIFunctionArguments
        {
            ["agentName"] = "NonExistent",
            ["input"] = "Some input",
            ["description"] = "Some task",
        });

        // Assert
        string text = GetStringResult(result);
        Assert.Contains("Error", text);
        Assert.Contains("NonExistent", text);
    }

    /// <summary>
    /// Verify that StartBackgroundTask assigns sequential IDs.
    /// </summary>
    [Fact]
    public async Task StartBackgroundTask_AssignsSequentialIdsAsync()
    {
        // Arrange
        var tcs1 = new TaskCompletionSource<AgentResponse>();
        var tcs2 = new TaskCompletionSource<AgentResponse>();
        var callCount = 0;
        var agent = CreateMockAgentWithCallback("Research", () =>
        {
            callCount++;
            return callCount == 1 ? tcs1.Task : tcs2.Task;
        });
        var (tools, _) = await CreateToolsWithProviderAsync(agent);
        AIFunction startBackgroundTask = GetTool(tools, "background_agents_start_task");

        // Act
        object? result1 = await startBackgroundTask.InvokeAsync(new AIFunctionArguments
        {
            ["agentName"] = "Research",
            ["input"] = "Task 1",
            ["description"] = "First task",
        });
        object? result2 = await startBackgroundTask.InvokeAsync(new AIFunctionArguments
        {
            ["agentName"] = "Research",
            ["input"] = "Task 2",
            ["description"] = "Second task",
        });

        // Assert
        Assert.Contains("1", GetStringResult(result1));
        Assert.Contains("2", GetStringResult(result2));

        tcs1.SetResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "done")));
        tcs2.SetResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "done")));
    }

    #endregion

    #region WaitForFirstCompletion Tests

    /// <summary>
    /// Verify that WaitForFirstCompletion returns the ID of a completed task.
    /// </summary>
    [Fact]
    public async Task WaitForFirstCompletion_ReturnsCompletedTaskIdAsync()
    {
        // Arrange — use a single task to avoid Task.Run scheduling races.
        var tcs = new TaskCompletionSource<AgentResponse>();
        var agent = CreateMockAgentWithRunResult("Research", tcs.Task);
        var (tools, _) = await CreateToolsWithProviderAsync(agent);
        AIFunction startBackgroundTask = GetTool(tools, "background_agents_start_task");
        AIFunction waitForFirst = GetTool(tools, "background_agents_wait_for_first_completion");

        // Start one task
        await startBackgroundTask.InvokeAsync(new AIFunctionArguments
        {
            ["agentName"] = "Research",
            ["input"] = "Task 1",
            ["description"] = "First task",
        });

        // Complete the task
        tcs.SetResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "Result 1")));

        // Act
        object? result = await waitForFirst.InvokeAsync(new AIFunctionArguments
        {
            ["taskIds"] = new List<int> { 1 },
        });

        // Assert
        string text = GetStringResult(result);
        Assert.Contains("1", text);
        Assert.Contains("finished with status: Completed", text);
    }

    /// <summary>
    /// Verify that WaitForFirstCompletion with empty list returns an error.
    /// </summary>
    [Fact]
    public async Task WaitForFirstCompletion_EmptyList_ReturnsErrorAsync()
    {
        // Arrange
        var agent = CreateMockAgent("Research", "Research agent");
        var (tools, _) = await CreateToolsWithProviderAsync(agent);
        AIFunction waitForFirst = GetTool(tools, "background_agents_wait_for_first_completion");

        // Act
        object? result = await waitForFirst.InvokeAsync(new AIFunctionArguments
        {
            ["taskIds"] = new List<int>(),
        });

        // Assert
        Assert.Contains("Error", GetStringResult(result));
    }

    #endregion

    #region GetBackgroundTaskResults Tests

    /// <summary>
    /// Verify that GetBackgroundTaskResults returns the result text of a completed task.
    /// </summary>
    [Fact]
    public async Task GetBackgroundTaskResults_CompletedTask_ReturnsResultTextAsync()
    {
        // Arrange
        var tcs = new TaskCompletionSource<AgentResponse>();
        var agent = CreateMockAgentWithRunResult("Research", tcs.Task);
        var (tools, _) = await CreateToolsWithProviderAsync(agent);
        AIFunction startBackgroundTask = GetTool(tools, "background_agents_start_task");
        AIFunction waitForFirst = GetTool(tools, "background_agents_wait_for_first_completion");
        AIFunction getResults = GetTool(tools, "background_agents_get_task_results");

        // Start a task
        await startBackgroundTask.InvokeAsync(new AIFunctionArguments
        {
            ["agentName"] = "Research",
            ["input"] = "Research AI",
            ["description"] = "AI research",
        });

        // Complete it
        tcs.SetResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "AI is fascinating!")));

        // Wait for completion to finalize state
        await waitForFirst.InvokeAsync(new AIFunctionArguments
        {
            ["taskIds"] = new List<int> { 1 },
        });

        // Act
        object? result = await getResults.InvokeAsync(new AIFunctionArguments
        {
            ["taskId"] = 1,
        });

        // Assert
        Assert.Contains("AI is fascinating!", GetStringResult(result));
    }

    /// <summary>
    /// Verify that GetBackgroundTaskResults for a still-running task returns status info.
    /// </summary>
    [Fact]
    public async Task GetBackgroundTaskResults_RunningTask_ReturnsStatusAsync()
    {
        // Arrange
        var tcs = new TaskCompletionSource<AgentResponse>();
        var agent = CreateMockAgentWithRunResult("Research", tcs.Task);
        var (tools, _) = await CreateToolsWithProviderAsync(agent);
        AIFunction startBackgroundTask = GetTool(tools, "background_agents_start_task");
        AIFunction getResults = GetTool(tools, "background_agents_get_task_results");

        // Start a task (don't complete it)
        await startBackgroundTask.InvokeAsync(new AIFunctionArguments
        {
            ["agentName"] = "Research",
            ["input"] = "Research AI",
            ["description"] = "AI research",
        });

        // Act
        object? result = await getResults.InvokeAsync(new AIFunctionArguments
        {
            ["taskId"] = 1,
        });

        // Assert
        Assert.Contains("still running", GetStringResult(result));

        tcs.SetResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "done")));
    }

    /// <summary>
    /// Verify that GetBackgroundTaskResults for a nonexistent task returns an error.
    /// </summary>
    [Fact]
    public async Task GetBackgroundTaskResults_NonexistentTask_ReturnsErrorAsync()
    {
        // Arrange
        var agent = CreateMockAgent("Research", "Research agent");
        var (tools, _) = await CreateToolsWithProviderAsync(agent);
        AIFunction getResults = GetTool(tools, "background_agents_get_task_results");

        // Act
        object? result = await getResults.InvokeAsync(new AIFunctionArguments
        {
            ["taskId"] = 999,
        });

        // Assert
        Assert.Contains("Error", GetStringResult(result));
    }

    /// <summary>
    /// Verify that GetBackgroundTaskResults for a failed task returns the error.
    /// </summary>
    [Fact]
    public async Task GetBackgroundTaskResults_FailedTask_ReturnsErrorTextAsync()
    {
        // Arrange
        var tcs = new TaskCompletionSource<AgentResponse>();
        var agent = CreateMockAgentWithRunResult("Research", tcs.Task);
        var (tools, _) = await CreateToolsWithProviderAsync(agent);
        AIFunction startBackgroundTask = GetTool(tools, "background_agents_start_task");
        AIFunction waitForFirst = GetTool(tools, "background_agents_wait_for_first_completion");
        AIFunction getResults = GetTool(tools, "background_agents_get_task_results");

        // Start a task
        await startBackgroundTask.InvokeAsync(new AIFunctionArguments
        {
            ["agentName"] = "Research",
            ["input"] = "Research AI",
            ["description"] = "AI research",
        });

        // Fail it
        tcs.SetException(new InvalidOperationException("Connection failed"));

        // Wait for completion to finalize state
        await waitForFirst.InvokeAsync(new AIFunctionArguments
        {
            ["taskIds"] = new List<int> { 1 },
        });

        // Act
        object? result = await getResults.InvokeAsync(new AIFunctionArguments
        {
            ["taskId"] = 1,
        });

        // Assert
        string text = GetStringResult(result);
        Assert.Contains("failed", text);
        Assert.Contains("Connection failed", text);
    }

    #endregion

    #region GetAllTasks Tests

    /// <summary>
    /// Verify that GetAllTasks returns running tasks with descriptions and status.
    /// </summary>
    [Fact]
    public async Task GetAllTasks_ReturnsRunningTasksAsync()
    {
        // Arrange
        var tcs = new TaskCompletionSource<AgentResponse>();
        var agent = CreateMockAgentWithRunResult("Research", tcs.Task);
        var (tools, _) = await CreateToolsWithProviderAsync(agent);
        AIFunction startBackgroundTask = GetTool(tools, "background_agents_start_task");
        AIFunction getAllTasks = GetTool(tools, "background_agents_get_all_tasks");

        // Start a task
        await startBackgroundTask.InvokeAsync(new AIFunctionArguments
        {
            ["agentName"] = "Research",
            ["input"] = "Research AI",
            ["description"] = "AI research task",
        });

        // Act
        object? result = await getAllTasks.InvokeAsync(new AIFunctionArguments());

        // Assert
        string text = GetStringResult(result);
        Assert.Contains("1", text);
        Assert.Contains("Research", text);
        Assert.Contains("AI research task", text);
        Assert.Contains("Running", text);

        tcs.SetResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "done")));
    }

    /// <summary>
    /// Verify that GetAllTasks returns completed tasks with their status.
    /// </summary>
    [Fact]
    public async Task GetAllTasks_ShowsCompletedTasksAsync()
    {
        // Arrange
        var tcs = new TaskCompletionSource<AgentResponse>();
        var agent = CreateMockAgentWithRunResult("Research", tcs.Task);
        var (tools, _) = await CreateToolsWithProviderAsync(agent);
        AIFunction startBackgroundTask = GetTool(tools, "background_agents_start_task");
        AIFunction waitForFirst = GetTool(tools, "background_agents_wait_for_first_completion");
        AIFunction getAllTasks = GetTool(tools, "background_agents_get_all_tasks");

        // Start and complete a task
        await startBackgroundTask.InvokeAsync(new AIFunctionArguments
        {
            ["agentName"] = "Research",
            ["input"] = "Research AI",
            ["description"] = "AI research",
        });
        tcs.SetResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "done")));
        await waitForFirst.InvokeAsync(new AIFunctionArguments
        {
            ["taskIds"] = new List<int> { 1 },
        });

        // Act
        object? result = await getAllTasks.InvokeAsync(new AIFunctionArguments());

        // Assert
        string text = GetStringResult(result);
        Assert.Contains("Completed", text);
        Assert.Contains("Research", text);
    }

    /// <summary>
    /// Verify that GetAllTasks returns no tasks when none exist.
    /// </summary>
    [Fact]
    public async Task GetAllTasks_NoTasks_ReturnsNoneAsync()
    {
        // Arrange
        var agent = CreateMockAgent("Research", "Research agent");
        var (tools, _) = await CreateToolsWithProviderAsync(agent);
        AIFunction getAllTasks = GetTool(tools, "background_agents_get_all_tasks");

        // Act
        object? result = await getAllTasks.InvokeAsync(new AIFunctionArguments());

        // Assert
        Assert.Contains("No tasks", GetStringResult(result));
    }

    #endregion

    #region ContinueTask Tests

    /// <summary>
    /// Verify that ContinueTask resumes a completed task with new input.
    /// </summary>
    [Fact]
    public async Task ContinueTask_CompletedTask_ResumesAsync()
    {
        // Arrange
        var tcs1 = new TaskCompletionSource<AgentResponse>();
        var tcs2 = new TaskCompletionSource<AgentResponse>();
        var callCount = 0;
        var agent = CreateMockAgentWithCallback("Research", () =>
        {
            callCount++;
            return callCount == 1 ? tcs1.Task : tcs2.Task;
        });
        var (tools, _) = await CreateToolsWithProviderAsync(agent);
        AIFunction startBackgroundTask = GetTool(tools, "background_agents_start_task");
        AIFunction waitForFirst = GetTool(tools, "background_agents_wait_for_first_completion");
        AIFunction continueTask = GetTool(tools, "background_agents_continue_task");
        AIFunction getResults = GetTool(tools, "background_agents_get_task_results");

        // Start and complete a task
        await startBackgroundTask.InvokeAsync(new AIFunctionArguments
        {
            ["agentName"] = "Research",
            ["input"] = "Research AI",
            ["description"] = "AI research",
        });
        tcs1.SetResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "First result")));
        await waitForFirst.InvokeAsync(new AIFunctionArguments
        {
            ["taskIds"] = new List<int> { 1 },
        });

        // Act — continue the task
        object? continueResult = await continueTask.InvokeAsync(new AIFunctionArguments
        {
            ["taskId"] = 1,
            ["text"] = "Please elaborate",
        });

        // Assert — task is resumed
        Assert.Contains("continued", GetStringResult(continueResult));

        // Complete the second run
        tcs2.SetResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "Elaborated result")));
        await waitForFirst.InvokeAsync(new AIFunctionArguments
        {
            ["taskIds"] = new List<int> { 1 },
        });

        object? result = await getResults.InvokeAsync(new AIFunctionArguments
        {
            ["taskId"] = 1,
        });
        Assert.Contains("Elaborated result", GetStringResult(result));
    }

    /// <summary>
    /// Verify that ContinueTask on a running task returns an error.
    /// </summary>
    [Fact]
    public async Task ContinueTask_RunningTask_ReturnsErrorAsync()
    {
        // Arrange
        var tcs = new TaskCompletionSource<AgentResponse>();
        var agent = CreateMockAgentWithRunResult("Research", tcs.Task);
        var (tools, _) = await CreateToolsWithProviderAsync(agent);
        AIFunction startBackgroundTask = GetTool(tools, "background_agents_start_task");
        AIFunction continueTask = GetTool(tools, "background_agents_continue_task");

        // Start a task (don't complete it)
        await startBackgroundTask.InvokeAsync(new AIFunctionArguments
        {
            ["agentName"] = "Research",
            ["input"] = "Research AI",
            ["description"] = "AI research",
        });

        // Act
        object? result = await continueTask.InvokeAsync(new AIFunctionArguments
        {
            ["taskId"] = 1,
            ["text"] = "More input",
        });

        // Assert
        Assert.Contains("still running", GetStringResult(result));

        tcs.SetResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "done")));
    }

    /// <summary>
    /// Verify that ContinueTask on a nonexistent task returns an error.
    /// </summary>
    [Fact]
    public async Task ContinueTask_NonexistentTask_ReturnsErrorAsync()
    {
        // Arrange
        var agent = CreateMockAgent("Research", "Research agent");
        var (tools, _) = await CreateToolsWithProviderAsync(agent);
        AIFunction continueTask = GetTool(tools, "background_agents_continue_task");

        // Act
        object? result = await continueTask.InvokeAsync(new AIFunctionArguments
        {
            ["taskId"] = 999,
            ["text"] = "More input",
        });

        // Assert
        Assert.Contains("Error", GetStringResult(result));
    }

    #endregion

    #region ClearCompletedTask Tests

    /// <summary>
    /// Verify that ClearCompletedTask removes a terminal task.
    /// </summary>
    [Fact]
    public async Task ClearCompletedTask_RemovesTerminalTaskAsync()
    {
        // Arrange
        var tcs = new TaskCompletionSource<AgentResponse>();
        var agent = CreateMockAgentWithRunResult("Research", tcs.Task);
        var (tools, _) = await CreateToolsWithProviderAsync(agent);
        AIFunction startBackgroundTask = GetTool(tools, "background_agents_start_task");
        AIFunction waitForFirst = GetTool(tools, "background_agents_wait_for_first_completion");
        AIFunction clearTask = GetTool(tools, "background_agents_clear_completed_task");
        AIFunction getResults = GetTool(tools, "background_agents_get_task_results");

        // Start and complete a task
        await startBackgroundTask.InvokeAsync(new AIFunctionArguments
        {
            ["agentName"] = "Research",
            ["input"] = "Research AI",
            ["description"] = "AI research",
        });
        tcs.SetResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "Result")));
        await waitForFirst.InvokeAsync(new AIFunctionArguments
        {
            ["taskIds"] = new List<int> { 1 },
        });

        // Act
        object? clearResult = await clearTask.InvokeAsync(new AIFunctionArguments
        {
            ["taskId"] = 1,
        });

        // Assert — task is cleared
        Assert.Contains("cleared", GetStringResult(clearResult));

        // Verify it's gone
        object? getResult = await getResults.InvokeAsync(new AIFunctionArguments
        {
            ["taskId"] = 1,
        });
        Assert.Contains("Error", GetStringResult(getResult));
    }

    /// <summary>
    /// Verify that ClearCompletedTask on a running task returns an error.
    /// </summary>
    [Fact]
    public async Task ClearCompletedTask_RunningTask_ReturnsErrorAsync()
    {
        // Arrange
        var tcs = new TaskCompletionSource<AgentResponse>();
        var agent = CreateMockAgentWithRunResult("Research", tcs.Task);
        var (tools, _) = await CreateToolsWithProviderAsync(agent);
        AIFunction startBackgroundTask = GetTool(tools, "background_agents_start_task");
        AIFunction clearTask = GetTool(tools, "background_agents_clear_completed_task");

        // Start a task (don't complete it)
        await startBackgroundTask.InvokeAsync(new AIFunctionArguments
        {
            ["agentName"] = "Research",
            ["input"] = "Research AI",
            ["description"] = "AI research",
        });

        // Act
        object? result = await clearTask.InvokeAsync(new AIFunctionArguments
        {
            ["taskId"] = 1,
        });

        // Assert
        Assert.Contains("still running", GetStringResult(result));

        tcs.SetResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "done")));
    }

    /// <summary>
    /// Verify that ClearCompletedTask on a nonexistent task returns an error.
    /// </summary>
    [Fact]
    public async Task ClearCompletedTask_NonexistentTask_ReturnsErrorAsync()
    {
        // Arrange
        var agent = CreateMockAgent("Research", "Research agent");
        var (tools, _) = await CreateToolsWithProviderAsync(agent);
        AIFunction clearTask = GetTool(tools, "background_agents_clear_completed_task");

        // Act
        object? result = await clearTask.InvokeAsync(new AIFunctionArguments
        {
            ["taskId"] = 999,
        });

        // Assert
        Assert.Contains("Error", GetStringResult(result));
    }

    #endregion

    #region StateKeys Tests

    /// <summary>
    /// Verify that the provider exposes state keys.
    /// </summary>
    [Fact]
    public void StateKeys_ReturnsExpectedKeys()
    {
        // Arrange
        var agent = CreateMockAgent("Research", "Research agent");
        var provider = new BackgroundAgentsProvider(new[] { agent });

        // Act
        var keys = provider.StateKeys;

        // Assert
        Assert.NotNull(keys);
        Assert.Equal(2, keys.Count);
    }

    #endregion

    #region CurrentRunContext Isolation Tests

    /// <summary>
    /// Verify that StartBackgroundTask does not corrupt CurrentRunContext of the calling agent.
    /// Because RunAsync is a non-async method that synchronously sets the static AsyncLocal
    /// CurrentRunContext, the provider must isolate the background agent call to prevent overwriting
    /// the outer agent's context.
    /// </summary>
    [Fact]
    public async Task StartBackgroundTask_DoesNotCorruptCurrentRunContextAsync()
    {
        // Arrange
        var tcs = new TaskCompletionSource<AgentResponse>();
        var agent = CreateMockAgentWithRunResult("Research", tcs.Task);
        var (tools, _) = await CreateToolsWithProviderAsync(agent);
        var startTool = GetTool(tools, "background_agents_start_task");

        AgentRunContext? contextBefore = AIAgent.CurrentRunContext;

        // Act — invoke StartBackgroundTask; this calls agent.RunAsync internally.
        var args = new AIFunctionArguments(new Dictionary<string, object?>
        {
            ["agentName"] = "Research",
            ["input"] = "Do work",
            ["description"] = "test task",
        });
        await startTool.InvokeAsync(args);

        // Assert — CurrentRunContext should be unchanged.
        Assert.Equal(contextBefore, AIAgent.CurrentRunContext);

        // Clean up
        tcs.SetResult(new AgentResponse(new List<ChatMessage> { new(ChatRole.Assistant, "done") }));
    }

    #endregion

    #region Options Tests

    /// <summary>
    /// Verify that custom instructions from options override the default instructions but agent list is still injected via placeholder.
    /// </summary>
    [Fact]
    public async Task CustomInstructions_OverridesDefaultInstructionsAsync()
    {
        // Arrange
        var agent = CreateMockAgent("Research", "Research agent");
        const string CustomInstructions = "These are custom background agent instructions.\n{background_agents}";
        var options = new BackgroundAgentsProviderOptions { Instructions = CustomInstructions };
        var provider = new BackgroundAgentsProvider(new[] { agent }, options);
        var context = CreateInvokingContext();

        // Act
        AIContext result = await provider.InvokingAsync(context);

        // Assert — custom instructions replace default, agent list is injected via {sub_agents} placeholder
        Assert.Contains("These are custom background agent instructions.", result.Instructions);
        Assert.Contains("Research", result.Instructions);
    }

    /// <summary>
    /// Verify that default instructions contain tool reference and agent names.
    /// </summary>
    [Fact]
    public async Task DefaultInstructions_ContainsToolReferenceAndAgentListAsync()
    {
        // Arrange
        var agent = CreateMockAgent("Research", "Research agent");
        var provider = new BackgroundAgentsProvider(new[] { agent });
        var context = CreateInvokingContext();

        // Act
        AIContext result = await provider.InvokingAsync(context);

        // Assert — instructions contain tool usage guidance and agent list
        Assert.Contains("background_agents_*", result.Instructions);
        Assert.Contains("background_agents_clear_completed_task", result.Instructions);
        Assert.Contains("Research", result.Instructions);
        Assert.Contains("Research agent", result.Instructions);
    }

    /// <summary>
    /// Verify that a custom AgentListBuilder function is used to build the agent list text.
    /// </summary>
    [Fact]
    public async Task CustomAgentListBuilder_UsedForAgentListAsync()
    {
        // Arrange
        var agent = CreateMockAgent("Research", "Research agent");
        var options = new BackgroundAgentsProviderOptions
        {
            AgentListBuilder = agents => $"Custom list: {string.Join(", ", agents.Keys)}",
        };
        var provider = new BackgroundAgentsProvider(new[] { agent }, options);
        var context = CreateInvokingContext();

        // Act
        AIContext result = await provider.InvokingAsync(context);

        // Assert — custom agent list builder output is in instructions
        Assert.Contains("Custom list: Research", result.Instructions);
        Assert.DoesNotContain("Available background agents:", result.Instructions);
    }

    #endregion

    #region ReleaseSessionAsync Tests

    /// <summary>
    /// Verify that releasing a session cancels and awaits an in-flight background task.
    /// </summary>
    [Fact]
    public async Task ReleaseSessionAsync_CancelsInFlightTaskAsync()
    {
        // Arrange
        var callbackEntered = new TaskCompletionSource<bool>();
        var observedCancellation = new TaskCompletionSource<bool>();
        var agent = CreateMockAgentWithCancellableCallback("Research", async ct =>
        {
            callbackEntered.SetResult(true);
            try
            {
                await Task.Delay(Timeout.Infinite, ct);
            }
            catch (OperationCanceledException)
            {
                observedCancellation.SetResult(true);
                throw;
            }

            return new AgentResponse(new ChatMessage(ChatRole.Assistant, "never"));
        });

        var (tools, provider, session) = await CreateToolsWithSessionAsync(agent);
        AIFunction startBackgroundTask = GetTool(tools, "background_agents_start_task");

        await startBackgroundTask.InvokeAsync(new AIFunctionArguments
        {
            ["agentName"] = "Research",
            ["input"] = "Task 1",
            ["description"] = "First task",
        });

        // Wait until the run is actually executing, otherwise cancellation may prevent the
        // delegate from ever being scheduled and the cancellation signal would never be set.
        Assert.True(await callbackEntered.Task);

        // Act
        await provider.ReleaseSessionAsync(session);

        // Assert — the background run observed cancellation and no tasks remain running.
        Assert.True(await observedCancellation.Task);
        Assert.Empty(provider.GetIncompleteTasks(session));
    }

    /// <summary>
    /// Verify that releasing a session more than once is a no-op.
    /// </summary>
    [Fact]
    public async Task ReleaseSessionAsync_IsIdempotentAsync()
    {
        // Arrange
        var agent = CreateMockAgentWithCancellableCallback("Research", async ct =>
        {
            await Task.Delay(Timeout.Infinite, ct);
            return new AgentResponse(new ChatMessage(ChatRole.Assistant, "never"));
        });
        var (tools, provider, session) = await CreateToolsWithSessionAsync(agent);
        AIFunction startBackgroundTask = GetTool(tools, "background_agents_start_task");

        await startBackgroundTask.InvokeAsync(new AIFunctionArguments
        {
            ["agentName"] = "Research",
            ["input"] = "Task 1",
            ["description"] = "First task",
        });

        // Act
        await provider.ReleaseSessionAsync(session);
        await provider.ReleaseSessionAsync(session);

        // Assert — the second release did not throw and the state remains released.
        Assert.Empty(provider.GetIncompleteTasks(session));
    }

    /// <summary>
    /// Verify that releasing one session does not affect background tasks in another session.
    /// </summary>
    [Fact]
    public async Task ReleaseSessionAsync_DoesNotAffectOtherSessionsAsync()
    {
        // Arrange
        var agent = CreateMockAgentWithCancellableCallback("Research", async ct =>
        {
            await Task.Delay(Timeout.Infinite, ct);
            return new AgentResponse(new ChatMessage(ChatRole.Assistant, "never"));
        });
        var provider = new BackgroundAgentsProvider(new[] { agent });

        var (toolsA, sessionA) = await CreateToolsForSessionAsync(provider);
        var (toolsB, sessionB) = await CreateToolsForSessionAsync(provider);

        await GetTool(toolsA, "background_agents_start_task").InvokeAsync(new AIFunctionArguments
        {
            ["agentName"] = "Research",
            ["input"] = "Task A",
            ["description"] = "Session A task",
        });

        await GetTool(toolsB, "background_agents_start_task").InvokeAsync(new AIFunctionArguments
        {
            ["agentName"] = "Research",
            ["input"] = "Task B",
            ["description"] = "Session B task",
        });

        // Act
        await provider.ReleaseSessionAsync(sessionA);

        // Assert — session B's task is untouched.
        Assert.Empty(provider.GetIncompleteTasks(sessionA));
        Assert.Single(provider.GetIncompleteTasks(sessionB));
    }

    /// <summary>
    /// Verify that releasing with cancelRunning false throws when tasks are still running.
    /// </summary>
    [Fact]
    public async Task ReleaseSessionAsync_CancelRunningFalseWithRunningTask_ThrowsAsync()
    {
        // Arrange
        var tcs = new TaskCompletionSource<AgentResponse>();
        var agent = CreateMockAgentWithRunResult("Research", tcs.Task);
        var (tools, provider, session) = await CreateToolsWithSessionAsync(agent);

        await GetTool(tools, "background_agents_start_task").InvokeAsync(new AIFunctionArguments
        {
            ["agentName"] = "Research",
            ["input"] = "Task 1",
            ["description"] = "First task",
        });

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(
            () => provider.ReleaseSessionAsync(session, cancelRunning: false));

        // Assert — the task is left running because the release was rejected.
        Assert.Single(provider.GetIncompleteTasks(session));

        tcs.SetResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "done")));
    }

    /// <summary>
    /// Verify that releasing with cancelRunning false succeeds when all tasks have completed.
    /// </summary>
    [Fact]
    public async Task ReleaseSessionAsync_CancelRunningFalseWithCompletedTask_SucceedsAsync()
    {
        // Arrange
        var agent = CreateMockAgentWithRunResult("Research", Task.FromResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "done"))));
        var (tools, provider, session) = await CreateToolsWithSessionAsync(agent);

        await GetTool(tools, "background_agents_start_task").InvokeAsync(new AIFunctionArguments
        {
            ["agentName"] = "Research",
            ["input"] = "Task 1",
            ["description"] = "First task",
        });

        // Ensure the run has completed before releasing.
        await GetTool(tools, "background_agents_wait_for_first_completion").InvokeAsync(new AIFunctionArguments
        {
            ["taskIds"] = new List<int> { 1 },
        });

        Assert.Empty(provider.GetIncompleteTasks(session));

        // Act
        await provider.ReleaseSessionAsync(session, cancelRunning: false);

        // Assert — subsequent starts are rejected, confirming the runtime was released.
        object? result = await GetTool(tools, "background_agents_start_task").InvokeAsync(new AIFunctionArguments
        {
            ["agentName"] = "Research",
            ["input"] = "Task 2",
            ["description"] = "Second task",
        });

        Assert.Contains("released", GetStringResult(result));
    }

    /// <summary>
    /// Verify that a task still running when the session is released is recorded as failed.
    /// </summary>
    [Fact]
    public async Task ReleaseSessionAsync_MarksRunningTasksAsFailedAsync()
    {
        // Arrange
        var agent = CreateMockAgentWithCancellableCallback("Research", async ct =>
        {
            await Task.Delay(Timeout.Infinite, ct);
            return new AgentResponse(new ChatMessage(ChatRole.Assistant, "never"));
        });

        var (tools, provider, session) = await CreateToolsWithSessionAsync(agent);

        await GetTool(tools, "background_agents_start_task").InvokeAsync(new AIFunctionArguments
        {
            ["agentName"] = "Research",
            ["input"] = "Task 1",
            ["description"] = "First task",
        });

        // Act
        await provider.ReleaseSessionAsync(session);

        // Assert
        object? result = await GetTool(tools, "background_agents_get_all_tasks").InvokeAsync(new AIFunctionArguments());
        string text = GetStringResult(result);
        Assert.Contains("[Failed]", text);
    }

    /// <summary>
    /// Verify that the start and continue tools return an error after the session is released.
    /// </summary>
    [Fact]
    public async Task ReleaseSessionAsync_ToolsReturnErrorAfterReleaseAsync()
    {
        // Arrange
        var agent = CreateMockAgentWithRunResult("Research", Task.FromResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "done"))));
        var (tools, provider, session) = await CreateToolsWithSessionAsync(agent);

        await GetTool(tools, "background_agents_start_task").InvokeAsync(new AIFunctionArguments
        {
            ["agentName"] = "Research",
            ["input"] = "Task 1",
            ["description"] = "First task",
        });

        await provider.ReleaseSessionAsync(session);

        // Act
        object? startResult = await GetTool(tools, "background_agents_start_task").InvokeAsync(new AIFunctionArguments
        {
            ["agentName"] = "Research",
            ["input"] = "Task 2",
            ["description"] = "Second task",
        });

        object? continueResult = await GetTool(tools, "background_agents_continue_task").InvokeAsync(new AIFunctionArguments
        {
            ["taskId"] = 1,
            ["text"] = "More work",
        });

        // Assert
        Assert.Contains("released", GetStringResult(startResult));
        Assert.Contains("released", GetStringResult(continueResult));
    }

    /// <summary>
    /// Verify that a task ignoring cancellation does not block the release beyond the timeout.
    /// </summary>
    [Fact]
    public async Task ReleaseSessionAsync_TimeoutAbandonsUncooperativeTaskAsync()
    {
        // Arrange — the run never observes its cancellation token.
        var tcs = new TaskCompletionSource<AgentResponse>();
        var agent = CreateMockAgentWithRunResult("Research", tcs.Task);
        var (tools, provider, session) = await CreateToolsWithSessionAsync(agent);

        await GetTool(tools, "background_agents_start_task").InvokeAsync(new AIFunctionArguments
        {
            ["agentName"] = "Research",
            ["input"] = "Task 1",
            ["description"] = "First task",
        });

        // Act
        await provider.ReleaseSessionAsync(session, timeout: TimeSpan.FromMilliseconds(50));

        // Assert — release completed despite the task still being pending.
        Assert.False(tcs.Task.IsCompleted);
        Assert.Empty(provider.GetIncompleteTasks(session));

        tcs.SetResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "late")));
    }

    /// <summary>
    /// Verify that releasing a null session throws.
    /// </summary>
    [Fact]
    public async Task ReleaseSessionAsync_NullSession_ThrowsAsync()
    {
        // Arrange
        var agent = CreateMockAgent("Research", "Research agent");
        var provider = new BackgroundAgentsProvider(new[] { agent });

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(() => provider.ReleaseSessionAsync(null!));
    }

    /// <summary>
    /// Verify that a task which completed but has not yet been refreshed keeps its result instead of
    /// being reported as canceled by the release.
    /// </summary>
    [Fact]
    public async Task ReleaseSessionAsync_CompletedButUnrefreshedTask_KeepsResultAsync()
    {
        // Arrange
        var runEntered = new TaskCompletionSource<bool>();
        var agent = CreateMockAgentWithCancellableCallback("Research", _ =>
        {
            runEntered.TrySetResult(true);
            return Task.FromResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "Result 1")));
        });
        var (tools, provider, session) = await CreateToolsWithSessionAsync(agent);

        await GetTool(tools, "background_agents_start_task").InvokeAsync(new AIFunctionArguments
        {
            ["agentName"] = "Research",
            ["input"] = "Task 1",
            ["description"] = "First task",
        });

        // Wait until the run has actually started, so it cannot be cancelled before it produces a result.
        // The persisted state is never refreshed, so the task is still marked Running when the release begins.
        Assert.True(await runEntered.Task);

        // Act
        await provider.ReleaseSessionAsync(session);

        // Assert — the successful result is preserved rather than overwritten with a release failure.
        object? result = await GetTool(tools, "background_agents_get_task_results").InvokeAsync(new AIFunctionArguments
        {
            ["taskId"] = 1,
        });

        Assert.Equal("Result 1", GetStringResult(result));
    }

    /// <summary>
    /// Verify that an invalid timeout is rejected before the session is released.
    /// </summary>
    [Fact]
    public async Task ReleaseSessionAsync_NegativeTimeout_ThrowsWithoutReleasingAsync()
    {
        // Arrange
        var tcs = new TaskCompletionSource<AgentResponse>();
        var agent = CreateMockAgentWithRunResult("Research", tcs.Task);
        var (tools, provider, session) = await CreateToolsWithSessionAsync(agent);

        await GetTool(tools, "background_agents_start_task").InvokeAsync(new AIFunctionArguments
        {
            ["agentName"] = "Research",
            ["input"] = "Task 1",
            ["description"] = "First task",
        });

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentOutOfRangeException>(
            () => provider.ReleaseSessionAsync(session, timeout: TimeSpan.FromSeconds(-5)));

        // Assert — the session was not released, so the task is untouched and new tasks can still start.
        Assert.Single(provider.GetIncompleteTasks(session));

        object? startResult = await GetTool(tools, "background_agents_start_task").InvokeAsync(new AIFunctionArguments
        {
            ["agentName"] = "Research",
            ["input"] = "Task 2",
            ["description"] = "Second task",
        });

        Assert.DoesNotContain("released", GetStringResult(startResult));

        tcs.SetResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "done")));
    }

    /// <summary>
    /// Verify that a failure to cancel the running tasks leaves the session un-released, rather than marking it
    /// released while its tasks are still running.
    /// </summary>
    [Fact]
    public async Task ReleaseSessionAsync_CancellationThrows_LeavesSessionUnreleasedAsync()
    {
        // Arrange — a cancellation callback that throws makes CancellationTokenSource.Cancel throw.
        var runEntered = new TaskCompletionSource<bool>();
        var runGate = new TaskCompletionSource<bool>();
        var agent = CreateMockAgentWithCancellableCallback("Research", async ct =>
        {
            ct.Register(() => throw new InvalidOperationException("Cancellation callback failed."));
            runEntered.TrySetResult(true);
            await runGate.Task;
            return new AgentResponse(new ChatMessage(ChatRole.Assistant, "done"));
        });
        var (tools, provider, session) = await CreateToolsWithSessionAsync(agent);

        await GetTool(tools, "background_agents_start_task").InvokeAsync(new AIFunctionArguments
        {
            ["agentName"] = "Research",
            ["input"] = "Task 1",
            ["description"] = "First task",
        });

        Assert.True(await runEntered.Task);

        // Act & Assert
        await Assert.ThrowsAsync<AggregateException>(() => provider.ReleaseSessionAsync(session));

        // Assert — the release did not take effect, so the session remains usable and can be released again.
        BackgroundAgentRuntimeState runtimeState = GetRuntimeState(provider, session);
        Assert.False(runtimeState.IsReleased);
        Assert.Null(runtimeState.ReleaseCompletion);
        Assert.Single(provider.GetIncompleteTasks(session));

        runGate.SetResult(true);
    }

    /// <summary>
    /// Verify that a start racing with a release does not register an untracked background task.
    /// </summary>
    [Fact]
    public async Task ReleaseSessionAsync_DuringStart_RefusesToRegisterTaskAsync()
    {
        // Arrange — session creation blocks so the release can happen mid-start.
        var sessionCreationGate = new TaskCompletionSource<bool>();
        var runStarted = false;
        var agent = CreateMockAgentWithGatedSession(
            "Research",
            sessionCreationGate.Task,
            () =>
            {
                runStarted = true;
                return Task.FromResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "done")));
            });

        var (tools, provider, session) = await CreateToolsWithSessionAsync(agent);

        Task<object?> startTask = GetTool(tools, "background_agents_start_task").InvokeAsync(new AIFunctionArguments
        {
            ["agentName"] = "Research",
            ["input"] = "Task 1",
            ["description"] = "First task",
        }).AsTask();

        // Act — release while the start is awaiting session creation, then let creation finish.
        await provider.ReleaseSessionAsync(session);
        sessionCreationGate.SetResult(true);

        object? startResult = await startTask;

        // Assert — the start was refused, no run was launched, and no task was recorded.
        Assert.Contains("released", GetStringResult(startResult));
        Assert.False(runStarted);
        Assert.Empty(provider.GetIncompleteTasks(session));

        object? allTasks = await GetTool(tools, "background_agents_get_all_tasks").InvokeAsync(new AIFunctionArguments());
        Assert.Equal("No tasks.", GetStringResult(allTasks));
    }

    /// <summary>
    /// Verify that a release racing with a start never leaves behind a background agent session, which would
    /// otherwise be retained for the lifetime of the parent session.
    /// </summary>
    [Fact]
    public async Task ReleaseSessionAsync_ConcurrentWithStart_LeavesNoRegisteredSessionsAsync()
    {
        // Registering the task and its session under a single lock makes this invariant hold for every possible
        // interleaving. Repeat so that a range of interleavings is exercised.
        for (int i = 0; i < 50; i++)
        {
            // Arrange
            var agent = CreateMockAgentWithCancellableCallback(
                "Research",
                _ => Task.FromResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "done"))));
            var (tools, provider, session) = await CreateToolsWithSessionAsync(agent);

            // Act — start a task and release the session concurrently.
            Task<object?> startTask = GetTool(tools, "background_agents_start_task").InvokeAsync(new AIFunctionArguments
            {
                ["agentName"] = "Research",
                ["input"] = "Task 1",
                ["description"] = "First task",
            }).AsTask();

            Task releaseTask = Task.Run(() => provider.ReleaseSessionAsync(session));

            await startTask;
            await releaseTask;

            // Assert — the release owns the cleanup, so no runtime reference may survive it.
            BackgroundAgentRuntimeState runtimeState = GetRuntimeState(provider, session);
            Assert.Empty(runtimeState.BackgroundTaskSessions);
            Assert.Empty(runtimeState.InFlightTasks);
            Assert.Empty(runtimeState.TaskCancellations);
        }
    }

    /// <summary>
    /// Verify that a caller releasing a session while another release is in progress waits for that release to
    /// finish rather than returning while tasks are still being cleaned up.
    /// </summary>
    [Fact]
    public async Task ReleaseSessionAsync_ConcurrentReleases_AllWaitForCleanupAsync()
    {
        // Arrange — the run ignores cancellation, so the first release stays in its wait until the gate opens.
        var runEntered = new TaskCompletionSource<bool>();
        var runGate = new TaskCompletionSource<bool>();
        var agent = CreateMockAgentWithCancellableCallback("Research", async _ =>
        {
            runEntered.TrySetResult(true);
            await runGate.Task;
            return new AgentResponse(new ChatMessage(ChatRole.Assistant, "done"));
        });
        var (tools, provider, session) = await CreateToolsWithSessionAsync(agent);

        await GetTool(tools, "background_agents_start_task").InvokeAsync(new AIFunctionArguments
        {
            ["agentName"] = "Research",
            ["input"] = "Task 1",
            ["description"] = "First task",
        });

        Assert.True(await runEntered.Task);

        // Act — the first release blocks on the running task; the second arrives while it is still waiting.
        Task firstRelease = provider.ReleaseSessionAsync(session, timeout: Timeout.InfiniteTimeSpan);
        Task secondRelease = provider.ReleaseSessionAsync(session, timeout: Timeout.InfiniteTimeSpan);

        // Assert — the second caller must not report a completed release while cleanup is still outstanding.
        await Task.Delay(50);
        Assert.False(firstRelease.IsCompleted);
        Assert.False(secondRelease.IsCompleted);

        runGate.SetResult(true);
        await firstRelease;
        await secondRelease;

        // Assert — both callers observe fully cleaned-up state.
        BackgroundAgentRuntimeState runtimeState = GetRuntimeState(provider, session);
        Assert.Empty(runtimeState.InFlightTasks);
        Assert.Empty(runtimeState.BackgroundTaskSessions);
        Assert.Empty(runtimeState.TaskCancellations);
    }

    /// <summary>
    /// Verify that a caller waiting on an in-progress release observes its own cancellation token rather than
    /// being held up by the releasing caller.
    /// </summary>
    [Fact]
    public async Task ReleaseSessionAsync_ConcurrentRelease_ObservesOwnCancellationAsync()
    {
        // Arrange
        var runEntered = new TaskCompletionSource<bool>();
        var runGate = new TaskCompletionSource<bool>();
        var agent = CreateMockAgentWithCancellableCallback("Research", async _ =>
        {
            runEntered.TrySetResult(true);
            await runGate.Task;
            return new AgentResponse(new ChatMessage(ChatRole.Assistant, "done"));
        });
        var (tools, provider, session) = await CreateToolsWithSessionAsync(agent);

        await GetTool(tools, "background_agents_start_task").InvokeAsync(new AIFunctionArguments
        {
            ["agentName"] = "Research",
            ["input"] = "Task 1",
            ["description"] = "First task",
        });

        Assert.True(await runEntered.Task);

        Task firstRelease = provider.ReleaseSessionAsync(session, timeout: Timeout.InfiniteTimeSpan);

        // Act & Assert — the second caller gives up on its own token instead of waiting for the first.
        using var cts = new CancellationTokenSource();
        cts.Cancel();

        await Assert.ThrowsAnyAsync<OperationCanceledException>(
            () => provider.ReleaseSessionAsync(session, cancellationToken: cts.Token));

        Assert.False(firstRelease.IsCompleted);

        runGate.SetResult(true);
        await firstRelease;
    }

    /// <summary>
    /// Verify that a caller waiting on an in-progress release does not inherit the failure of the caller that
    /// started it.
    /// </summary>
    [Fact]
    public async Task ReleaseSessionAsync_ConcurrentRelease_DoesNotInheritFirstCallerFailureAsync()
    {
        // Arrange — the run never completes, so the first release only ends when its own token is cancelled.
        var runEntered = new TaskCompletionSource<bool>();
        var runGate = new TaskCompletionSource<bool>();
        var agent = CreateMockAgentWithCancellableCallback("Research", async _ =>
        {
            runEntered.TrySetResult(true);
            await runGate.Task;
            return new AgentResponse(new ChatMessage(ChatRole.Assistant, "done"));
        });
        var (tools, provider, session) = await CreateToolsWithSessionAsync(agent);

        await GetTool(tools, "background_agents_start_task").InvokeAsync(new AIFunctionArguments
        {
            ["agentName"] = "Research",
            ["input"] = "Task 1",
            ["description"] = "First task",
        });

        Assert.True(await runEntered.Task);

        using var cts = new CancellationTokenSource();
        Task firstRelease = provider.ReleaseSessionAsync(session, timeout: Timeout.InfiniteTimeSpan, cancellationToken: cts.Token);
        Task secondRelease = provider.ReleaseSessionAsync(session, timeout: Timeout.InfiniteTimeSpan);

        // Act — the first caller abandons its wait.
        cts.Cancel();

        // Assert — the second caller still completes successfully once the cleanup has run.
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => firstRelease);
        await secondRelease;

        BackgroundAgentRuntimeState runtimeState = GetRuntimeState(provider, session);
        Assert.Empty(runtimeState.InFlightTasks);
        Assert.Empty(runtimeState.BackgroundTaskSessions);
        Assert.Empty(runtimeState.TaskCancellations);

        runGate.SetResult(true);
    }

    #endregion

    #region Helper Methods

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

    private static AIAgent CreateMockAgentWithCallback(string name, Func<Task<AgentResponse>> callback)
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
            .Returns(callback);
        return mock.Object;
    }

    private static async Task<(IEnumerable<AITool> Tools, BackgroundAgentsProvider Provider)> CreateToolsWithProviderAsync(AIAgent agent)
    {
        var provider = new BackgroundAgentsProvider(new[] { agent });
        var context = CreateInvokingContext();

        AIContext result = await provider.InvokingAsync(context);
        return (result.Tools!, provider);
    }

    private static AIAgent CreateMockAgentWithCancellableCallback(string name, Func<CancellationToken, Task<AgentResponse>> callback)
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
            .Returns((IEnumerable<ChatMessage> _, AgentSession _, AgentRunOptions _, CancellationToken ct) => callback(ct));
        return mock.Object;
    }

    private static AIAgent CreateMockAgentWithGatedSession(string name, Task sessionGate, Func<Task<AgentResponse>> callback)
    {
        var mock = new Mock<AIAgent>();
        mock.SetupGet(a => a.Name).Returns(name);
        mock.Protected()
            .Setup<ValueTask<AgentSession>>(
                "CreateSessionCoreAsync",
                ItExpr.IsAny<CancellationToken>())
            .Returns(async () =>
            {
                await sessionGate;
                return new ChatClientAgentSession();
            });
        mock.Protected()
            .Setup<Task<AgentResponse>>(
                "RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession>(),
                ItExpr.IsAny<AgentRunOptions>(),
                ItExpr.IsAny<CancellationToken>())
            .Returns(callback);
        return mock.Object;
    }

    private static async Task<(IEnumerable<AITool> Tools, BackgroundAgentsProvider Provider, AgentSession Session)> CreateToolsWithSessionAsync(AIAgent agent)
    {
        var provider = new BackgroundAgentsProvider(new[] { agent });
        var (tools, session) = await CreateToolsForSessionAsync(provider);
        return (tools, provider, session);
    }

    private static async Task<(IEnumerable<AITool> Tools, AgentSession Session)> CreateToolsForSessionAsync(BackgroundAgentsProvider provider)
    {
        var mockAgent = new Mock<AIAgent>().Object;
        var session = new ChatClientAgentSession();
#pragma warning disable MAAI001
        var context = new AIContextProvider.InvokingContext(mockAgent, session, new AIContext());
#pragma warning restore MAAI001

        AIContext result = await provider.InvokingAsync(context);
        return (result.Tools!, session);
    }

    private static BackgroundAgentRuntimeState GetRuntimeState(BackgroundAgentsProvider provider, AgentSession session)
    {
        // The runtime state key is the second of the provider's state keys.
        string runtimeStateKey = provider.StateKeys[1];
        Assert.True(session.StateBag.TryGetValue(runtimeStateKey, out BackgroundAgentRuntimeState? runtimeState, AgentJsonUtilities.DefaultOptions));
        return runtimeState!;
    }

    private static AIContextProvider.InvokingContext CreateInvokingContext()
    {
        var mockAgent = new Mock<AIAgent>().Object;
        var session = new ChatClientAgentSession();
#pragma warning disable MAAI001
        return new AIContextProvider.InvokingContext(mockAgent, session, new AIContext());
#pragma warning restore MAAI001
    }

    private static AIFunction GetTool(IEnumerable<AITool> tools, string name)
    {
        return (AIFunction)tools.First(t => t is AIFunction f && f.Name == name);
    }

    private static string GetStringResult(object? result)
    {
        var element = Assert.IsType<JsonElement>(result);
        return element.GetString()!;
    }

    #endregion
}
