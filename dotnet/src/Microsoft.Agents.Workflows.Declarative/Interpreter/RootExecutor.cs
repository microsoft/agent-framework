// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Reflection;
using Microsoft.Extensions.Configuration;

namespace Microsoft.Agents.Workflows.Declarative; // %%% TODO

/// <summary>
/// %%% COMMENT
/// </summary>
public abstract class RootExecutor<TInput> :
    ReflectingExecutor<RootExecutor<TInput>>,
    IMessageHandler<TInput>
    where TInput : notnull
{
    /// <summary>
    /// %%% COMMENT
    /// </summary>
    protected RootExecutor(string id, IConfiguration? configuration = null)
        : base(id)
    {
        this.Configuration = configuration;
    }

    private IConfiguration? Configuration { get; }

    /// <inheritdoc/>
    public async ValueTask HandleAsync(TInput message, IWorkflowContext context)
    {
        //await this.State.RestoreAsync(context, default).ConfigureAwait(false); // %%% TODO

        try
        {
            await this.ExecuteAsync(message, context, cancellationToken: default).ConfigureAwait(false);

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
    /// <param name="message">// %%% COMMENT</param>
    /// <param name="context"></param>
    /// <param name="cancellationToken"></param>
    /// <returns></returns>
    protected abstract ValueTask ExecuteAsync(TInput message, IWorkflowContext context, CancellationToken cancellationToken = default);

    /// <summary>
    /// %%% COMMENT
    /// </summary>
    /// <param name="name"></param>
    /// <returns></returns>
    protected string GetEnvironmentVariable(string name)
    {
        if (this.Configuration is not null)
        {
            return this.Configuration[name] ?? string.Empty;
        }

        return Environment.GetEnvironmentVariable(name) ?? string.Empty;
    }
}
