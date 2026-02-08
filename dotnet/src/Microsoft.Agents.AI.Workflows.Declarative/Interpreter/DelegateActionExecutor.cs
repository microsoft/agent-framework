// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;

namespace Microsoft.Agents.AI.Workflows.Declarative.Interpreter;

internal sealed class DelegateActionExecutor(string actionId, WorkflowFormulaState state, DelegateAction<ActionExecutorResult>? action = null, bool emitResult = true)
    : DelegateActionExecutor<ActionExecutorResult>(actionId, state, action, emitResult)
{
    public override ValueTask HandleAsync(ActionExecutorResult message, IWorkflowContext context, CancellationToken cancellationToken)
    {
        Debug.WriteLine($"RESULT #{this.Id} - {message.Result ?? "(null)"}");

        return base.HandleAsync(message, context, cancellationToken);
    }
}

internal class DelegateActionExecutor<TMessage> : Executor<TMessage>, IResettableExecutor, IModeledAction where TMessage : notnull
{
    private readonly WorkflowFormulaState _state;
    private readonly DelegateAction<TMessage>? _action;
    private readonly bool _emitResult;

    public DelegateActionExecutor(string actionId, WorkflowFormulaState state, DelegateAction<TMessage>? action = null, bool emitResult = true)
        : base(actionId)
    {
        this._state = state;
        this._action = action;
        this._emitResult = emitResult;
    }

    /// <inheritdoc/>
    public ValueTask ResetAsync()
    {
        return default;
    }

    public override async ValueTask HandleAsync(TMessage message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        if (this._action is not null)
        {
            await this._action.Invoke(new DeclarativeWorkflowContext(context, this._state), message, cancellationToken).ConfigureAwait(false);
        }

        if (this._emitResult)
        {
            await context.SendResultMessageAsync(this.Id, cancellationToken).ConfigureAwait(false);
        }
    }
}
