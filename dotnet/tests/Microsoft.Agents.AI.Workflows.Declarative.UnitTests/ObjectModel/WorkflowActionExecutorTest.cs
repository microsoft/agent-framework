// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
using Microsoft.PowerFx.Types;
using Xunit.Abstractions;
using Xunit.Sdk;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.ObjectModel;

/// <summary>
/// Base test class for <see cref="DeclarativeActionExecutor"/> implementations.
/// </summary>
public abstract class WorkflowActionExecutorTest(ITestOutputHelper output) : WorkflowTest(output)
{
    internal WorkflowFormulaState State { get; } = new(RecalcEngineFactory.Create());

    protected ActionId CreateActionId() => new($"{this.GetType().Name}_{Guid.NewGuid():N}");

    protected string FormatDisplayName(string name) => $"{this.GetType().Name}_{name}";

    internal Task<WorkflowEvent[]> ExecuteAsync(string actionId, DelegateAction<ActionExecutorResult> executorAction) =>
        this.ExecuteAsync([new DelegateActionExecutor(actionId, this.State, executorAction)], isDiscrete: false);

    internal Task<WorkflowEvent[]> ExecuteAsync(Executor executor, string actionId, DelegateAction<ActionExecutorResult> executorAction) =>
        this.ExecuteAsync([executor, new DelegateActionExecutor(actionId, this.State, executorAction)], isDiscrete: false);

    internal async Task<WorkflowEvent[]> ExecuteAsync(DeclarativeActionExecutor executor, bool isDiscrete = true)
    {
        VerifyIsDiscrete(executor, isDiscrete);
        return await this.ExecuteAsync([executor], isDiscrete);
    }

    internal async Task<WorkflowEvent[]> ExecuteAsync(Executor[] executors, bool isDiscrete)
    {
        this.State.Bind();

        TestWorkflowExecutor workflowExecutor = new();
        WorkflowBuilder workflowBuilder = new(workflowExecutor);
        Executor prevExecutor = workflowExecutor;
        foreach (Executor executor in executors)
        {
            workflowBuilder.AddEdge(prevExecutor, executor);
            prevExecutor = executor;
        }

        await using StreamingRun run = await InProcessExecution.StreamAsync(workflowBuilder.Build(), this.State);
        WorkflowEvent[] events = await run.WatchStreamAsync().ToArrayAsync();

        if (isDiscrete)
        {
            VerifyInvocationEvent(events);
            VerifyCompletionEvent(events);
        }

        ExecutorFailedEvent[] failureEvents = events.OfType<ExecutorFailedEvent>().ToArray();
        switch (failureEvents.Length)
        {
            case 0:
                break;
            case 1:
                throw failureEvents[0].Data ?? new XunitException("Executor failed without exception data.");
            default:
                AggregateException aggregateException = new("One or more executor failures occurred.", failureEvents.Select(e => e.Data).Where(e => e is not null).Cast<Exception>());
                throw aggregateException;

        }

        return events;
    }

    internal static void VerifyModel(DialogAction model, DeclarativeActionExecutor action)
    {
        Assert.Equal(model.Id, action.Id);
        Assert.Equal(model, action.Model);
    }

    internal static void VerifyIsDiscrete(DeclarativeActionExecutor action, bool isDiscrete = true)
    {
        Assert.Equal(
            isDiscrete,
            action.GetType().BaseType?
                .GetProperty("IsDiscreteAction", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance)?
                .GetValue(action));
    }

    protected static void VerifyInvocationEvent(WorkflowEvent[] events) =>
        Assert.Contains(events, e => e is DeclarativeActionInvokedEvent);

    protected static void VerifyCompletionEvent(WorkflowEvent[] events) =>
        Assert.Contains(events, e => e is DeclarativeActionCompletedEvent);

    protected void VerifyState(string variableName, FormulaValue expectedValue) => this.VerifyState(variableName, WorkflowFormulaState.DefaultScopeName, expectedValue);

    protected void VerifyState(string variableName, string scopeName, FormulaValue expectedValue)
    {
        FormulaValue actualValue = this.State.Get(variableName, scopeName);
        Assert.Equal(expectedValue.Format(), actualValue.Format());
    }

    protected void VerifyUndefined(string variableName, string? scopeName = null) =>
        Assert.IsType<BlankValue>(this.State.Get(variableName, scopeName));

    protected static TAction AssignParent<TAction>(DialogAction.Builder actionBuilder) where TAction : DialogAction
    {
        OnActivity.Builder activityBuilder =
            new()
            {
                Id = new("root"),
            };

        activityBuilder.Actions.Add(actionBuilder);

        OnActivity model = activityBuilder.Build();

        return (TAction)model.Actions[0];
    }

    internal sealed class TestWorkflowExecutor() : Executor<WorkflowFormulaState>("test_workflow")
    {
        [SendsMessage(typeof(ActionExecutorResult))]
        public override async ValueTask HandleAsync(WorkflowFormulaState message, IWorkflowContext context, CancellationToken cancellationToken) =>
            await context.SendResultMessageAsync(this.Id, cancellationToken).ConfigureAwait(false);
    }
}
