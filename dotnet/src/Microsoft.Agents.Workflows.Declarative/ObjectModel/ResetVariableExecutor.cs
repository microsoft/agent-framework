// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Declarative.ObjectModel;

internal sealed class ResetVariableExecutor(ResetVariable model) :
    DeclarativeActionExecutor<ResetVariable>(model)
{
    protected override ValueTask ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        PropertyPath variablePath = Throw.IfNull(this.Model.Variable, $"{nameof(this.Model)}.{nameof(model.Variable)}");

        this.Context.Engine.ClearScopedVariable(this.Context.Scopes, this.Model.Variable);
        Debug.WriteLine(
            $"""
            !!! CLEAR {this.GetType().Name} [{this.Id}]
                NAME: {this.Model.Variable!.Format()}
            """);

        return default;
    }
}
