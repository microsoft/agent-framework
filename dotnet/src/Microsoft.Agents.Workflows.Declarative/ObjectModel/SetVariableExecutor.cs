// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Abstractions;
using Microsoft.PowerFx.Types;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Declarative.ObjectModel;

internal sealed class SetVariableExecutor(SetVariable model, WorkflowFormulaState state)
    : DeclarativeActionExecutor<SetVariable>(model, state)
{
    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        PropertyPath variablePath = Throw.IfNull(this.Model.Variable?.Path, $"{nameof(this.Model)}.{nameof(model.Variable)}");

        if (this.Model.Value is null)
        {
            await this.AssignAsync(variablePath, FormulaValue.NewBlank(), context).ConfigureAwait(false);
        }
        else
        {
            EvaluationResult<DataValue> expressionResult = this.Evaluator.GetValue(this.Model.Value);

            await this.AssignAsync(variablePath, expressionResult.Value.ToFormula(), context).ConfigureAwait(false);
        }

        return default;
    }
}
