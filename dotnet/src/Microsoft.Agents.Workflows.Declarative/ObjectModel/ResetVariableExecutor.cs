﻿// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Bot.ObjectModel;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Declarative.ObjectModel;

internal sealed class ResetVariableExecutor(ResetVariable model, DeclarativeWorkflowState state) :
    DeclarativeActionExecutor<ResetVariable>(model, state)
{
    protected override ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        PropertyPath variablePath = Throw.IfNull(this.Model.Variable, $"{nameof(this.Model)}.{nameof(model.Variable)}");

        this.State.Reset(this.Model.Variable);
        Debug.WriteLine(
            $"""
            STATE: {this.GetType().Name} [{this.Id}]
             NAME: {this.Model.Variable!.Format()}
            """);

        return default;
    }
}
