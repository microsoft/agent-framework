// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
using Microsoft.Agents.ObjectModel.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;

internal sealed class ClearAllVariablesExecutor(ClearAllVariables model, WorkflowFormulaState state)
    : DeclarativeActionExecutor<ClearAllVariables>(model, state)
{
    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        EvaluationResult<VariablesToClearWrapper> variablesResult = this.Evaluator.GetValue(this.Model.Variables);

        string? scope = variablesResult.Value.Value switch
        {
            VariablesToClear.AllGlobalVariables => VariableScopeNames.Global,
            VariablesToClear.ConversationScopedVariables => WorkflowFormulaState.DefaultScopeName,
            VariablesToClear.ConversationHistory => null,
            VariablesToClear.UserScopedVariables => null,
            _ => null,
        };

        if (scope is not null)
        {
            await context.QueueClearScopeAsync(scope, cancellationToken).ConfigureAwait(false);
            Debug.WriteLine(
                $"""
                STATE: {this.GetType().Name} [{this.Id}]
                SCOPE: {scope}
                """);
        }

        return default;
    }
}
