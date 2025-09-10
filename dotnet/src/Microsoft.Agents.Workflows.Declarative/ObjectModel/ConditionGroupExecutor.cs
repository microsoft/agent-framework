// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
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

    public ConditionGroupExecutor(ConditionGroup model, DeclarativeWorkflowState state)
        : base(model, state)
    {
    }

    public bool IsMatch(ConditionItem conditionItem, object? result)
    {
        if (result is not DeclarativeExecutorResult message)
        {
            return false;
        }

        return string.Equals(Steps.Item(this.Model, conditionItem), message.Result as string, StringComparison.Ordinal);
    }

    public bool IsElse(object? result)
    {
        if (result is not DeclarativeExecutorResult message)
        {
            return false;
        }

        return string.Equals(Steps.Else(this.Model), message.Result as string, StringComparison.Ordinal);
    }

#pragma warning disable CS1998 // Async method lacks 'await' operators and will run synchronously
    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
#pragma warning restore CS1998 // Async method lacks 'await' operators and will run synchronously
    {
        for (int index = 0; index < this.Model.Conditions.Length; ++index)
        {
            ConditionItem conditionItem = this.Model.Conditions[index];
            if (conditionItem.Condition is null)
            {
                continue; // Skip if no condition is defined
            }

            EvaluationResult<bool> expressionResult = this.State.ExpressionEngine.GetValue(conditionItem.Condition);
            if (expressionResult.Value)
            {
                return Steps.Item(this.Model, conditionItem);
            }
        }

        return Steps.Else(this.Model);
    }
}
