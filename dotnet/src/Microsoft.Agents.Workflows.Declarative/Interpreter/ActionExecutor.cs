// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Reflection;

namespace Microsoft.Agents.Workflows.Declarative; // %%% TODO

/// <summary>
/// Base class for an action executor that receives the initial trigger message.
/// </summary>
public abstract class ActionExecutor :
    ReflectingExecutor<ActionExecutor>,
    IMessageHandler<string> // %%% IDK
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
    public async ValueTask HandleAsync(string message, IWorkflowContext context)
    {
        try
        {
            await this.ExecuteAsync(context, cancellationToken: default).ConfigureAwait(false);

            //await context.SendMessageAsync(new DeclarativeExecutorResult(this.Id)).ConfigureAwait(false); // %%% TODO
            await context.SendMessageAsync(this.Id).ConfigureAwait(false); // %%% TODO
        }
        catch (DeclarativeActionException exception)
        {
            Debug.WriteLine($"ERROR [{this.Id}] {exception.GetType().Name}\n{exception.Message}");
            throw;
        }
        catch (Exception exception)
        {
            Debug.WriteLine($"ERROR [{this.Id}] {exception.GetType().Name}\n{exception.Message}");
            throw new DeclarativeActionException($"Unhandled workflow failure - #{this.Id} ({this.GetType().Name})", exception);
        }
    }

    /// <summary>
    /// Executes the core logic of the action.
    /// </summary>
    /// <param name="context">The workflow execution context providing messaging and state services.</param>
    /// <param name="cancellationToken">A token that can be used to observe cancellation.</param>
    /// <returns>A <see cref="ValueTask"/> representing the asynchronous execution operation.</returns>
    protected abstract ValueTask ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken = default);
}
