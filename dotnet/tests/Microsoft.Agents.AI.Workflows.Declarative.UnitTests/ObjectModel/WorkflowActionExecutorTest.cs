// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
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

    internal async Task<WorkflowEvent[]> ExecuteAsync(DeclarativeActionExecutor executor)
    {
        TestWorkflowExecutor workflowExecutor = new();
        WorkflowBuilder workflowBuilder = new(workflowExecutor);
        workflowBuilder.AddEdge(workflowExecutor, executor);
        await using StreamingRun run = await InProcessExecution.StreamAsync(workflowBuilder.Build(), this.State);
        WorkflowEvent[] events = await run.WatchStreamAsync().ToArrayAsync();
        Assert.Contains(events, e => e is DeclarativeActionInvokedEvent);
        Assert.Contains(events, e => e is DeclarativeActionCompletedEvent);
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

    protected void VerifyState(string variableName, FormulaValue expectedValue) => this.VerifyState(variableName, WorkflowFormulaState.DefaultScopeName, expectedValue);

    internal void VerifyState(string variableName, string scopeName, FormulaValue expectedValue)
    {
        FormulaValue actualValue = this.State.Get(variableName, scopeName);
        Assert.Equal(expectedValue.Format(), actualValue.Format());
    }

    internal void VerifyUndefined(string variableName, string? scopeName = null) =>
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
        public override async ValueTask HandleAsync(WorkflowFormulaState message, IWorkflowContext context, CancellationToken cancellationToken) =>
            await context.SendResultMessageAsync(this.Id, cancellationToken).ConfigureAwait(false);
    }
}
