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
