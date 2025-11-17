// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Abstractions;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;

internal sealed class SetVariableExecutor(SetVariable model, WorkflowFormulaState state)
    : DeclarativeActionExecutor<SetVariable>(model, state)
{
    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        if (this.Model.Value is null)
        {
            await this.AssignAsync(this.Model.Variable?.Path, FormulaValue.NewBlank(), context).ConfigureAwait(false);
        }
        else
        {
            EvaluationResult<DataValue> expressionResult = this.Evaluator.GetValue(this.Model.Value);

            await this.AssignAsync(this.Model.Variable?.Path, expressionResult.Value.ToFormula(), context).ConfigureAwait(false);
        }

        return default;
    }
}
