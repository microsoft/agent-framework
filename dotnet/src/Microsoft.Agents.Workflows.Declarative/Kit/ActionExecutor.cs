// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Agents.Workflows.Reflection;

namespace Microsoft.Agents.Workflows.Declarative.Kit;

/// <summary>
/// Base class for an action executor that receives the initial trigger message.
/// </summary>
public abstract class ActionExecutor :
    ReflectingExecutor<ActionExecutor>,
    IMessageHandler<ActionExecutorResult>
{
    /// <summary>
    /// Initializes a new instance of the <see cref="ActionExecutor"/> class.
    /// </summary>
    /// <param name="id">The executor id</param>
    protected ActionExecutor(string id)
        : base(id)
    {
    }

    /// <inheritdoc/>
    public async ValueTask HandleAsync(ActionExecutorResult message, IWorkflowContext context)
    {
        await this.ExecuteAsync(new DeclarativeWorkflowContext(context), cancellationToken: default).ConfigureAwait(false);

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
