// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Specialized.Magentic;

/// <summary>
/// Base type for Magentic Orchestration Events
/// </summary>
/// <param name="data"></param>
[JsonDerivedType(typeof(MagenticPlanCreatedEvent))]
[JsonDerivedType(typeof(MagenticReplannedEvent))]
[JsonDerivedType(typeof(MagenticProgressLedgerUpdatedEvent))]
public abstract class MagenticOrchestratorEvent(object? data) : WorkflowEvent(data)
{
}

/// <summary>
/// Represents the creation of the initial plan
/// </summary>
/// <param name="fullTaskLeger"></param>
public sealed class MagenticPlanCreatedEvent(ChatMessage fullTaskLeger) : MagenticOrchestratorEvent(fullTaskLeger)
{
    /// <summary>
    /// A <see cref="ChatMessage"/> containing the initial plan.
    /// </summary>
    public ChatMessage FullTaskLedger { get; } = fullTaskLeger;
}

/// <summary>
/// Represents the creation of a new plan in response to a stall.
/// </summary>
/// <param name="fullTaskLeger"></param>
public sealed class MagenticReplannedEvent(ChatMessage fullTaskLeger) : MagenticOrchestratorEvent(fullTaskLeger)
{
    /// <summary>
    /// A <see cref="ChatMessage"/> containing the new plan.
    /// </summary>
    public ChatMessage FullTaskLedger { get; } = fullTaskLeger;
}

/// <summary>
/// Represents an update to the <see cref="MagenticProgressLedger"/> when running a coordination round.
/// </summary>
/// <param name="progressLedger"></param>
public sealed class MagenticProgressLedgerUpdatedEvent(MagenticProgressLedger progressLedger) : MagenticOrchestratorEvent(progressLedger)
{
    /// <summary>
    /// The new state of the <see cref="MagenticProgressLedger"/>
    /// </summary>
    public MagenticProgressLedger ProgressLedger { get; } = progressLedger;
}

/// <summary>
/// Magentic orchestrator that defines the workflow structure.
///
/// This orchestrator manages the overall Magentic workflow in the following structure:
///
///    1. Upon receiving the task(a list of messages), it creates the plan using the manager then runs the inner loop.
///    2. The inner loop is distributed and implementation is decentralized. In the orchestrator, it is responsible for:
///        - Creating the progress ledger using the manager.
///        - Checking for task completion.
///        - Detecting stalling or looping and triggering replanning if needed.
///        - Sending requests to participants based on the progress ledger's next speaker.
///        - Issue requests for human intervention if enabled and needed.
///    3. The inner loop waits for responses from the selected participant, then continues the loop.
///    4. The orchestrator breaks out of the inner loop when the replanning or final answer conditions are met.
///    5. The outer loop handles replanning and reenters the inner loop.
/// </summary>
/// <param name="managerAgent"></param>
/// <param name="team"></param>
/// <param name="limits"></param>
/// <param name="requirePlanSignoff"></param>
internal class MagenticOrchestrator(AIAgent managerAgent, List<AIAgent> team, TaskLimits limits, bool requirePlanSignoff)
    : ChatProtocolExecutor(nameof(MagenticOrchestrator), s_options, declareCrossRunShareable: false)
{
    private readonly MagenticManager _manager = new(managerAgent);

    private static readonly ChatProtocolExecutorOptions s_options = new()
    {
        StringMessageChatRole = ChatRole.User,
        AutoSendTurnToken = false
    };

    private MagenticTaskContext? _taskContext;
    private PortBinding? _planReviewPort;
    private string? _currentSpeakerExecutorId;

    protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
    {
        return base.ConfigureProtocol(protocolBuilder)
                   .SendsMessage<ChatMessage>()
                   .SendsMessage<ResetChatSignal>()
                   .YieldsOutput<List<ChatMessage>>()
                   .ConfigureRoutes(ConfigureRoutes);

        void ConfigureRoutes(RouteBuilder routeBuilder) => routeBuilder.AddPortHandler<MagenticPlanReviewRequest, MagenticPlanReviewResponse>(
                "RequestPlanReview",
                this.ProcessPlanReviewAsync,
                out this._planReviewPort);
    }

    private ValueTask SubmitPlanReviewRequestAsync(MagenticTaskContext taskContext, IWorkflowContext workflowContext, bool replanAfterStall = false)
    {
        MagenticProgressLedger? progressLedger = taskContext.ProgressLedger;
        if (progressLedger?.IsStarted is not true)
        {
            progressLedger = null;
        }

        MagenticPlanReviewRequest request = new(taskContext.TaskLedger!.CurrentPlan, progressLedger, replanAfterStall);

        return this._planReviewPort!.PostRequestAsync(request);
    }

    private async ValueTask ProcessPlanReviewAsync(MagenticPlanReviewResponse response, IWorkflowContext context, CancellationToken cancellationToken)
    {
        /*
        Handle the human response to the plan review request.

        Logic:
        There are code paths which will trigger a plan review request to the human:
        - Initial plan creation if `require_plan_signoff` is True.
        - Potentially during the inner loop if stalling is detected (resetting and replanning).

        The human can either approve the plan or request revisions with comments.
        - If approved, proceed to run the outer loop, which simply adds the task ledger
          to the conversation and enters the inner loop.
        - If revision requested, append the review comments to the chat history,
          trigger replanning via the manager, emit a REPLANNED event, then run the outer loop.
         */
        if (this._taskContext == null || this._taskContext.TaskLedger == null)
        {
            throw new InvalidOperationException("Magentic Orchestration was not initialized correctly.");
        }

        if (this._taskContext.IsTerminated)
        {
            throw new InvalidOperationException("This Magentic orchestration has already terminated. To process new messages, create a new workflow instance.");
        }

        if (response.IsApproved)
        {
            await this.DelegateToTeamAsync(this._taskContext, context, cancellationToken).ConfigureAwait(false);
        }
        else
        {
            this._taskContext.ChatHistory.AddRange(response.Review);

            await this.UpdatePlanAndDelegateAsync(this._taskContext, context, cancellationToken).ConfigureAwait(false);
        }
    }

    private async ValueTask UpdatePlanAndDelegateAsync(MagenticTaskContext taskContext, IWorkflowContext context, CancellationToken cancellationToken, bool replanAfterStall = false)
    {
        bool isReplan = taskContext.TaskLedger != null;

        taskContext.TaskLedger = await this._manager.UpdatePlanAsync(taskContext, context, cancellationToken)
                                                    .ConfigureAwait(false);

        this._fullTaskLedgerMessage = new(ChatRole.User, taskContext.ToTaskLedgerFullPrompt());
        taskContext.ChatHistory.Add(this._fullTaskLedgerMessage);

        await context.AddEventAsync(isReplan
                                    ? new MagenticReplannedEvent(this._fullTaskLedgerMessage)
                                    : new MagenticPlanCreatedEvent(this._fullTaskLedgerMessage), cancellationToken).ConfigureAwait(false);

        if (requirePlanSignoff)
        {
            await this.SubmitPlanReviewRequestAsync(taskContext, context, replanAfterStall).ConfigureAwait(false);
        }
        else
        {
            await this.DelegateToTeamAsync(taskContext, context, cancellationToken).ConfigureAwait(false);
        }
    }

    protected override async ValueTask TakeTurnAsync(List<ChatMessage> messages, IWorkflowContext context, bool? emitEvents, CancellationToken cancellationToken = default)
    {
        if (this._taskContext?.IsTerminated == true)
        {
            throw new InvalidOperationException("This Magentic orchestration has already terminated. To process new messages, create a new workflow instance.");
        }

        if (this._taskContext == null)
        {
            // First Turn: Initialize the task context and create the initial plan
            this._taskContext = new(messages, team, limits, emitEvents, []);
            await this.UpdatePlanAndDelegateAsync(this._taskContext, context, cancellationToken).ConfigureAwait(false);
        }
        else
        {
            // Subsequent turns: agent returned control, go directly to coordination (progress ledger only, no replan).
            if (messages is { Count: > 0 })
            {
                // Capture the participant's reply into the manager-visible chat history so the progress ledger can see it.
                this._taskContext.ChatHistory.AddRange(messages);

                // Share the reply with the other participants except the replier
                await this.BroadcastReplyToOtherParticipantsAsync(messages, context, cancellationToken).ConfigureAwait(false);
            }
            await this.RunCoordinationRoundAsync(this._taskContext, context, cancellationToken).ConfigureAwait(false);
        }
    }

    /// <summary>
    /// Forwards a participant's reply to every other participant so they share the running conversation.
    /// The messages are buffered (no <see cref="TurnToken"/> is sent) - they only become context for the participant's next turn.
    /// </summary>
    private ValueTask BroadcastReplyToOtherParticipantsAsync(
        List<ChatMessage> messages, IWorkflowContext context, CancellationToken cancellationToken)
    {
        // Without a known current speaker we cannot exclude the reply's author, so skip the broadcast
        // rather than risk echoing the reply back to its own author. This covers the window after a
        // checkpoint restore but before any delegation has set the current speaker.
        if (string.IsNullOrEmpty(this._currentSpeakerExecutorId))
        {
            return default;
        }

        List<Task>? sendTasks = null;
        foreach (AIAgent agent in team)
        {
            string executorId = AIAgentHostExecutor.IdFor(agent);
            if (string.Equals(executorId, this._currentSpeakerExecutorId, StringComparison.Ordinal))
            {
                continue;
            }
            (sendTasks ??= []).Add(context.SendMessageAsync(messages, executorId, cancellationToken).AsTask());
        }
        return sendTasks is null ? default : new ValueTask(Task.WhenAll(sendTasks));
    }

    private ChatMessage? _fullTaskLedgerMessage;
    private ValueTask DelegateToTeamAsync(MagenticTaskContext taskContext, IWorkflowContext context, CancellationToken cancellationToken)
    {
        return this.RunCoordinationRoundAsync(taskContext, context, cancellationToken);
    }

    private async ValueTask RunCoordinationRoundAsync(MagenticTaskContext taskContext, IWorkflowContext context, CancellationToken cancellationToken)
    {
        (bool hitRoundLimit, bool hitResetLimit) = taskContext.CheckLimits();

        if (hitRoundLimit || hitResetLimit)
        {
            string limitType = hitRoundLimit ? "round" : "reset";

            List<ChatMessage> messages = [new(ChatRole.Assistant, $"Task execution stopped due to hitting the maximum {limitType} count limit.")];
            await context.YieldOutputAsync(messages, cancellationToken).ConfigureAwait(false);
            taskContext.IsTerminated = true;

            return;
        }

        taskContext.TaskCounters.RoundCount++;

        // Update the Progress Ledger
        try
        {
            await this._manager.UpdateProgressLedgerAsync(taskContext, context, cancellationToken).ConfigureAwait(false);

            await context.AddEventAsync(new MagenticProgressLedgerUpdatedEvent(taskContext.ProgressLedger), cancellationToken)
                         .ConfigureAwait(false);
        }
        // Retry on exception to max retry count, unless it is OperationCancelledException - in that case exit the loop right away
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            await context.AddEventAsync(new WorkflowWarningEvent($"Magentic Orchestrator: Progress ledger creation failed, triggering reset: {ex}"), cancellationToken)
                         .ConfigureAwait(false);

            await this.ResetAndReplanAsync(taskContext, context, cancellationToken).ConfigureAwait(false);
            return;
        }

        // Check and handle finish condition
        if (taskContext.ProgressLedger.IsRequestSatisfied)
        {
            await this.PrepareFinalAnswerAsync(taskContext, context, cancellationToken).ConfigureAwait(false);
            return;
        }

        // Check and handle stalls
        if (taskContext.ProgressLedger.IsInLoop || !taskContext.ProgressLedger.IsProgressBeingMade)
        {
            taskContext.TaskCounters.StallCount++;
        }
        else
        {
            taskContext.TaskCounters.StallCount = Math.Max(0, taskContext.TaskCounters.StallCount - 1);
        }

        if (taskContext.IsStalled)
        {
            await this.ResetAndReplanAsync(taskContext, context, cancellationToken).ConfigureAwait(false);
            return;
        }

        // Prepare to delegate to the next speaker
        string nextSpeaker = taskContext.ProgressLedger.NextSpeaker;
        if (string.IsNullOrEmpty(nextSpeaker))
        {
            await context.AddEventAsync(new WorkflowWarningEvent("Next speaker answer empty; selecting first participant as fallback"), cancellationToken)
                         .ConfigureAwait(false);
            nextSpeaker = team.First().Name!;
        }

        AIAgent? nextAgent = team.FirstOrDefault(agent => agent.Name == nextSpeaker);
        if (nextAgent == null)
        {
            await context.AddEventAsync(new WorkflowWarningEvent($"Invalid next speaker: {nextSpeaker}"), cancellationToken)
                         .ConfigureAwait(false);
            await this.PrepareFinalAnswerAsync(taskContext, context, cancellationToken).ConfigureAwait(false);
            return;
        }

        string nextExecutorId = AIAgentHostExecutor.IdFor(nextAgent);

        if (!string.IsNullOrWhiteSpace(taskContext.ProgressLedger.InstructionOrQuestion))
        {
            ChatMessage instruction = new(ChatRole.Assistant, taskContext.ProgressLedger.InstructionOrQuestion);
            taskContext.ChatHistory.Add(instruction);

            // Target the instruction at the chosen speaker only.
            await context.SendMessageAsync(instruction, nextExecutorId, cancellationToken).ConfigureAwait(false);
        }

        this._currentSpeakerExecutorId = nextExecutorId;
        await context.SendMessageAsync(new TurnToken(taskContext.EmitUpdateEvents), nextExecutorId, cancellationToken).ConfigureAwait(false);
    }

    private async ValueTask ResetAndReplanAsync(MagenticTaskContext taskContext, IWorkflowContext context, CancellationToken cancellationToken)
    {
        bool wasStalled = taskContext.IsStalled;
        taskContext.Reset();
        this._currentSpeakerExecutorId = null;
        await context.SendMessageAsync(new ResetChatSignal(), cancellationToken: cancellationToken).ConfigureAwait(false);

        await this.UpdatePlanAndDelegateAsync(taskContext, context, cancellationToken, replanAfterStall: wasStalled).ConfigureAwait(false);
    }

    private async ValueTask PrepareFinalAnswerAsync(MagenticTaskContext taskContext, IWorkflowContext context, CancellationToken cancellationToken)
    {
        List<ChatMessage> messages = [await this._manager.PrepareFinalAnswerAsync(taskContext, context, cancellationToken).ConfigureAwait(false)];
        await context.YieldOutputAsync(messages, cancellationToken).ConfigureAwait(false);
        taskContext.IsTerminated = true;
        this._currentSpeakerExecutorId = null;
    }

    protected internal override async ValueTask OnCheckpointingAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        Task contextStateTask = this._taskContext == null
                              ? Task.CompletedTask
                              : context.QueueStateUpdateAsync(MagenticConstants.MagenticTaskContextKey,
                                                              this._taskContext.ExportState(),
                                                              cancellationToken: cancellationToken)
                                       .AsTask();

        Task currentSpeakerTask = context.QueueStateUpdateAsync(MagenticConstants.CurrentSpeakerStateKey,
                                                            this._currentSpeakerExecutorId,
                                                            cancellationToken: cancellationToken)
                                        .AsTask();

        await Task.WhenAll(base.OnCheckpointingAsync(context, cancellationToken).AsTask(),
                           contextStateTask,
                           currentSpeakerTask).ConfigureAwait(false);
    }

    protected internal override async ValueTask OnCheckpointRestoredAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        await Task.WhenAll(base.OnCheckpointRestoredAsync(context, cancellationToken).AsTask(),
                            LoadContextStateAsync(),
                            LoadCurrentSpeakerAsync()).ConfigureAwait(false);

        async Task LoadContextStateAsync()
        {
            MagenticTaskState? state = await context.ReadStateAsync<MagenticTaskState>(MagenticConstants.MagenticTaskContextKey, cancellationToken: cancellationToken)
                                                    .ConfigureAwait(false);

            if (state != null)
            {
                this._taskContext = new MagenticTaskContext(state, team, limits, []);
            }
        }

        async Task LoadCurrentSpeakerAsync()
        {
            this._currentSpeakerExecutorId = await context.ReadStateAsync<string?>(MagenticConstants.CurrentSpeakerStateKey, cancellationToken: cancellationToken)
                                                        .ConfigureAwait(false);
        }
    }
}
