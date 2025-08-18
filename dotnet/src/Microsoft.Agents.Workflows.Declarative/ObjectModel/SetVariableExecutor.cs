// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Abstractions;
using Microsoft.PowerFx.Types;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Declarative.ObjectModel;

internal sealed class SetVariableExecutor(SetVariable model) : DeclarativeActionExecutor<SetVariable>(model)
{
    protected override ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        PropertyPath variablePath = Throw.IfNull(this.Model.Variable?.Path, $"{nameof(this.Model)}.{nameof(model.Variable)}");

        if (this.Model.Value is null)
        {
            this.AssignTarget(variablePath, FormulaValue.NewBlank());
        }
        else
        {
            EvaluationResult<DataValue> expressionResult = this.State.ExpressionEngine.GetValue(this.Model.Value);

            this.AssignTarget(variablePath, expressionResult.Value.ToFormulaValue());
        }

        return default;
    }
}
