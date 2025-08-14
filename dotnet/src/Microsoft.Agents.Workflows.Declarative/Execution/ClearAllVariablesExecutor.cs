// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.Execution;

internal sealed class ClearAllVariablesExecutor(ClearAllVariables model) : WorkflowActionExecutor<ClearAllVariables>(model)
{
    protected override ValueTask ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        EvaluationResult<VariablesToClearWrapper> result = this.Context.ExpressionEngine.GetValue<VariablesToClearWrapper>(this.Model.Variables, this.Context.Scopes);

        result.Value.Handle(new ScopeHandler(this.Context));

        return new ValueTask();
    }

    private sealed class ScopeHandler(WorkflowExecutionContext context) : IEnumVariablesToClearHandler
    {
        public void HandleAllGlobalVariables()
        {
            context.Engine.ClearScope(context.Scopes, WorkflowScopeType.Global);
        }

        public void HandleConversationHistory()
        {
            throw new System.NotImplementedException(); // %%% LOG / NO EXCEPTION - Is this to be supported ???
        }

        public void HandleConversationScopedVariables()
        {
            context.Engine.ClearScope(context.Scopes, WorkflowScopeType.Topic);
        }

        public void HandleUnknownValue()
        {
            // No scope to clear for unknown values.
        }

        public void HandleUserScopedVariables()
        {
            context.Engine.ClearScope(context.Scopes, WorkflowScopeType.Env);
        }
    }
}
