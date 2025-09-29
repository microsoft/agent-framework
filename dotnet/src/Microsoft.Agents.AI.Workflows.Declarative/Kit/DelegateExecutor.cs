// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows.Declarative.Kit;

/// <summary>
/// Signature for a delegate that can be used with <see cref="DelegateExecutor{TMessages}"/>.
/// </summary>
/// <typeparam name="TMessage">The type of message being handled</typeparam>
/// <param name="context">The workflow execution context providing messaging and state services.</param>
/// <param name="message">The the message handled by this executor.</param>
/// <param name="cancellationToken">A token that can be used to observe cancellation.</param>
/// <returns>A <see cref="ValueTask"/> representing the asynchronous execution operation.</returns>
public delegate ValueTask DelegateAction<TMessage>(IWorkflowContext context, TMessage message, CancellationToken cancellationToken) where TMessage : notnull;

/// <summary>
/// Base class for an action executor that receives the initial trigger message.
/// </summary>
public sealed class DelegateExecutor(string id, FormulaSession session, DelegateAction<ActionExecutorResult>? action = null)
    : DelegateExecutor<ActionExecutorResult>(id, session, action);

/// <summary>
/// Base class for an action executor that receives the initial trigger message.
/// </summary>
/// <typeparam name="TMessage">The type of message being handled</typeparam>
public class DelegateExecutor<TMessage> : ActionExecutor<TMessage> where TMessage : notnull
{
    private readonly DelegateAction<TMessage>? _action;

    /// <summary>
    /// Initializes a new instance of the <see cref="ActionExecutor"/> class.
    /// </summary>
    /// <param name="id">The executor id</param>
    /// <param name="session">Session to support formula expressions.</param>
    /// <param name="action">An optional delegate to execute.</param>
    public DelegateExecutor(string id, FormulaSession session, DelegateAction<TMessage>? action = null)
        : base(id, session)
    {
        this._action = action;
    }

    /// <inheritdoc/>
    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, TMessage message, CancellationToken cancellationToken = default)
    {
        if (this._action is not null)
        {
            await this._action.Invoke(context, message, cancellationToken).ConfigureAwait(false);
        }

        return default;
    }
}
