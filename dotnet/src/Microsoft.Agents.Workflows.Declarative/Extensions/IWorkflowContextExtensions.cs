// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Agents.Workflows.Declarative.Kit;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx.Types;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Declarative.Extensions;

internal static class IWorkflowContextExtensions
{
    public static ValueTask RaiseInvocationEventAsync(this IWorkflowContext context, DialogAction action, string? priorEventId = null) =>
        context.AddEventAsync(new DeclarativeActionInvokedEvent(action, priorEventId));

    public static ValueTask RaiseCompletionEventAsync(this IWorkflowContext context, DialogAction action) =>
        context.AddEventAsync(new DeclarativeActionCompletedEvent(action));

    public static ValueTask SendResultMessageAsync(this IWorkflowContext context, string id, object? result = null, CancellationToken cancellationToken = default) =>
        context.SendMessageAsync(new ExecutorResultMessage(id, result));

    public static ValueTask QueueStateResetAsync(this IWorkflowContext context, PropertyPath variablePath) =>
        context.QueueStateUpdateAsync(Throw.IfNull(variablePath.VariableName), UnassignedValue.Instance, Throw.IfNull(variablePath.VariableScopeName));

    public static ValueTask QueueStateUpdateAsync<TValue>(this IWorkflowContext context, PropertyPath variablePath, TValue? value) =>
        context.QueueStateUpdateAsync(Throw.IfNull(variablePath.VariableName), value, Throw.IfNull(variablePath.VariableScopeName));

    public static FormulaValue ReadState(this IWorkflowContext context, PropertyPath variablePath) =>
        context.ReadState(Throw.IfNull(variablePath.VariableName), Throw.IfNull(variablePath.VariableScopeName));

    public static FormulaValue ReadState(this IWorkflowContext context, string key, string? scopeName = null)
    {
        if (context is not DeclarativeWorkflowContext declarativeContext)
        {
            throw new DeclarativeActionException($"Invalid workflow context: {context.GetType().Name}.");
        }

        return declarativeContext.State.Get(key, scopeName);
    }

    public static async Task<WorkflowFormulaState> GetStateAsync(this IWorkflowContext context, CancellationToken cancellationToken) // %%% REFINE
    {
        if (context is DeclarativeWorkflowContext declarativeContext)
        {
            return declarativeContext.State;
        }

        WorkflowFormulaState state = new(RecalcEngineFactory.Create());

        await state.RestoreAsync(context, cancellationToken).ConfigureAwait(false);

        return state;
    }
}
