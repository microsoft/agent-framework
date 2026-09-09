// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
using Microsoft.Agents.ObjectModel.Abstractions;
using Microsoft.PowerFx.Types;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;

internal sealed class SetTextVariableExecutor(SetTextVariable model, WorkflowFormulaState state)
    : DeclarativeActionExecutor<SetTextVariable>(model, state)
{
    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(this.Model.Variable);
        Throw.IfNull(this.Model.Value);

        EvaluationResult<string> expressionResult = this.Evaluator.Format(this.Model.Value);

        await this.AssignAsync(this.Model.Variable.Path, FormulaValue.New(expressionResult.Value), context, expressionResult.Sensitivity).ConfigureAwait(false);

        return default;
    }
}
