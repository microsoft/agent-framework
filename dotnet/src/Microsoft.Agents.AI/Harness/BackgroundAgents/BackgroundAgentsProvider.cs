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
/// <item><description><c>background_agents_start_task</c> — Start a background task on a named agent with text input. Returns the task ID.</description></item>
/// <item><description><c>background_agents_wait_for_first_completion</c> — Wait until the first specified task completes or the configured timeout expires. A timeout leaves the tasks running so the tool can be called again.</description></item>
/// <item><description><c>background_agents_get_task_results</c> — Retrieve the text output of a completed background task.</description></item>
/// <item><description><c>background_agents_get_all_tasks</c> — List all background tasks with their IDs, statuses, descriptions, and agent names.</description></item>
/// <item><description><c>background_agents_continue_task</c> — Send follow-up input to a completed background task's session to resume work.</description></item>
/// <item><description><c>background_agents_clear_completed_task</c> — Remove a completed background task and release its session to free memory.</description></item>
/// </list>
/// </para>
/// <para>
/// Background tasks are tracked per session and keep running until they complete. When a host is finished with a
/// session it should call <see cref="ReleaseSessionAsync"/> to cancel and await any in-flight tasks, so that
/// abandoned work does not continue to invoke models and tools in the background.
/// </para>
/// <para>
/// <strong>Security considerations:</strong> The agents passed to the constructor are delegated
/// arbitrary work by the parent agent — the parent sends them text input (which may include content
/// derived from the parent's own untrusted context) and receives back whatever text they produce. A
/// compromised or malicious supplied agent (for example, one with a compromised system prompt, tools,
/// or upstream model) could exfiltrate that input to an external system, or return adversarial output
/// designed to influence the parent agent via indirect prompt injection once its result is retrieved.
/// Only supply agents you have vetted and trust with the data the parent may pass to them.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class BackgroundAgentsProvider : AIContextProvider
{
    private const string DefaultInstructions =
        """
        ## BackgroundAgents
        You have access to background agents that can perform work on your behalf.

        - Use the `background_agents_*` list of tools to start tasks on background agents and check their results.
        - Creating a background task does not block, and background tasks run concurrently.
        - Important: Always wait for outstanding tasks to finish before you finish processing.
        - Important: After retrieving results from a completed task, clear it with background_agents_clear_completed_task to free memory, unless you plan to continue it with background_agents_continue_task.

        {background_agents}
        """;

    private const string ReleasedRuntimeStartError =
        "Error: The background agents runtime for this session has been released. No new background tasks can be started.";

    private const string ReleasedRuntimeContinueError =
        "Error: The background agents runtime for this session has been released. Background tasks can no longer be continued.";

    private const string ReleasedTaskCanceledMessage = "Task was canceled because the session was released.";

    private readonly Dictionary<string, AIAgent> _agents;
    private static readonly TimeSpan s_defaultReleaseTimeout = TimeSpan.FromSeconds(30);
    private readonly ProviderSessionState<BackgroundAgentState> _sessionState;
    private readonly ProviderSessionState<BackgroundAgentRuntimeState> _runtimeSessionState;
    private readonly string _instructions;
    private readonly TimeSpan _waitTimeout;
    private IReadOnlyList<string>? _stateKeys;

    /// <summary>
    /// Initializes a new instance of the <see cref="BackgroundAgentsProvider"/> class.
    /// </summary>
    /// <param name="agents">
    /// The collection of background agents available for delegation. <strong>Security:</strong> Each
    /// supplied agent should be vetted and trusted, since it will receive text input from the parent
    /// agent and its output is fed back into the parent's context — see the type-level security
    /// considerations for details on the exfiltration and prompt-injection risks of untrusted agents.
    /// </param>
    /// <param name="options">Optional settings controlling the provider behavior.</param>
    /// <exception cref="ArgumentNullException"><paramref name="agents"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">An agent has a null or empty name, or agent names are not unique.</exception>
    /// <exception cref="ArgumentOutOfRangeException">
    /// <see cref="BackgroundAgentsProviderOptions.WaitTimeout"/> is not positive or exceeds the maximum supported delay.
    /// </exception>
    public BackgroundAgentsProvider(IEnumerable<AIAgent> agents, BackgroundAgentsProviderOptions? options = null)
    {
        _ = Throw.IfNull(agents);

        this._agents = ValidateAndBuildAgentDictionary(agents);
        this._waitTimeout = options?.WaitTimeout ?? BackgroundAgentsProviderOptions.DefaultWaitTimeout;
        if (this._waitTimeout <= TimeSpan.Zero)
        {
            throw new ArgumentOutOfRangeException(
                nameof(options),
                this._waitTimeout,
                $"{nameof(BackgroundAgentsProviderOptions.WaitTimeout)} must be positive.");
        }

        if (this._waitTimeout > BackgroundAgentsProviderOptions.MaximumWaitTimeout)
        {
            throw new ArgumentOutOfRangeException(
                nameof(options),
                this._waitTimeout,
                $"{nameof(BackgroundAgentsProviderOptions.WaitTimeout)} must not exceed {BackgroundAgentsProviderOptions.MaximumWaitTimeout.TotalMilliseconds} milliseconds.");
        }

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
#pragma warning disable MAAI001
        FeatureUsage.MarkUsed((int)FeatureIndex.CoreBackgroundAgentsProvider);
#pragma warning restore MAAI001

        BackgroundAgentState state = this._sessionState.GetOrInitializeState(context.Session);
        BackgroundAgentRuntimeState runtimeState = this._runtimeSessionState.GetOrInitializeState(context.Session);

        return new ValueTask<AIContext>(new AIContext
        {
            Instructions = this._instructions,
            Tools = this.CreateTools(state, runtimeState, context.Session),
        });
    }

    /// <summary>
    /// Gets the background tasks for the specified session that have not yet completed (i.e., are still running).
    /// </summary>
    /// <remarks>
    /// The status of in-flight tasks is refreshed before the result is computed, so tasks that have finished since the
    /// last interaction are finalized and excluded. Only tasks whose <see cref="BackgroundTaskInfo.Status"/> is
    /// <see cref="BackgroundTaskStatus.Running"/> are returned; <see cref="BackgroundTaskStatus.Completed"/>,
    /// <see cref="BackgroundTaskStatus.Failed"/>, and <see cref="BackgroundTaskStatus.Lost"/> are all terminal and are
    /// not included. The returned <see cref="BackgroundTaskInfo"/> instances are live references to internal state.
    /// </remarks>
    /// <param name="session">The agent session whose background tasks should be inspected.</param>
    /// <returns>A read-only list of the background tasks that are still running.</returns>
    public IReadOnlyList<BackgroundTaskInfo> GetIncompleteTasks(AgentSession? session)
    {
        BackgroundAgentState state = this._sessionState.GetOrInitializeState(session);
        BackgroundAgentRuntimeState runtimeState = this._runtimeSessionState.GetOrInitializeState(session);

        this.TryRefreshTaskState(state, runtimeState, session);

        var incomplete = new List<BackgroundTaskInfo>();
        foreach (BackgroundTaskInfo task in state.Tasks)
        {
            if (task.Status == BackgroundTaskStatus.Running)
            {
                incomplete.Add(task);
            }
        }

        return incomplete;
    }

    /// <summary>
    /// Releases all runtime state held for the specified session, cancelling and awaiting any in-flight background tasks.
    /// </summary>
    /// <param name="session">The agent session whose background runtime should be released.</param>
    /// <param name="cancelRunning">
    /// <see langword="true"/> to cancel any background tasks that are still running; <see langword="false"/> to require that
    /// all background tasks have already completed.
    /// </param>
    /// <param name="timeout">
    /// The maximum amount of time to wait for cancelled tasks to finish. Defaults to 30 seconds when <see langword="null"/>.
    /// Use <see cref="Timeout.InfiniteTimeSpan"/> to wait indefinitely. If the timeout elapses, the remaining tasks are
    /// abandoned rather than blocking the caller.
    /// </param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests while waiting.</param>
    /// <returns>A task that represents the asynchronous release operation.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="session"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentOutOfRangeException"><paramref name="timeout"/> is negative and is not <see cref="Timeout.InfiniteTimeSpan"/>.</exception>
    /// <exception cref="InvalidOperationException"><paramref name="cancelRunning"/> is <see langword="false"/> and one or more background tasks are still running.</exception>
    /// <remarks>
    /// <para>
    /// Background tasks continue to execute — invoking models and tools — even after a host stops using the session
    /// that started them. Hosts should call this method when a conversation ends, or from their own eviction policy,
    /// so that abandoned work is stopped instead of running to completion with results nobody will read.
    /// </para>
    /// <para>
    /// This method is idempotent: releasing an already-released session does nothing. Once released, the
    /// <c>background_agents_start_task</c> and <c>background_agents_continue_task</c> tools refuse to run for that
    /// session, and any tasks that were still running are recorded as
    /// <see cref="BackgroundTaskStatus.Failed"/> so a restored session does not report phantom running work.
    /// </para>
    /// <para>
    /// It is also safe to call concurrently. A caller that arrives while another release of the same session is
    /// still in progress waits for that release to finish rather than returning early, so a completed call always
    /// means the background tasks have been cancelled, awaited and cleaned up. Such a caller observes only its own
    /// <paramref name="cancellationToken"/>; it neither inherits the in-progress release's failure nor is held up
    /// by that caller's <paramref name="timeout"/>.
    /// </para>
    /// </remarks>
    public async Task ReleaseSessionAsync(
        AgentSession session,
        bool cancelRunning = true,
        TimeSpan? timeout = null,
        CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(session);

        TimeSpan effectiveTimeout = timeout ?? s_defaultReleaseTimeout;
        if (effectiveTimeout < TimeSpan.Zero && effectiveTimeout != Timeout.InfiniteTimeSpan)
        {
            throw new ArgumentOutOfRangeException(
                nameof(timeout),
                effectiveTimeout,
                "The timeout must not be negative, unless it is Timeout.InfiniteTimeSpan.");
        }

        BackgroundAgentRuntimeState runtimeState = this._runtimeSessionState.GetOrInitializeState(session);
        BackgroundAgentState state = this._sessionState.GetOrInitializeState(session);

        KeyValuePair<int, Task<AgentResponse>>[] trackedTasks = [];
        HashSet<int> pendingTaskIds = [];
        TaskCompletionSource<bool>? releaseCompletion = null;
        Task? releaseInProgress = null;

        lock (runtimeState.SyncRoot)
        {
            if (runtimeState.IsReleased)
            {
                // A release is already in progress or has completed. Await it rather than returning early, so that
                // a completed call always means the in-flight tasks have been cancelled, awaited and cleaned up.
                releaseInProgress = runtimeState.ReleaseCompletion?.Task;
            }
            else
            {
                trackedTasks = runtimeState.InFlightTasks.ToArray();

                // Snapshot which tasks were still pending before anything is cancelled. Tasks that had already
                // finished keep their real outcome; only these pending ones are reported as released.
                pendingTaskIds = [.. trackedTasks.Where(t => !t.Value.IsCompleted).Select(t => t.Key)];

                if (!cancelRunning && pendingTaskIds.Count > 0)
                {
                    throw new InvalidOperationException(
                        $"Cannot release the session because {pendingTaskIds.Count} background task(s) are still running. Pass cancelRunning: true to cancel them.");
                }

                // Cancel before publishing the release. If cancelling throws, the runtime is left un-released so
                // that the caller can retry, rather than being flagged as released with tasks still running.
                foreach (int taskId in pendingTaskIds)
                {
                    if (runtimeState.TaskCancellations.TryGetValue(taskId, out CancellationTokenSource? cts))
                    {
                        try
                        {
                            cts.Cancel();
                        }
                        catch (ObjectDisposedException)
                        {
                            // The source was already disposed by a concurrent finalization; nothing to cancel.
                        }
                    }
                }

                // Continuations run asynchronously so that a waiting caller never resumes inline on the thread
                // that is completing the release.
                releaseCompletion = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
                runtimeState.ReleaseCompletion = releaseCompletion;
                runtimeState.IsReleased = true;
            }
        }

        if (releaseCompletion is null)
        {
            if (releaseInProgress is not null)
            {
                await AwaitReleaseInProgressAsync(releaseInProgress, cancellationToken).ConfigureAwait(false);
            }

            return;
        }

        try
        {
            await WaitForTasksAsync(trackedTasks.Select(t => t.Value), effectiveTimeout, cancellationToken).ConfigureAwait(false);
        }
        finally
        {
            lock (runtimeState.SyncRoot)
            {
                // Finalize every tracked task that actually finished, so successful results and real failure
                // reasons are preserved rather than being overwritten with a release failure.
                foreach (var kvp in trackedTasks)
                {
                    BackgroundTaskInfo? tracked = state.Tasks.FirstOrDefault(t => t.Id == kvp.Key);
                    if (tracked is null || tracked.Status != BackgroundTaskStatus.Running || !kvp.Value.IsCompleted)
                    {
                        continue;
                    }

                    FinalizeTask(tracked, kvp.Value, runtimeState);

                    if (kvp.Value.IsCanceled && pendingTaskIds.Contains(kvp.Key))
                    {
                        // Report the actual reason rather than the generic cancellation message.
                        tracked.ErrorText = ReleasedTaskCanceledMessage;
                    }
                }

                foreach (int taskId in runtimeState.TaskCancellations.Keys.ToArray())
                {
                    DisposeTaskCancellation(runtimeState, taskId);
                }

                runtimeState.InFlightTasks.Clear();
                runtimeState.BackgroundTaskSessions.Clear();

                // Anything still running was abandoned (for example after the timeout elapsed).
                foreach (BackgroundTaskInfo task in state.Tasks)
                {
                    if (task.Status == BackgroundTaskStatus.Running)
                    {
                        task.Status = BackgroundTaskStatus.Failed;
                        task.ErrorText = ReleasedTaskCanceledMessage;
                    }
                }
            }

            this._sessionState.SaveState(session, state);
            this._runtimeSessionState.SaveState(session, runtimeState);

            // Signalled last so that any caller awaiting this release observes fully cleaned-up state. Completed
            // successfully even when this caller failed, because the cleanup above always runs.
            releaseCompletion.TrySetResult(true);
        }
    }

    /// <summary>
    /// Waits for a release that another caller started to finish its cleanup, giving up if the caller's own
    /// <paramref name="cancellationToken"/> is signalled.
    /// </summary>
    private static async Task AwaitReleaseInProgressAsync(Task releaseInProgress, CancellationToken cancellationToken)
    {
        if (releaseInProgress.IsCompleted || !cancellationToken.CanBeCanceled)
        {
            // The release completion is never faulted or cancelled, so awaiting it cannot throw.
            await releaseInProgress.ConfigureAwait(false);
            return;
        }

        // Do not let this caller be held up by the releasing caller's timeout.
        var cancellation = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        using (cancellationToken.Register(static state => ((TaskCompletionSource<bool>)state!).TrySetResult(true), cancellation))
        {
            await Task.WhenAny(releaseInProgress, cancellation.Task).ConfigureAwait(false);
        }

        if (!releaseInProgress.IsCompleted)
        {
            cancellationToken.ThrowIfCancellationRequested();
        }
    }

    /// <summary>
    /// Waits for the specified tasks to finish, observing their exceptions and giving up once the timeout elapses.
    /// </summary>
    private static async Task WaitForTasksAsync(IEnumerable<Task> tasks, TimeSpan timeout, CancellationToken cancellationToken)
    {
        // Attach an observer to every task, including those that already completed, so that a fault is always
        // observed. Otherwise clearing the last reference to a faulted task can surface an UnobservedTaskException.
        Task[] observers = tasks.Select(t => t.ContinueWith(
            static antecedent => _ = antecedent.Exception,
            CancellationToken.None,
            TaskContinuationOptions.ExecuteSynchronously,
            TaskScheduler.Default)).ToArray();

        // Observers never fault, so awaiting them cannot throw.
        Task[] pending = observers.Where(o => !o.IsCompleted).ToArray();
        if (pending.Length == 0)
        {
            return;
        }

        Task all = Task.WhenAll(pending);

        if (timeout == Timeout.InfiniteTimeSpan && !cancellationToken.CanBeCanceled)
        {
            await all.ConfigureAwait(false);
            return;
        }

        using var delayCts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        Task delay = Task.Delay(timeout, delayCts.Token);

        Task winner = await Task.WhenAny(all, delay).ConfigureAwait(false);
        delayCts.Cancel();

        if (winner != all)
        {
            // The wait was abandoned; the remaining tasks are left to finish on their own.
            cancellationToken.ThrowIfCancellationRequested();
        }
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
        lock (runtimeState.SyncRoot)
        {
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
        }

        if (changed)
        {
            this._sessionState.SaveState(session, state);
        }
    }

    /// <summary>
    /// Finalizes a task by extracting results from the completed Task and updating the BackgroundTaskInfo.
    /// </summary>
    /// <remarks>Callers must hold <see cref="BackgroundAgentRuntimeState.SyncRoot"/>.</remarks>
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
        DisposeTaskCancellation(runtimeState, taskInfo.Id);
    }

    /// <summary>
    /// Removes and disposes the <see cref="CancellationTokenSource"/> tracked for the specified task, if any.
    /// </summary>
    /// <remarks>Callers must hold <see cref="BackgroundAgentRuntimeState.SyncRoot"/>.</remarks>
    private static void DisposeTaskCancellation(BackgroundAgentRuntimeState runtimeState, int taskId)
    {
        if (runtimeState.TaskCancellations.TryGetValue(taskId, out CancellationTokenSource? cts))
        {
            runtimeState.TaskCancellations.Remove(taskId);
            cts.Dispose();
        }
    }

    /// <summary>
    /// Starts a background run for the specified task, tracking the resulting task, the background agent session,
    /// and a <see cref="CancellationTokenSource"/> that allows the run to be cancelled when the session is released.
    /// </summary>
    /// <returns>
    /// <see langword="true"/> if the run was started and tracked; <see langword="false"/> if the session was
    /// released before the run could be registered, in which case nothing is started.
    /// </returns>
    /// <remarks>
    /// All references for the task are registered under a single acquisition of
    /// <see cref="BackgroundAgentRuntimeState.SyncRoot"/>, so a concurrent release can never observe a partially
    /// registered task, nor can a caller re-add references to a runtime that has already been released.
    /// </remarks>
    private static bool StartTrackedRun(BackgroundAgentRuntimeState runtimeState, int taskId, AIAgent agent, string input, AgentSession subSession)
    {
        lock (runtimeState.SyncRoot)
        {
            // Re-check under the lock: the session may have been released while the caller awaited session creation.
            // Starting here would produce a task that is never tracked and therefore never cancelled.
            if (runtimeState.IsReleased)
            {
                return false;
            }

            // Replace any cancellation source left over from a previous run of the same task.
            DisposeTaskCancellation(runtimeState, taskId);

            var cts = new CancellationTokenSource();
            runtimeState.TaskCancellations[taskId] = cts;

            // Registered here rather than by the caller so that the session reference cannot be re-added to a
            // runtime that a concurrent release has already cleared. For a continued task this simply re-assigns
            // the session the caller read from this same dictionary.
            runtimeState.BackgroundTaskSessions[taskId] = subSession;

            // Wrap in Task.Run to fork the ExecutionContext. AIAgent.RunAsync is a non-async
            // method that synchronously sets the static AsyncLocal CurrentRunContext. Without
            // this isolation, the background agent's RunAsync would overwrite the outer (calling)
            // agent's CurrentRunContext, corrupting all subsequent tool invocations in the
            // same FICC batch.
            runtimeState.InFlightTasks[taskId] = Task.Run(() => agent.RunAsync(input, subSession, cancellationToken: cts.Token), cts.Token);
            return true;
        }
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
                    if (runtimeState.IsReleased)
                    {
                        return ReleasedRuntimeStartError;
                    }

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

                    if (!StartTrackedRun(runtimeState, taskId, agent, input, subSession))
                    {
                        // The session was released while the background session was being created.
                        state.Tasks.Remove(taskInfo);
                        this._sessionState.SaveState(session, state);
                        return ReleasedRuntimeStartError;
                    }

                    this._sessionState.SaveState(session, state);
                    return $"Background task {taskId} started on agent '{agentName}'.";
                },
                new AIFunctionFactoryOptions
                {
                    Name = "background_agents_start_task",
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
                    lock (runtimeState.SyncRoot)
                    {
                        foreach (int id in taskIds)
                        {
                            if (runtimeState.InFlightTasks.TryGetValue(id, out Task<AgentResponse>? inFlight))
                            {
                                waitableTasks.Add((id, inFlight));
                            }
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

                    // Wait for the first task to complete, but return control without stopping the tasks if the timeout elapses.
                    Task<Task<AgentResponse>> firstCompletionTask = Task.WhenAny(waitableTasks.Select(t => t.Task));
                    using var timeoutCts = new CancellationTokenSource();
                    Task timeoutTask = Task.Delay(this._waitTimeout, timeoutCts.Token);
                    Task winner = await Task.WhenAny(firstCompletionTask, timeoutTask).ConfigureAwait(false);
                    timeoutCts.Cancel();

                    if (winner == timeoutTask && !firstCompletionTask.IsCompleted)
                    {
                        return FormattableString.Invariant(
                            $"No background task completed within {this._waitTimeout.TotalSeconds:g} seconds. The tasks are still running; call this tool again if you wish to continue waiting.");
                    }

                    Task<AgentResponse> completedTask = await firstCompletionTask.ConfigureAwait(false);

                    // Find which ID completed.
                    var completedEntry = waitableTasks.First(t => t.Task == completedTask);

                    // Finalize the completed task.
                    BackgroundTaskInfo? taskInfo = state.Tasks.FirstOrDefault(t => t.Id == completedEntry.Id);
                    if (taskInfo is not null)
                    {
                        lock (runtimeState.SyncRoot)
                        {
                            if (taskInfo.Status == BackgroundTaskStatus.Running)
                            {
                                FinalizeTask(taskInfo, completedEntry.Task, runtimeState);
                            }
                        }

                        this._sessionState.SaveState(session, state);
                    }

                    return $"Task {completedEntry.Id} finished with status: {taskInfo?.Status.ToString() ?? "Unknown"}.";
                },
                new AIFunctionFactoryOptions
                {
                    Name = "background_agents_wait_for_first_completion",
                    Description = "Wait until the first of the specified background tasks completes or the configured timeout expires. Provide one or more task IDs. Returns a status message containing the ID of the task that completed first. On timeout, the tasks remain running and this tool can be called again to continue waiting.",
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
                    Name = "background_agents_get_task_results",
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
                    Name = "background_agents_get_all_tasks",
                    Description = "List all background tasks with their IDs, statuses, agent names, and descriptions.",
                    SerializerOptions = serializerOptions,
                }),

            AIFunctionFactory.Create(
                (int taskId, string text) =>
                {
                    if (runtimeState.IsReleased)
                    {
                        return ReleasedRuntimeContinueError;
                    }

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

                    AgentSession? subSession;
                    lock (runtimeState.SyncRoot)
                    {
                        _ = runtimeState.BackgroundTaskSessions.TryGetValue(taskId, out subSession);
                    }

                    if (subSession is null)
                    {
                        return $"Error: Session for task {taskId} is no longer available.";
                    }

                    // Reset task state and start a new run on the existing session.
                    taskInfo.Status = BackgroundTaskStatus.Running;
                    taskInfo.ResultText = null;
                    taskInfo.ErrorText = null;

                    // Wrap in Task.Run to isolate the ExecutionContext (see StartBackgroundTask comment).
                    if (!StartTrackedRun(runtimeState, taskId, agent, text, subSession))
                    {
                        taskInfo.Status = BackgroundTaskStatus.Failed;
                        taskInfo.ErrorText = ReleasedTaskCanceledMessage;
                        this._sessionState.SaveState(session, state);
                        return ReleasedRuntimeContinueError;
                    }

                    this._sessionState.SaveState(session, state);
                    return $"Task {taskId} continued with new input.";
                },
                new AIFunctionFactoryOptions
                {
                    Name = "background_agents_continue_task",
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
                    lock (runtimeState.SyncRoot)
                    {
                        runtimeState.InFlightTasks.Remove(taskId);
                        runtimeState.BackgroundTaskSessions.Remove(taskId);
                        DisposeTaskCancellation(runtimeState, taskId);
                    }

                    this._sessionState.SaveState(session, state);
                    return $"Task {taskId} cleared.";
                },
                new AIFunctionFactoryOptions
                {
                    Name = "background_agents_clear_completed_task",
                    Description = "Remove a completed or failed background task and release its session to free memory. Use this after retrieving results when you no longer need to continue the task.",
                    SerializerOptions = serializerOptions,
                }),
        ];
    }
}
