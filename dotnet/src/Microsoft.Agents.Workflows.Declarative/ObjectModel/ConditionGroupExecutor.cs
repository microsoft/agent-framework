// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Bot.ObjectModel;

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

    public ConditionGroupExecutor(ConditionGroup model)
        : base(model)
    {
    }

    public bool IsMatch(ConditionItem conditionItem, object? result)
    {
        if (result is not ExecutionResultMessage message)
        {
            return false;
        }

        return string.Equals(Steps.Item(this.Model, conditionItem), message.Result as string, StringComparison.Ordinal);
    }

    public bool IsElse(object? result)
    {
        if (result is not ExecutionResultMessage message)
        {
            return false;
        }

        return string.Equals(Steps.Else(this.Model), message.Result as string, StringComparison.Ordinal);
    }

    protected override ValueTask ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        for (int index = 0; index < this.Model.Conditions.Length; ++index)
        {
            ConditionItem conditionItem = this.Model.Conditions[index];
            bool result = this.Context.Engine.Eval(conditionItem.Condition?.ExpressionText ?? "true").AsBoolean();
            if (result)
            {
                this.Context.Result = Steps.Item(this.Model, conditionItem);
                break;
            }
        }

        this.Context.Result ??= Steps.Else(this.Model);

        return default;
    }
}
