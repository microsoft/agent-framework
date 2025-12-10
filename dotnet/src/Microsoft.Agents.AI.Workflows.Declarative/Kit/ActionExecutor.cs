// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;

namespace Microsoft.Agents.AI.Workflows.Declarative.Kit;

/// <summary>
/// Base class for action executors that do not consume the input message (most).
/// </summary>
/// <param name="id">The executor id</param>
/// <param name="session">Session to support formula expressions.</param>
public abstract class ActionExecutor(string id, FormulaSession session) : ActionExecutor<ActionExecutorResult>(id, session)
{
    /// <inheritdoc/>
    protected override ValueTask<object?> ExecuteAsync(IWorkflowContext context, ActionExecutorResult message, CancellationToken cancellationToken = default) =>
        this.ExecuteAsync(context, cancellationToken);

    /// <summary>
    /// Executes the core logic of the action.
    /// </summary>
    /// <param name="context">The workflow execution context providing messaging and state services.</param>
    /// <param name="cancellationToken">A token that can be used to observe cancellation.</param>
    /// <returns>A <see cref="ValueTask"/> representing the asynchronous execution operation.</returns>
    protected abstract ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken = default);

    /// <summary>
    /// Test wether the provided value matches the value returned by the prior executor.
    /// </summary>
    /// <param name="value">The value to test against the message result.</param>
    /// <param name="message">The message containing the prior executor result.</param>
    /// <returns>True if the value matches the message result</returns>
    public static bool IsMatch<TValue>(TValue value, object? message) where TValue : class
    {
        ActionExecutorResult executorMessage = ActionExecutorResult.ThrowIfNot(message);

        object? result = executorMessage.Result;
        if (result is TValue resultValue)
        {
            return value.Equals(resultValue);
        }

        return false;
    }
}

/// <summary>
/// Base class for an action executor that receives the initial trigger message.
/// </summary>
/// <typeparam name="TMessage">The type of message being handled</typeparam>
public abstract class ActionExecutor<TMessage> : Executor<TMessage>, IResettableExecutor where TMessage : notnull
{
    private readonly FormulaSession _session;

    /// <summary>
    /// Initializes a new instance of the <see cref="ActionExecutor{TMessage}"/> class.
    /// </summary>
    /// <param name="id">The executor id</param>
    /// <param name="session">Session to support formula expressions.</param>
    protected ActionExecutor(string id, FormulaSession session)
        : base(id)
    {
        this._session = session;
    }

    /// <inheritdoc/>
    public ValueTask ResetAsync()
    {
        return default;
    }

    /// <inheritdoc/>
    public override async ValueTask HandleAsync(TMessage message, IWorkflowContext context, CancellationToken cancellationToken)
    {
        object? result = await this.ExecuteAsync(new DeclarativeWorkflowContext(context, this._session.State), message, cancellationToken).ConfigureAwait(false);
        Debug.WriteLine($"RESULT #{this.Id} - {result ?? "(null)"}");

        await context.SendResultMessageAsync(this.Id, result, cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Executes the core logic of the action.
    /// </summary>
    /// <param name="context">The workflow execution context providing messaging and state services.</param>
    /// <param name="message">The the message handled by this executor.</param>
    /// <param name="cancellationToken">A token that can be used to observe cancellation.</param>
    /// <returns>A <see cref="ValueTask"/> representing the asynchronous execution operation.</returns>
    protected abstract ValueTask<object?> ExecuteAsync(IWorkflowContext context, TMessage message, CancellationToken cancellationToken = default);
}
