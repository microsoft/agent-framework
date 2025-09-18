// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.ObjectModel;

internal sealed class ConditionGroupExecutor : DeclarativeActionExecutor<ConditionGroup>
{
    public static class Steps
    {
        public static string Item(ConditionGroup model, ConditionItem conditionItem)
        {
            if (conditionItem.Id is not null)
            {
                return conditionItem.Id;
            }
            int index = model.Conditions.IndexOf(conditionItem);
            return $"{model.Id}_Items{index}";
        }

        public static string Else(ConditionGroup model) => model.ElseActions.Id.Value ?? $"{model.Id}_Else";
    }

    public ConditionGroupExecutor(ConditionGroup model, WorkflowFormulaState state)
        : base(model, state)
    {
    }

    protected override bool IsDiscreteAction => false;

    public bool IsMatch(ConditionItem conditionItem, object? message)
    {
        ExecutorResultMessage executorMessage = ExecutorResultMessage.ThrowIfNot(message);
        return string.Equals(Steps.Item(this.Model, conditionItem), executorMessage.Result as string, StringComparison.Ordinal);
    }

    public bool IsElse(object? message)
    {
        ExecutorResultMessage executorMessage = ExecutorResultMessage.ThrowIfNot(message);
        return string.Equals(Steps.Else(this.Model), executorMessage.Result as string, StringComparison.Ordinal);
    }

    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        for (int index = 0; index < this.Model.Conditions.Length; ++index)
        {
            ConditionItem conditionItem = this.Model.Conditions[index];
            if (conditionItem.Condition is null)
            {
                continue; // Skip if no condition is defined
            }

            EvaluationResult<bool> expressionResult = this.Evaluator.GetValue(conditionItem.Condition);
            if (expressionResult.Value)
            {
                return Steps.Item(this.Model, conditionItem);
            }
        }

        return Steps.Else(this.Model);
    }

    public async ValueTask DoneAsync(IWorkflowContext context, ExecutorResultMessage _, CancellationToken cancellationToken) =>
        await context.RaiseCompletionEventAsync(this.Model).ConfigureAwait(false);
}
