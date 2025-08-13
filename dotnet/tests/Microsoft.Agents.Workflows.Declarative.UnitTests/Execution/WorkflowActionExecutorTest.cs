// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Core;
using Microsoft.Agents.Workflows.Declarative.Execution;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Agents.Workflows.Execution;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.PowerFx.Types;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.Execution;

/// <summary>
/// Base test class for <see cref="WorkflowActionExecutor"/> implementations.
/// </summary>
public abstract class WorkflowActionExecutorTest(ITestOutputHelper output) : WorkflowTest(output)
{
    internal WorkflowScopes Scopes { get; } = new();

    protected ActionId CreateActionId() => new($"{this.GetType().Name}_{Guid.NewGuid():N}");

    protected string FormatDisplayName(string name) => $"{this.GetType().Name}_{name}";

    internal async Task Execute(WorkflowActionExecutor executor)
    {
        WorkflowExecutionContext context = new(RecalcEngineFactory.Create(this.Scopes), this.Scopes, () => null!, NullLogger.Instance);
        executor.Attach(context);
        WorkflowBuilder workflowBuilder = new(executor);
        LocalRunner<string> runner = new(workflowBuilder.Build<string>());
        StreamingRun handle = await runner.StreamAsync("<placeholder>");
        WorkflowEvent[] events = await handle.WatchStreamAsync().ToArrayAsync();
    }

    internal void VerifyModel(DialogAction model, WorkflowActionExecutor action)
    {
        Assert.Equal(model.Id, action.Id);
        Assert.Equal(model, action.Model);
    }

    protected void VerifyState(string variableName, FormulaValue expectedValue) => this.VerifyState(variableName, WorkflowScopeType.Topic, expectedValue);

    internal void VerifyState(string variableName, WorkflowScopeType scope, FormulaValue expectedValue)
    {
        FormulaValue actualValue = this.Scopes.Get(variableName, scope);
        Assert.Equivalent(expectedValue, actualValue);
    }

    protected void VerifyUndefined(string variableName) => this.VerifyUndefined(variableName, WorkflowScopeType.Topic);

    internal void VerifyUndefined(string variableName, WorkflowScopeType scope)
    {
        Assert.IsType<BlankValue>(this.Scopes.Get(variableName, scope));
    }

    protected TAction AssignParent<TAction>(DialogAction.Builder actionBuilder) where TAction : DialogAction
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
}
