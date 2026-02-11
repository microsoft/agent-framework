// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
using Microsoft.Agents.ObjectModel.Abstractions;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;

internal sealed class SetVariableExecutor(SetVariable model, WorkflowFormulaState state)
    : DeclarativeActionExecutor<SetVariable>(model, state)
{
    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(this.Model.Variable);
        Throw.IfNull(this.Model.Value);

        EvaluationResult<DataValue> expressionResult = this.Evaluator.GetValue(this.Model.Value);

        await this.AssignAsync(this.Model.Variable.Path, expressionResult.Value.ToFormula(), context).ConfigureAwait(false);

        return default;
    }
}
