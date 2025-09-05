// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Reflection;

namespace Microsoft.Agents.Workflows.Declarative.Interpreter;

internal delegate ValueTask DelegateAction(IWorkflowContext context, CancellationToken cancellationToken);

internal sealed class DelegateActionExecutor : ReflectingExecutor<DelegateActionExecutor>, IMessageHandler<DeclarativeExecutorResult>
{
    private readonly DelegateAction? _action;

    public DelegateActionExecutor(string actionId, DelegateAction? action = null)
        : base(actionId)
    {
        this._action = action;
    }

    public async ValueTask HandleAsync(DeclarativeExecutorResult message, IWorkflowContext context)
    {
        if (this._action is not null)
        {
            await this._action.Invoke(context, default).ConfigureAwait(false);
        }

        await context.SendMessageAsync(new DeclarativeExecutorResult(this.Id)).ConfigureAwait(false);
    }
}
