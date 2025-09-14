// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Extensions;

namespace Microsoft.Agents.Workflows.Declarative.Interpreter;

internal delegate ValueTask DelegateAction<TMessage>(IWorkflowContext context, TMessage message, CancellationToken cancellationToken) where TMessage : notnull;

internal sealed class DelegateActionExecutor(string actionId, DelegateAction<ExecutorResultMessage>? action = null, bool emitResult = true)
    : DelegateActionExecutor<ExecutorResultMessage>(actionId, action, emitResult)
{
    public override ValueTask HandleAsync(ExecutorResultMessage message, IWorkflowContext context)
    {
        Debug.WriteLine($"RESULT #{this.Id} - {message.Result ?? "(null)"}");

        return base.HandleAsync(message, context);
    }
}

internal class DelegateActionExecutor<TMessage> : Executor<TMessage> where TMessage : notnull
{
    private readonly DelegateAction<TMessage>? _action;
    private readonly bool _emitResult;

    public DelegateActionExecutor(string actionId, DelegateAction<TMessage>? action = null, bool emitResult = true)
        : base(actionId)
    {
        this._action = action;
        this._emitResult = emitResult;
    }

    public override async ValueTask HandleAsync(TMessage message, IWorkflowContext context)
    {
        if (this._action is not null)
        {
            await this._action.Invoke(context, message, default).ConfigureAwait(false);
        }

        if (this._emitResult)
        {
            await context.SendResultMessageAsync(this.Id).ConfigureAwait(false);
        }
    }
}
