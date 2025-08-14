// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Abstractions;
using Microsoft.PowerFx.Types;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Declarative.Execution;

internal sealed class SetVariableExecutor(SetVariable model) : WorkflowActionExecutor<SetVariable>(model)
{
    protected override ValueTask ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        PropertyPath variablePath = Throw.IfNull(this.Model.Variable?.Path, $"{nameof(this.Model)}.{nameof(model.Variable)}");

        if (this.Model.Value is null)
        {
            this.AssignTarget(this.Context, variablePath, FormulaValue.NewBlank());
        }
        else
        {
            EvaluationResult<DataValue> result = this.Context.ExpressionEngine.GetValue(this.Model.Value, this.Context.Scopes);

            this.AssignTarget(this.Context, variablePath, result.Value.ToFormulaValue());
        }

        return new ValueTask();
    }
}
