// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Execution;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.Handlers;

internal sealed class ClearAllVariablesAction : ProcessAction<ClearAllVariables>
{
    public ClearAllVariablesAction(ClearAllVariables source)
        : base(source)
    {
    }

    protected override Task HandleAsync(ProcessActionContext context, CancellationToken cancellationToken)
    {
        EvaluationResult<VariablesToClearWrapper> result = context.ExpressionEngine.GetValue<VariablesToClearWrapper>(this.Model.Variables, context.Scopes); // %%% FAILURE CASE (CATCH) & NULL OVERRIDE

        result.Value.Handle(new ScopeHandler(context));

        return Task.CompletedTask;
    }

    private sealed class ScopeHandler(ProcessActionContext context) : IEnumVariablesToClearHandler
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
