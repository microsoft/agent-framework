// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Reflection;

namespace Microsoft.Agents.Workflows.Declarative; // %%% TODO

/// <summary>
/// %%% COMMENT
/// </summary>
public abstract class ActionExecutor :
    ReflectingExecutor<ActionExecutor>,
    IMessageHandler<string>
{
    /// <summary>
    /// %%% COMMENT
    /// </summary>
    protected ActionExecutor(string id)
        : base(id)
    {
    }

    /// <inheritdoc/>
    public async ValueTask HandleAsync(string message, IWorkflowContext context)
    {
        //await this.State.RestoreAsync(context, default).ConfigureAwait(false); // %%% TODO

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
    /// %%% COMMENT
    /// </summary>
    /// <param name="context"></param>
    /// <param name="cancellationToken"></param>
    /// <returns></returns>
    protected abstract ValueTask ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken = default);
}
