// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;

internal sealed record ParallelForeachIterationResult(
    int Index,
    WorkflowStateChange[] StateChanges,
    WorkflowEvent[] Events,
    ChatMessage[] ConversationMessages);

/// <summary>
/// Runs one Foreach body through the existing workflow runtime with isolated formula state.
/// </summary>
internal static class ParallelForeachIterationRunner
{
    public static void ValidateBody(Foreach model)
    {
        DialogAction[] bodyActions =
        [
            .. model.Descendants()
                .OfType<DialogAction>()
                .Where(action => BelongsToLoopBody(action, model)),
        ];
        HashSet<string> bodyActionIds =
        [
            .. bodyActions
                .Select(action => action.Id.Value),
        ];

        foreach (DialogAction action in bodyActions)
        {
            if (action is Question or RequestExternalInput)
            {
                Reject(model, action, "it can await external input and cannot be checkpointed safely");
            }

            if (action is InvokeFunctionTool or InvokeMcpTool)
            {
                Reject(model, action, "it can suspend for external input and cannot be checkpointed safely");
            }

            if (action is AddConversationMessage or CopyConversationMessages)
            {
                Reject(model, action, "it mutates a conversation immediately and cannot be staged safely");
            }

            if (action is InvokeAzureAgent { ConversationId: not null } or HttpRequestAction { ConversationId: not null })
            {
                Reject(model, action, "an explicit conversation target cannot be isolated per iteration");
            }

            if (action is EndDialog or EndConversation or CancelAllDialogs or CancelDialog)
            {
                Reject(model, action, "it terminates or cancels workflow-wide control flow");
            }

            if (action is BreakLoop or ContinueLoop && TargetsLoop(action, model))
            {
                Reject(model, action, $"{action.GetType().Name} cannot target the parallel loop");
            }

            if (action is GotoAction gotoAction)
            {
                string targetId = gotoAction.ActionId.Value;
                if (!bodyActionIds.Contains(targetId) || TargetsDifferentParallelLoop(gotoAction, model))
                {
                    Reject(model, action, $"GotoAction target '{targetId}' is outside the parallel body");
                }
            }
        }
    }

    private static void Reject(Foreach model, DialogAction action, string reason) =>
        throw new DeclarativeModelException(
            $"Parallel Foreach '{model.Id.Value}' cannot execute action '{action.Id.Value}' " +
            $"({action.GetType().Name}): {reason}.");

    public static async Task<ParallelForeachIterationResult> RunAsync(
        Foreach model,
        FormulaValue value,
        int index,
        WorkflowStateSnapshot stateSnapshot,
        DeclarativeWorkflowOptions workflowOptions,
        TimeSpan? timeout,
        Action<Exception> reportFailure,
        CancellationToken cancellationToken)
    {
        using CancellationTokenSource timeoutSource = new();
        using CancellationTokenSource iterationSource = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, timeoutSource.Token);
        if (timeout.HasValue)
        {
            timeoutSource.CancelAfter(timeout.Value);
        }

        WorkflowFormulaState branchState = WorkflowFormulaState.CreateBranch(workflowOptions.CreateRecalcEngine(), stateSnapshot);
        WorkflowConversationMessageBuffer conversationMessageBuffer = new();
        branchState.ConversationMessageBuffer = conversationMessageBuffer;
        branchState.ParallelFailureReporter = reportFailure;
        SetLoopVariable(branchState, model.Value!.Path, new PortableValue(value.AsPortable()).ToFormula());
        if (model.Index is not null)
        {
            SetLoopVariable(branchState, model.Index.Path, FormulaValue.New(index));
        }
        branchState.Bind();
        branchState.BeginTrackingChanges();

        Workflow workflow = BuildIterationWorkflow(model, branchState, workflowOptions);

        StreamingRun? run = null;
        bool runCanceled = false;
        try
        {
            run = await InProcessExecution.RunStreamingAsync(
                workflow,
                new ActionExecutorResult(model.Id.Value),
                cancellationToken: iterationSource.Token).ConfigureAwait(false);

            List<WorkflowEvent> eventList = [];
            await foreach (WorkflowEvent workflowEvent in run.WatchStreamAsync(blockOnPendingRequest: false, iterationSource.Token).ConfigureAwait(false))
            {
                eventList.Add(workflowEvent);
            }

            if (iterationSource.IsCancellationRequested)
            {
                await run.CancelRunAsync().ConfigureAwait(false);
                runCanceled = true;
            }

            if (timeoutSource.IsCancellationRequested)
            {
                throw new TimeoutException(
                    $"The iteration exceeded its timeout of {timeout.GetValueOrDefault().TotalMilliseconds} ms.");
            }

            cancellationToken.ThrowIfCancellationRequested();

            RunStatus status = await run.GetStatusAsync(iterationSource.Token).ConfigureAwait(false);
            WorkflowEvent[] events = [.. eventList];

            Exception[] failures =
            [
                .. events
                    .OfType<WorkflowErrorEvent>()
                    .Select(
                        workflowError =>
                            workflowError.Data as Exception ??
                            new DeclarativeActionException(
                                "The iteration failed without exception data.")),
            ];
            if (failures.Length > 0)
            {
                throw failures.Length == 1 ? failures[0] : new AggregateException(failures);
            }

            if (status == RunStatus.PendingRequests || events.Any(workflowEvent => workflowEvent is RequestInfoEvent))
            {
                throw new DeclarativeActionException(
                    "The iteration requested external input. " +
                    "Checkpointing an in-flight parallel iteration is not supported.");
            }

            if (status != RunStatus.Idle)
            {
                throw new DeclarativeActionException(
                    $"The iteration ended with unsupported status '{status}'.");
            }

            WorkflowStateChange[] stateChanges =
            [
                .. branchState
                    .CaptureChanges()
                    .Where(change => !Matches(change, model.Value.Path) && (model.Index is null || !Matches(change, model.Index.Path))),
            ];
            WorkflowEvent[] bufferedEvents = [.. events.Where(workflowEvent => ShouldReplay(workflowEvent, model.Id.Value))];

            return new(index, stateChanges, bufferedEvents, [.. conversationMessageBuffer.Messages]);
        }
        catch (OperationCanceledException) when (timeoutSource.IsCancellationRequested)
        {
            throw new TimeoutException(
                $"The iteration exceeded its timeout of {timeout!.Value.TotalMilliseconds} ms.");
        }
        finally
        {
            if (run is not null)
            {
                if (iterationSource.IsCancellationRequested && !runCanceled)
                {
                    await run.CancelRunAsync().ConfigureAwait(false);
                }

                await run.DisposeAsync().ConfigureAwait(false);
            }
        }
    }

    private static Workflow BuildIterationWorkflow(
        Foreach model,
        WorkflowFormulaState state,
        DeclarativeWorkflowOptions workflowOptions)
    {
        DelegateActionExecutor root = new(model.Id.Value, state);
        WorkflowActionVisitor visitor = new(root, state, workflowOptions);
        WorkflowElementWalker walker = new(visitor);
        foreach (DialogAction action in model.Actions)
        {
            walker.Visit(action);
        }

        return visitor.Complete();
    }

    private static void SetLoopVariable(WorkflowFormulaState state, PropertyPath path, FormulaValue value) =>
        state.Set(path.VariableName!, value, path.NamespaceAlias);

    private static bool Matches(WorkflowStateChange change, PropertyPath path) =>
        string.Equals(change.VariableName, path.VariableName, StringComparison.Ordinal) &&
        string.Equals(change.ScopeName, WorkflowFormulaState.GetScopeName(path.NamespaceAlias), StringComparison.Ordinal);

    private static bool ShouldReplay(WorkflowEvent workflowEvent, string rootExecutorId) =>
        (workflowEvent is not WorkflowStartedEvent
            and not SuperStepEvent
            and not WorkflowErrorEvent
            and not RequestInfoEvent
            and not ExecutorFailedEvent) &&
        (workflowEvent is not ExecutorEvent executorEvent || executorEvent.ExecutorId != rootExecutorId);

    private static bool TargetsDifferentParallelLoop(DialogAction action, Foreach loop)
    {
        BotElement? ancestor = action.Parent;
        while (ancestor is not null && ancestor is not Foreach)
        {
            ancestor = ancestor.Parent;
        }
        return ancestor is Foreach ancestorLoop
            && !ancestorLoop.Id.Equals(loop.Id)
            && ForeachExecutionOptions.Parse(ancestorLoop).IsParallel;
    }

    private static bool BelongsToLoopBody(DialogAction action, Foreach loop)
    {
        BotElement? ancestor = action.Parent;
        while (ancestor is not null)
        {
            if (ancestor is Foreach ancestorLoop && ForeachExecutionOptions.Parse(ancestorLoop).IsParallel)
            {
                return ancestorLoop.Id.Equals(loop.Id);
            }

            ancestor = ancestor.Parent;
        }

        return false;
    }

    private static bool TargetsLoop(DialogAction action, Foreach loop)
    {
        BotElement? ancestor = action.Parent;
        while (ancestor is not null && ancestor is not Foreach)
        {
            ancestor = ancestor.Parent;
        }

        return ancestor is Foreach ancestorLoop && ancestorLoop.Id.Equals(loop.Id);
    }
}
