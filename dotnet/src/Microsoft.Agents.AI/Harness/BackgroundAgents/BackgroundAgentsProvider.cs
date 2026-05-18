// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// An <see cref="AIContextProvider"/> that enables an agent to delegate work to background agents asynchronously.
/// </summary>
/// <remarks>
/// <para>
/// The <see cref="BackgroundAgentsProvider"/> allows a parent agent to start background tasks on child agents,
/// wait for their completion, and retrieve results. Each background task runs in its own session and
/// executes concurrently.
/// </para>
/// <para>
/// This provider exposes the following tools to the agent:
/// <list type="bullet">
/// <item><description><c>BackgroundAgents_StartTask</c> — Start a background task on a named agent with text input. Returns the task ID.</description></item>
/// <item><description><c>BackgroundAgents_WaitForFirstCompletion</c> — Block until the first of the specified tasks completes. Returns the completed task's ID.</description></item>
/// <item><description><c>BackgroundAgents_GetTaskResults</c> — Retrieve the text output of a completed background task.</description></item>
/// <item><description><c>BackgroundAgents_GetAllTasks</c> — List all background tasks with their IDs, statuses, descriptions, and agent names.</description></item>
/// <item><description><c>BackgroundAgents_ContinueTask</c> — Send follow-up input to a completed background task's session to resume work.</description></item>
/// <item><description><c>BackgroundAgents_ClearCompletedTask</c> — Remove a completed background task and release its session to free memory.</description></item>
/// </list>
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class BackgroundAgentsProvider : AIContextProvider
{
    private const string DefaultInstructions =
        """
        ## BackgroundAgents
        You have access to background agents that can perform work on your behalf.

        - Use the `BackgroundAgents_*` list of tools to start tasks on background agents and check their results.
        - Creating a background task does not block, and background tasks run concurrently.
        - Important: Always wait for outstanding tasks to finish before you finish processing.
        - Important: After retrieving results from a completed task, clear it with BackgroundAgents_ClearCompletedTask to free memory, unless you plan to continue it with BackgroundAgents_ContinueTask.

        {background_agents}
        """;

    private readonly Dictionary<string, AIAgent> _agents;
    private readonly ProviderSessionState<BackgroundAgentState> _sessionState;
    private readonly ProviderSessionState<BackgroundAgentRuntimeState> _runtimeSessionState;
    private readonly string _instructions;
    private IReadOnlyList<string>? _stateKeys;

    /// <summary>
    /// Initializes a new instance of the <see cref="BackgroundAgentsProvider"/> class.
    /// </summary>
    /// <param name="agents">The collection of background agents available for delegation.</param>
    /// <param name="options">Optional settings controlling the provider behavior.</param>
    /// <exception cref="ArgumentNullException"><paramref name="agents"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">An agent has a null or empty name, or agent names are not unique.</exception>
    public BackgroundAgentsProvider(IEnumerable<AIAgent> agents, BackgroundAgentsProviderOptions? options = null)
    {
        _ = Throw.IfNull(agents);

        this._agents = ValidateAndBuildAgentDictionary(agents);

        string baseInstructions = options?.Instructions ?? DefaultInstructions;
        string agentListText = options?.AgentListBuilder is not null
            ? options.AgentListBuilder(this._agents)
            : BuildDefaultAgentListText(this._agents);
        this._instructions = baseInstructions.Replace("{background_agents}", agentListText);

        this._sessionState = new ProviderSessionState<BackgroundAgentState>(
            _ => new BackgroundAgentState(),
            this.GetType().Name,
            AgentJsonUtilities.DefaultOptions);

        this._runtimeSessionState = new ProviderSessionState<BackgroundAgentRuntimeState>(
            _ => new BackgroundAgentRuntimeState(),
            this.GetType().Name + "_Runtime",
            AgentJsonUtilities.DefaultOptions);
    }

    /// <inheritdoc />
    public override IReadOnlyList<string> StateKeys => this._stateKeys ??= [this._sessionState.StateKey, this._runtimeSessionState.StateKey];

    /// <inheritdoc />
    protected override ValueTask<AIContext> ProvideAIContextAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        BackgroundAgentState state = this._sessionState.GetOrInitializeState(context.Session);
        BackgroundAgentRuntimeState runtimeState = this._runtimeSessionState.GetOrInitializeState(context.Session);

        return new ValueTask<AIContext>(new AIContext
        {
            Instructions = this._instructions,
            Tools = this.CreateTools(state, runtimeState, context.Session),
        });
    }

    /// <summary>
    /// Validates the agent collection and builds a case-insensitive name dictionary.
    /// </summary>
    private static Dictionary<string, AIAgent> ValidateAndBuildAgentDictionary(IEnumerable<AIAgent> agents)
    {
        var dict = new Dictionary<string, AIAgent>(StringComparer.OrdinalIgnoreCase);
        foreach (AIAgent agent in agents)
        {
            if (string.IsNullOrWhiteSpace(agent.Name))
            {
                throw new ArgumentException("All background agents must have a non-empty Name.", nameof(agents));
            }

            if (dict.ContainsKey(agent.Name))
            {
                throw new ArgumentException($"Duplicate background agent name: '{agent.Name}'. Agent names must be unique (case-insensitive).", nameof(agents));
            }

            dict[agent.Name] = agent;
        }

        if (dict.Count == 0)
        {
            throw new ArgumentException("At least one background agent must be provided.", nameof(agents));
        }

        return dict;
    }

    /// <summary>
    /// Builds the default text listing available background agents and their descriptions.
    /// </summary>
    private static string BuildDefaultAgentListText(IReadOnlyDictionary<string, AIAgent> agents)
    {
        var sb = new StringBuilder();
        sb.AppendLine("Available background agents:");
        foreach (var kvp in agents)
        {
            sb.Append("- ").Append(kvp.Key);
            if (!string.IsNullOrWhiteSpace(kvp.Value.Description))
            {
                sb.Append(": ").Append(kvp.Value.Description);
            }

            sb.AppendLine();
        }

        return sb.ToString();
    }

    /// <summary>
    /// Refreshes the status of in-flight tasks in the given state for the specified session.
    /// </summary>
    private void TryRefreshTaskState(BackgroundAgentState state, BackgroundAgentRuntimeState runtimeState, AgentSession? session)
    {
        bool changed = false;
        foreach (BackgroundTaskInfo task in state.Tasks)
        {
            if (task.Status != BackgroundTaskStatus.Running)
            {
                continue;
            }

            if (!runtimeState.InFlightTasks.TryGetValue(task.Id, out Task<AgentResponse>? inFlight))
            {
                // In-flight reference lost (e.g., after restart/deserialization).
                task.Status = BackgroundTaskStatus.Lost;
                changed = true;
                continue;
            }

            if (inFlight.IsCompleted)
            {
                FinalizeTask(task, inFlight, runtimeState);
                changed = true;
            }
        }

        if (changed)
        {
            this._sessionState.SaveState(session, state);
        }
    }

    /// <summary>
    /// Finalizes a task by extracting results from the completed Task and updating the BackgroundTaskInfo.
    /// </summary>
    private static void FinalizeTask(BackgroundTaskInfo taskInfo, Task<AgentResponse> completedTask, BackgroundAgentRuntimeState runtimeState)
    {
        if (completedTask.Status == TaskStatus.RanToCompletion)
        {
            taskInfo.Status = BackgroundTaskStatus.Completed;
#pragma warning disable VSTHRD002 // Avoid problematic synchronous waits — task is already completed
            taskInfo.ResultText = completedTask.Result.Text;
#pragma warning restore VSTHRD002
        }
        else if (completedTask.IsFaulted)
        {
            taskInfo.Status = BackgroundTaskStatus.Failed;
            taskInfo.ErrorText = completedTask.Exception?.InnerException?.Message ?? completedTask.Exception?.Message ?? "Unknown error";
        }
        else if (completedTask.IsCanceled)
        {
            taskInfo.Status = BackgroundTaskStatus.Failed;
            taskInfo.ErrorText = "Task was canceled.";
        }

        runtimeState.InFlightTasks.Remove(taskInfo.Id);
    }

    private AITool[] CreateTools(BackgroundAgentState state, BackgroundAgentRuntimeState runtimeState, AgentSession? session)
    {
        var serializerOptions = AgentJsonUtilities.DefaultOptions;

        return
        [
            AIFunctionFactory.Create(
                async (
                    [Description("The name of the background agent to delegate the task to.")] string agentName,
                    [Description("The request to pass to the background agent.")] string input,
                    [Description("A description of the task used to identify the task later.")] string description) =>
                {
                    if (!this._agents.TryGetValue(agentName, out AIAgent? agent))
                    {
                        return $"Error: No background agent found with name '{agentName}'. Available agents: {string.Join(", ", this._agents.Keys)}";
                    }

                    int taskId = state.NextTaskId++;
                    var taskInfo = new BackgroundTaskInfo
                    {
                        Id = taskId,
                        AgentName = agentName,
                        Description = description,
                        Status = BackgroundTaskStatus.Running,
                    };
                    state.Tasks.Add(taskInfo);

                    // Create a dedicated session for this background task so it can be continued later.
                    AgentSession subSession = await agent.CreateSessionAsync().ConfigureAwait(false);

                    // Wrap in Task.Run to fork the ExecutionContext. AIAgent.RunAsync is a non-async
                    // method that synchronously sets the static AsyncLocal CurrentRunContext. Without
                    // this isolation, the background agent's RunAsync would overwrite the outer (calling)
                    // agent's CurrentRunContext, corrupting all subsequent tool invocations in the
                    // same FICC batch.
                    runtimeState.InFlightTasks[taskId] = Task.Run(() => agent.RunAsync(input, subSession));
                    runtimeState.BackgroundTaskSessions[taskId] = subSession;

                    this._sessionState.SaveState(session, state);
                    return $"Background task {taskId} started on agent '{agentName}'.";
                },
                new AIFunctionFactoryOptions
                {
                    Name = "BackgroundAgents_StartTask",
                    Description = "Start a background task on a named background agent. Returns a confirmation message containing the task ID.",
                    SerializerOptions = serializerOptions,
                }),

            AIFunctionFactory.Create(
                async (List<int> taskIds) =>
                {
                    if (taskIds.Count == 0)
                    {
                        return "Error: No task IDs provided.";
                    }

                    // Collect in-flight tasks matching the requested IDs (including already-completed ones,
                    // since Task.WhenAny returns immediately for completed tasks).
                    var waitableTasks = new List<(int Id, Task<AgentResponse> Task)>();
                    foreach (int id in taskIds)
                    {
                        if (runtimeState.InFlightTasks.TryGetValue(id, out Task<AgentResponse>? inFlight))
                        {
                            waitableTasks.Add((id, inFlight));
                        }
                    }

                    if (waitableTasks.Count == 0)
                    {
                        // Refresh state to catch any that completed.
                        this.TryRefreshTaskState(state, runtimeState, session);
                        this._sessionState.SaveState(session, state);

                        // Check if any of the requested IDs are already complete.
                        BackgroundTaskInfo? alreadyComplete = state.Tasks.FirstOrDefault(t => taskIds.Contains(t.Id) && t.Status != BackgroundTaskStatus.Running);
                        if (alreadyComplete is not null)
                        {
                            return $"Task {alreadyComplete.Id} is not running; current status: {alreadyComplete.Status}.";
                        }

                        return "Error: None of the specified task IDs correspond to running tasks.";
                    }

                    // Wait for the first one to complete.
                    Task completedTask = await Task.WhenAny(waitableTasks.Select(t => t.Task)).ConfigureAwait(false);

                    // Find which ID completed.
                    var completedEntry = waitableTasks.First(t => t.Task == completedTask);

                    // Finalize the completed task.
                    BackgroundTaskInfo? taskInfo = state.Tasks.FirstOrDefault(t => t.Id == completedEntry.Id);
                    if (taskInfo is not null)
                    {
                        FinalizeTask(taskInfo, completedEntry.Task, runtimeState);
                        this._sessionState.SaveState(session, state);
                    }

                    return $"Task {completedEntry.Id} finished with status: {taskInfo?.Status.ToString() ?? "Unknown"}.";
                },
                new AIFunctionFactoryOptions
                {
                    Name = "BackgroundAgents_WaitForFirstCompletion",
                    Description = "Block until the first of the specified background tasks completes. Provide one or more task IDs. Returns a status message containing the ID of the task that completed first.",
                    SerializerOptions = serializerOptions,
                }),

            AIFunctionFactory.Create(
                (int taskId) =>
                {
                    this.TryRefreshTaskState(state, runtimeState, session);

                    BackgroundTaskInfo? taskInfo = state.Tasks.FirstOrDefault(t => t.Id == taskId);
                    if (taskInfo is null)
                    {
                        return $"Error: No task found with ID {taskId}.";
                    }

                    return taskInfo.Status switch
                    {
                        BackgroundTaskStatus.Completed => taskInfo.ResultText ?? "(no output)",
                        BackgroundTaskStatus.Failed => $"Task failed: {taskInfo.ErrorText ?? "Unknown error"}",
                        BackgroundTaskStatus.Lost => "Task state was lost (reference unavailable).",
                        BackgroundTaskStatus.Running => $"Task {taskId} is still running.",
                        _ => $"Task {taskId} has status: {taskInfo.Status}.",
                    };
                },
                new AIFunctionFactoryOptions
                {
                    Name = "BackgroundAgents_GetTaskResults",
                    Description = "Get the text output of a background task by its ID. Returns the result text if complete, or status information if still running or failed.",
                    SerializerOptions = serializerOptions,
                }),

            AIFunctionFactory.Create(
                () =>
                {
                    this.TryRefreshTaskState(state, runtimeState, session);

                    if (state.Tasks.Count == 0)
                    {
                        return "No tasks.";
                    }

                    var sb = new StringBuilder();
                    sb.AppendLine("Tasks:");
                    foreach (BackgroundTaskInfo task in state.Tasks)
                    {
                        sb.Append("- Task ").Append(task.Id).Append(" [").Append(task.Status).Append("] (").Append(task.AgentName).Append("): ").AppendLine(task.Description);
                    }

                    return sb.ToString();
                },
                new AIFunctionFactoryOptions
                {
                    Name = "BackgroundAgents_GetAllTasks",
                    Description = "List all background tasks with their IDs, statuses, agent names, and descriptions.",
                    SerializerOptions = serializerOptions,
                }),

            AIFunctionFactory.Create(
                (int taskId, string text) =>
                {
                    this.TryRefreshTaskState(state, runtimeState, session);

                    BackgroundTaskInfo? taskInfo = state.Tasks.FirstOrDefault(t => t.Id == taskId);
                    if (taskInfo is null)
                    {
                        return $"Error: No task found with ID {taskId}.";
                    }

                    if (taskInfo.Status == BackgroundTaskStatus.Lost)
                    {
                        return $"Error: Task {taskId} cannot be continued because its session was lost (e.g., after a session restore). Start a new task instead.";
                    }

                    if (taskInfo.Status == BackgroundTaskStatus.Running)
                    {
                        return $"Error: Task {taskId} is still running. Wait for it to complete before continuing.";
                    }

                    if (!this._agents.TryGetValue(taskInfo.AgentName, out AIAgent? agent))
                    {
                        return $"Error: Agent '{taskInfo.AgentName}' is no longer available.";
                    }

                    if (!runtimeState.BackgroundTaskSessions.TryGetValue(taskId, out AgentSession? subSession))
                    {
                        return $"Error: Session for task {taskId} is no longer available.";
                    }

                    // Reset task state and start a new run on the existing session.
                    taskInfo.Status = BackgroundTaskStatus.Running;
                    taskInfo.ResultText = null;
                    taskInfo.ErrorText = null;

                    // Wrap in Task.Run to isolate the ExecutionContext (see StartBackgroundTask comment).
                    runtimeState.InFlightTasks[taskId] = Task.Run(() => agent.RunAsync(text, subSession));

                    this._sessionState.SaveState(session, state);
                    return $"Task {taskId} continued with new input.";
                },
                new AIFunctionFactoryOptions
                {
                    Name = "BackgroundAgents_ContinueTask",
                    Description = "Send follow-up input to a completed or failed background task to resume its work. The background task's session is preserved, so the agent retains conversational context.",
                    SerializerOptions = serializerOptions,
                }),

            AIFunctionFactory.Create(
                (int taskId) =>
                {
                    this.TryRefreshTaskState(state, runtimeState, session);

                    BackgroundTaskInfo? taskInfo = state.Tasks.FirstOrDefault(t => t.Id == taskId);
                    if (taskInfo is null)
                    {
                        return $"Error: No task found with ID {taskId}.";
                    }

                    if (taskInfo.Status == BackgroundTaskStatus.Running)
                    {
                        return $"Error: Task {taskId} is still running. Wait for it to complete before clearing.";
                    }

                    // Remove the task from state.
                    state.Tasks.Remove(taskInfo);

                    // Clean up runtime references.
                    runtimeState.InFlightTasks.Remove(taskId);
                    runtimeState.BackgroundTaskSessions.Remove(taskId);

                    this._sessionState.SaveState(session, state);
                    return $"Task {taskId} cleared.";
                },
                new AIFunctionFactoryOptions
                {
                    Name = "BackgroundAgents_ClearCompletedTask",
                    Description = "Remove a completed or failed background task and release its session to free memory. Use this after retrieving results when you no longer need to continue the task.",
                    SerializerOptions = serializerOptions,
                }),
        ];
    }
}
