// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Agents.Workflows.Reflection;

namespace Microsoft.Agents.Workflows.Declarative.Kit;

internal delegate ValueTask DelegateAction(IWorkflowContext context, CancellationToken cancellationToken);

internal sealed class DelegateActionExecutor : ReflectingExecutor<DelegateActionExecutor>, IMessageHandler<ActionExecutorResult>
{
    private readonly DelegateAction? _action;

    public DelegateActionExecutor(string actionId, DelegateAction? action = null)
        : base(actionId)
    {
        this._action = action;
    }

    public async ValueTask HandleAsync(ActionExecutorResult message, IWorkflowContext context)
    {
        if (this._action is not null)
        {
            await this._action.Invoke(new DeclarativeWorkflowContext(context), default).ConfigureAwait(false); // %%% NEEDED??? DeclarativeWorkflowContext
        }

        await context.SendMessageAsync(new ActionExecutorResult(this.Id)).ConfigureAwait(false);
    }
}
