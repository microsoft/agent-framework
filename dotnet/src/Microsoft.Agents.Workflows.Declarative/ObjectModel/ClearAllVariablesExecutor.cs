// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.ObjectModel;

internal sealed class ClearAllVariablesExecutor(ClearAllVariables model) : DeclarativeActionExecutor<ClearAllVariables>(model)
{
    protected override ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        EvaluationResult<VariablesToClearWrapper> variablesResult = this.State.ExpressionEngine.GetValue<VariablesToClearWrapper>(this.Model.Variables);

        variablesResult.Value.Handle(new ScopeHandler(this.Id, this.State));

        return default;
    }

    private sealed class ScopeHandler(string executorId, DeclarativeWorkflowState state) : IEnumVariablesToClearHandler
    {
        public void HandleAllGlobalVariables()
        {
            this.ClearAll(VariableScopeNames.Global);
        }

        public void HandleConversationHistory()
        {
            throw new System.NotImplementedException(); // %%% DECISION: Is this to be supported ???
        }

        public void HandleConversationScopedVariables()
        {
            this.ClearAll(VariableScopeNames.Topic);
        }

        public void HandleUnknownValue()
        {
            // No scope to clear for unknown values.
        }

        public void HandleUserScopedVariables()
        {
            this.ClearAll(VariableScopeNames.Environment); // %%% DECISION: Is this correct?  If not, what?
        }

        private void ClearAll(string scope)
        {
            state.Clear(scope);
            Debug.WriteLine(
                $"""
                 STATE: {this.GetType().Name} [{executorId}]
                 SCOPE: {scope}
                 """);
        }
    }
}
