// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Agents.Workflows.Reflection;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx.Types;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.ObjectModel;

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
        StreamingRun run = await InProcessExecution.StreamAsync(workflowBuilder.Build<WorkflowFormulaState>(), this.State);
        WorkflowEvent[] events = await run.WatchStreamAsync().ToArrayAsync();
        Assert.Contains(events, e => e is DeclarativeActionInvokedEvent);
        Assert.Contains(events, e => e is DeclarativeActionCompletedEvent);
        return events;
    }

    internal static void VerifyModel(DialogAction model, DeclarativeActionExecutor action)
    {
        Assert.Equal(model.Id, action.Id);
        Assert.Equal(model, action.Model);
    }

    protected void VerifyState(string variableName, FormulaValue expectedValue) => this.VerifyState(variableName, VariableScopeNames.Topic, expectedValue);

    internal void VerifyState(string variableName, string scopeName, FormulaValue expectedValue)
    {
        FormulaValue actualValue = this.State.Get(variableName, scopeName);
        Assert.Equal(expectedValue.Format(), actualValue.Format());
    }

    protected void VerifyUndefined(string variableName) => this.VerifyUndefined(variableName, VariableScopeNames.Topic);

    internal void VerifyUndefined(string variableName, string scopeName) =>
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

    internal sealed class TestWorkflowExecutor() :
        ReflectingExecutor<TestWorkflowExecutor>(nameof(TestWorkflowExecutor)),
        IMessageHandler<WorkflowFormulaState>
    {
        public async ValueTask HandleAsync(WorkflowFormulaState message, IWorkflowContext context) =>
            await context.SendMessageAsync(new ExecutorResultMessage(this.Id)).ConfigureAwait(false);
    }
}
