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
/// An <see cref="AIContextProvider"/> that enables an agent to delegate work to sub-agents asynchronously.
/// </summary>
/// <remarks>
/// <para>
/// The <see cref="SubAgentsProvider"/> allows a parent agent to start sub-tasks on child agents,
/// wait for their completion, and retrieve results. Each sub-task runs in its own session and
/// executes concurrently.
/// </para>
/// <para>
/// This provider exposes the following tools to the agent:
/// <list type="bullet">
/// <item><description><c>SubAgents_StartTask</c> — Start a sub-task on a named agent with text input. Returns the task ID.</description></item>
/// <item><description><c>SubAgents_WaitForFirstCompletion</c> — Block until the first of the specified tasks completes. Returns the completed task's ID.</description></item>
/// <item><description><c>SubAgents_GetTaskResults</c> — Retrieve the text output of a completed sub-task.</description></item>
/// <item><description><c>SubAgents_GetAllTasks</c> — List all sub-tasks with their IDs, statuses, descriptions, and agent names.</description></item>
/// <item><description><c>SubAgents_ContinueTask</c> — Send follow-up input to a completed sub-task's session to resume work.</description></item>
/// <item><description><c>SubAgents_ClearCompletedTask</c> — Remove a completed sub-task and release its session to free memory.</description></item>
/// </list>
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class SubAgentsProvider : AIContextProvider
{
    private const string DefaultInstructions =
        """
        ## SubAgents
        You have access to sub-agents that can perform work on your behalf.

        - Use the `SubAgents_*` list of tools to start tasks on sub agents and check their results.
        - Creating a sub task does not block, and sub-tasks run concurrently.
        - Important: Always wait for outstanding tasks to finish before you finish processing.
        - Important: After retrieving results from a completed task, clear it with SubAgents_ClearCompletedTask to free memory, unless you plan to continue it with SubAgents_ContinueTask.

        {sub_agents}
        """;

    private readonly Dictionary<string, AIAgent> _agents;
    private readonly ProviderSessionState<SubAgentState> _sessionState;
    private readonly ProviderSessionState<SubAgentRuntimeState> _runtimeSessionState;
    private readonly string _instructions;
    private IReadOnlyList<string>? _stateKeys;

    /// <summary>
    /// Initializes a new instance of the <see cref="SubAgentsProvider"/> class.
    /// </summary>
    /// <param name="agents">The collection of sub-agents available for delegation.</param>
    /// <param name="options">Optional settings controlling the provider behavior.</param>
    /// <exception cref="ArgumentNullException"><paramref name="agents"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">An agent has a null or empty name, or agent names are not unique.</exception>
    public SubAgentsProvider(IEnumerable<AIAgent> agents, SubAgentsProviderOptions? options = null)
    {
        _ = Throw.IfNull(agents);

        this._agents = ValidateAndBuildAgentDictionary(agents);

        string baseInstructions = options?.Instructions ?? DefaultInstructions;
        string agentListText = options?.AgentListBuilder is not null
            ? options.AgentListBuilder(this._agents)
            : BuildDefaultAgentListText(this._agents);
        this._instructions = baseInstructions.Replace("{sub_agents}", agentListText);

        this._sessionState = new ProviderSessionState<SubAgentState>(
            _ => new SubAgentState(),
            this.GetType().Name,
            AgentJsonUtilities.DefaultOptions);

        this._runtimeSessionState = new ProviderSessionState<SubAgentRuntimeState>(
            _ => new SubAgentRuntimeState(),
            this.GetType().Name + "_Runtime",
            AgentJsonUtilities.DefaultOptions);
    }

    /// <inheritdoc />
    public override IReadOnlyList<string> StateKeys => this._stateKeys ??= [this._sessionState.StateKey, this._runtimeSessionState.StateKey];

    /// <inheritdoc />
    protected override ValueTask<AIContext> ProvideAIContextAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        SubAgentState state = this._sessionState.GetOrInitializeState(context.Session);
        SubAgentRuntimeState runtimeState = this._runtimeSessionState.GetOrInitializeState(context.Session);

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
                throw new ArgumentException("All sub-agents must have a non-empty Name.", nameof(agents));
            }

            if (dict.ContainsKey(agent.Name))
            {
                throw new ArgumentException($"Duplicate sub-agent name: '{agent.Name}'. Agent names must be unique (case-insensitive).", nameof(agents));
            }

            dict[agent.Name] = agent;
        }

        if (dict.Count == 0)
        {
            throw new ArgumentException("At least one sub-agent must be provided.", nameof(agents));
        }

        return dict;
    }

    /// <summary>
    /// Builds the default text listing available sub-agents and their descriptions.
    /// </summary>
    private static string BuildDefaultAgentListText(IReadOnlyDictionary<string, AIAgent> agents)
    {
        var sb = new StringBuilder();
        sb.AppendLine("Available sub-agents:");
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
    private void TryRefreshTaskState(SubAgentState state, SubAgentRuntimeState runtimeState, AgentSession? session)
    {
        bool changed = false;
        foreach (SubTaskInfo task in state.Tasks)
        {
            if (task.Status != SubTaskStatus.Running)
            {
                continue;
            }

            if (!runtimeState.InFlightTasks.TryGetValue(task.Id, out Task<AgentResponse>? inFlight))
            {
                // In-flight reference lost (e.g., after restart/deserialization).
                task.Status = SubTaskStatus.Lost;
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
    /// Finalizes a task by extracting results from the completed Task and updating the SubTaskInfo.
    /// </summary>
    private static void FinalizeTask(SubTaskInfo taskInfo, Task<AgentResponse> completedTask, SubAgentRuntimeState runtimeState)
    {
        if (completedTask.Status == TaskStatus.RanToCompletion)
        {
            taskInfo.Status = SubTaskStatus.Completed;
#pragma warning disable VSTHRD002 // Avoid problematic synchronous waits — task is already completed
            taskInfo.ResultText = completedTask.Result.Text;
#pragma warning restore VSTHRD002
        }
        else if (completedTask.IsFaulted)
        {
            taskInfo.Status = SubTaskStatus.Failed;
            taskInfo.ErrorText = completedTask.Exception?.InnerException?.Message ?? completedTask.Exception?.Message ?? "Unknown error";
        }
        else if (completedTask.IsCanceled)
        {
            taskInfo.Status = SubTaskStatus.Failed;
            taskInfo.ErrorText = "Task was canceled.";
        }

        runtimeState.InFlightTasks.Remove(taskInfo.Id);
    }

    private AITool[] CreateTools(SubAgentState state, SubAgentRuntimeState runtimeState, AgentSession? session)
    {
        var serializerOptions = AgentJsonUtilities.DefaultOptions;

        return
        [
            AIFunctionFactory.Create(
                async (
                    [Description("The name of the sub agent to delegate the task to.")] string agentName,
                    [Description("The request to pass to the sub agent.")] string input,
                    [Description("A description of the task used to identify the task later.")] string description) =>
                {
                    if (!this._agents.TryGetValue(agentName, out AIAgent? agent))
                    {
                        return $"Error: No sub-agent found with name '{agentName}'. Available agents: {string.Join(", ", this._agents.Keys)}";
                    }

                    int taskId = state.NextTaskId++;
                    var taskInfo = new SubTaskInfo
                    {
                        Id = taskId,
                        AgentName = agentName,
                        Description = description,
                        Status = SubTaskStatus.Running,
                    };
                    state.Tasks.Add(taskInfo);

                    // Create a dedicated session for this sub-task so it can be continued later.
                    AgentSession subSession = await agent.CreateSessionAsync().ConfigureAwait(false);

                    // Wrap in Task.Run to fork the ExecutionContext. AIAgent.RunAsync is a non-async
                    // method that synchronously sets the static AsyncLocal CurrentRunContext. Without
                    // this isolation, the sub-agent's RunAsync would overwrite the outer (calling)
                    // agent's CurrentRunContext, corrupting all subsequent tool invocations in the
                    // same FICC batch.
                    runtimeState.InFlightTasks[taskId] = Task.Run(() => agent.RunAsync(input, subSession));
                    runtimeState.SubTaskSessions[taskId] = subSession;

                    this._sessionState.SaveState(session, state);
                    return $"Sub-task {taskId} started on agent '{agentName}'.";
                },
                new AIFunctionFactoryOptions
                {
                    Name = "SubAgents_StartTask",
                    Description = "Start a sub-task on a named sub-agent. Returns a confirmation message containing the task ID.",
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
                        SubTaskInfo? alreadyComplete = state.Tasks.FirstOrDefault(t => taskIds.Contains(t.Id) && t.Status != SubTaskStatus.Running);
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
                    SubTaskInfo? taskInfo = state.Tasks.FirstOrDefault(t => t.Id == completedEntry.Id);
                    if (taskInfo is not null)
                    {
                        FinalizeTask(taskInfo, completedEntry.Task, runtimeState);
                        this._sessionState.SaveState(session, state);
                    }

                    return $"Task {completedEntry.Id} finished with status: {taskInfo?.Status.ToString() ?? "Unknown"}.";
                },
                new AIFunctionFactoryOptions
                {
                    Name = "SubAgents_WaitForFirstCompletion",
                    Description = "Block until the first of the specified sub-tasks completes. Provide one or more task IDs. Returns a status message containing the ID of the task that completed first.",
                    SerializerOptions = serializerOptions,
                }),

            AIFunctionFactory.Create(
                (int taskId) =>
                {
                    this.TryRefreshTaskState(state, runtimeState, session);

                    SubTaskInfo? taskInfo = state.Tasks.FirstOrDefault(t => t.Id == taskId);
                    if (taskInfo is null)
                    {
                        return $"Error: No task found with ID {taskId}.";
                    }

                    return taskInfo.Status switch
                    {
                        SubTaskStatus.Completed => taskInfo.ResultText ?? "(no output)",
                        SubTaskStatus.Failed => $"Task failed: {taskInfo.ErrorText ?? "Unknown error"}",
                        SubTaskStatus.Lost => "Task state was lost (reference unavailable).",
                        SubTaskStatus.Running => $"Task {taskId} is still running.",
                        _ => $"Task {taskId} has status: {taskInfo.Status}.",
                    };
                },
                new AIFunctionFactoryOptions
                {
                    Name = "SubAgents_GetTaskResults",
                    Description = "Get the text output of a sub-task by its ID. Returns the result text if complete, or status information if still running or failed.",
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
                    foreach (SubTaskInfo task in state.Tasks)
                    {
                        sb.Append("- Task ").Append(task.Id).Append(" [").Append(task.Status).Append("] (").Append(task.AgentName).Append("): ").AppendLine(task.Description);
                    }

                    return sb.ToString();
                },
                new AIFunctionFactoryOptions
                {
                    Name = "SubAgents_GetAllTasks",
                    Description = "List all sub-tasks with their IDs, statuses, agent names, and descriptions.",
                    SerializerOptions = serializerOptions,
                }),

            AIFunctionFactory.Create(
                (int taskId, string text) =>
                {
                    this.TryRefreshTaskState(state, runtimeState, session);

                    SubTaskInfo? taskInfo = state.Tasks.FirstOrDefault(t => t.Id == taskId);
                    if (taskInfo is null)
                    {
                        return $"Error: No task found with ID {taskId}.";
                    }

                    if (taskInfo.Status == SubTaskStatus.Lost)
                    {
                        return $"Error: Task {taskId} cannot be continued because its session was lost (e.g., after a session restore). Start a new task instead.";
                    }

                    if (taskInfo.Status == SubTaskStatus.Running)
                    {
                        return $"Error: Task {taskId} is still running. Wait for it to complete before continuing.";
                    }

                    if (!this._agents.TryGetValue(taskInfo.AgentName, out AIAgent? agent))
                    {
                        return $"Error: Agent '{taskInfo.AgentName}' is no longer available.";
                    }

                    if (!runtimeState.SubTaskSessions.TryGetValue(taskId, out AgentSession? subSession))
                    {
                        return $"Error: Session for task {taskId} is no longer available.";
                    }

                    // Reset task state and start a new run on the existing session.
                    taskInfo.Status = SubTaskStatus.Running;
                    taskInfo.ResultText = null;
                    taskInfo.ErrorText = null;

                    // Wrap in Task.Run to isolate the ExecutionContext (see StartSubTask comment).
                    runtimeState.InFlightTasks[taskId] = Task.Run(() => agent.RunAsync(text, subSession));

                    this._sessionState.SaveState(session, state);
                    return $"Task {taskId} continued with new input.";
                },
                new AIFunctionFactoryOptions
                {
                    Name = "SubAgents_ContinueTask",
                    Description = "Send follow-up input to a completed or failed sub-task to resume its work. The sub-task's session is preserved, so the agent retains conversational context.",
                    SerializerOptions = serializerOptions,
                }),

            AIFunctionFactory.Create(
                (int taskId) =>
                {
                    this.TryRefreshTaskState(state, runtimeState, session);

                    SubTaskInfo? taskInfo = state.Tasks.FirstOrDefault(t => t.Id == taskId);
                    if (taskInfo is null)
                    {
                        return $"Error: No task found with ID {taskId}.";
                    }

                    if (taskInfo.Status == SubTaskStatus.Running)
                    {
                        return $"Error: Task {taskId} is still running. Wait for it to complete before clearing.";
                    }

                    // Remove the task from state.
                    state.Tasks.Remove(taskInfo);

                    // Clean up runtime references.
                    runtimeState.InFlightTasks.Remove(taskId);
                    runtimeState.SubTaskSessions.Remove(taskId);

                    this._sessionState.SaveState(session, state);
                    return $"Task {taskId} cleared.";
                },
                new AIFunctionFactoryOptions
                {
                    Name = "SubAgents_ClearCompletedTask",
                    Description = "Remove a completed or failed sub-task and release its session to free memory. Use this after retrieving results when you no longer need to continue the task.",
                    SerializerOptions = serializerOptions,
                }),
        ];
    }
}
