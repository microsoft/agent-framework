// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Interpreter;

namespace Microsoft.Agents.Workflows.Declarative.Kit;

/// <summary>
/// Base class for an action executor that receives the initial trigger message.
/// </summary>
public abstract class ActionExecutor : Executor<ActionExecutorResult>
{
    private readonly FormulaSession _context;

    /// <summary>
    /// Initializes a new instance of the <see cref="ActionExecutor"/> class.
    /// </summary>
    /// <param name="id">The executor id</param>
    /// <param name="session">Session to support formula expressions.</param>
    protected ActionExecutor(string id, FormulaSession session)
        : base(id)
    {
        this._context = session;
    }

    /// <inheritdoc/>
    public override async ValueTask HandleAsync(ActionExecutorResult message, IWorkflowContext context)
    {
        await this.ExecuteAsync(new DeclarativeWorkflowContext(context, this._context.State), cancellationToken: default).ConfigureAwait(false);

        await context.SendMessageAsync(new ActionExecutorResult(this.Id)).ConfigureAwait(false);
    }

    /// <summary>
    /// Executes the core logic of the action.
    /// </summary>
    /// <param name="context">The workflow execution context providing messaging and state services.</param>
    /// <param name="cancellationToken">A token that can be used to observe cancellation.</param>
    /// <returns>A <see cref="ValueTask"/> representing the asynchronous execution operation.</returns>
    protected abstract ValueTask ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken = default);
}
