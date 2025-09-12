// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows.Declarative.Interpreter;

internal delegate ValueTask DelegateAction(IWorkflowContext context, object? message, CancellationToken cancellationToken);

internal sealed class DelegateActionExecutor(string actionId, DelegateAction? action = null)
    : DelegateActionExecutor<DeclarativeExecutorResult>(actionId, action);

internal class DelegateActionExecutor<TInput> : Executor<TInput>
{
    private readonly DelegateAction? _action;

    public DelegateActionExecutor(string actionId, DelegateAction? action = null)
        : base(actionId)
    {
        this._action = action;
    }
    protected virtual bool EmitResultEvent => true;

    public override async ValueTask HandleAsync(TInput message, IWorkflowContext context)
    {
        if (this._action is not null)
        {
            await this._action.Invoke(context, message, default).ConfigureAwait(false);
        }

        if (this.EmitResultEvent)
        {
            await this.SendResultMessageAsync(context).ConfigureAwait(false); // %%% EXTENSION
        }
    }

    protected ValueTask SendResultMessageAsync(IWorkflowContext context, object? result = null, CancellationToken cancellationToken = default) =>
        context.SendMessageAsync(new DeclarativeExecutorResult(this.Id, result));
}
