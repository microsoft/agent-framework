// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Reflection;

namespace Microsoft.Agents.Workflows.Declarative.Interpreter;

internal sealed class DelegateActionExecutor : ReflectingExecutor<DelegateActionExecutor>, IMessageHandler<ExecutionResultMessage>
{
    private readonly Func<ValueTask>? _action;

    public DelegateActionExecutor(string actionId, Action? action = null)
        : this(actionId,
               action is null ?
               null :
               () =>
               {
                   action?.Invoke();
                   return default;
               })
    { }

    public DelegateActionExecutor(string actionId, Func<ValueTask>? action = null)
        : base(actionId)
    {
        this._action = action;
    }

    public async ValueTask HandleAsync(ExecutionResultMessage message, IWorkflowContext context)
    {
        if (this._action is not null)
        {
            await this._action.Invoke().ConfigureAwait(false);
        }

        await context.SendMessageAsync(new ExecutionResultMessage(this.Id)).ConfigureAwait(false);
    }
}
