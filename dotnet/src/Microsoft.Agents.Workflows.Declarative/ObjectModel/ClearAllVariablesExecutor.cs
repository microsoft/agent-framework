// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.ObjectModel;

internal sealed class ClearAllVariablesExecutor(ClearAllVariables model) : DeclarativeActionExecutor<ClearAllVariables>(model)
{
    protected override ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        EvaluationResult<VariablesToClearWrapper> variablesResult = this.State.ExpressionEngine.GetValue<VariablesToClearWrapper>(this.Model.Variables, this.State.Scopes);

        variablesResult.Value.Handle(new ScopeHandler(this.State));

        return default;
    }

    private sealed class ScopeHandler(DeclarativeWorkflowState state) : IEnumVariablesToClearHandler
    {
        public void HandleAllGlobalVariables()
        {
            state.Clear(WorkflowScopeType.Global);
        }

        public void HandleConversationHistory()
        {
            throw new System.NotImplementedException(); // %%% DECISION: Is this to be supported ???
        }

        public void HandleConversationScopedVariables()
        {
            state.Clear(WorkflowScopeType.Topic);
        }

        public void HandleUnknownValue()
        {
            // No scope to clear for unknown values.
        }

        public void HandleUserScopedVariables()
        {
            state.Clear(WorkflowScopeType.Env); // %%% DECISION: Is this correct?  If not, what?
        }
    }
}
