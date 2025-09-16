// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.ObjectModel;

internal sealed class ClearAllVariablesExecutor(ClearAllVariables model, WorkflowFormulaState state)
    : DeclarativeActionExecutor<ClearAllVariables>(model, state)
{
    protected override ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        EvaluationResult<VariablesToClearWrapper> variablesResult = this.State.Evaluator.GetValue<VariablesToClearWrapper>(this.Model.Variables);

        variablesResult.Value.Handle(new ScopeHandler(this.Id, this.State));

        return default;
    }

    private sealed class ScopeHandler(string executorId, WorkflowFormulaState state) : IEnumVariablesToClearHandler
    {
        public void HandleAllGlobalVariables()
        {
            this.ClearAll(VariableScopeNames.Global);
        }

        public void HandleConversationHistory()
        {
            // Not supported....
        }

        public void HandleConversationScopedVariables()
        {
            this.ClearAll(WorkflowFormulaState.DefaultScopeName);
        }

        public void HandleUnknownValue()
        {
            // No scope to clear for unknown values.
        }

        public void HandleUserScopedVariables()
        {
            // Not supported....
        }

        private void ClearAll(string scope)
        {
            state.ResetAll(scope);
            Debug.WriteLine(
                $"""
                 STATE: {this.GetType().Name} [{executorId}]
                 SCOPE: {scope}
                 """);
        }
    }
}
