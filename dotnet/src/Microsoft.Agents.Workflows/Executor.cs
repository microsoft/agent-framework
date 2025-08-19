// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Reflection;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Execution;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// A component that processes messages in a <see cref="Workflow"/>.
/// </summary>
[DebuggerDisplay("{GetType().Name}{Id}")]
public abstract class Executor : IIdentified
{
    /// <summary>
    /// A unique identifier for the executor.
    /// </summary>
    public string Id { get; }

    /// <summary>
    /// Initialize the executor with a unique identifier
    /// </summary>
    /// <param name="id">A optional unique identifier for the executor. If <c>null</c>, a type-tagged
    /// UUID will be generated.</param>
    protected Executor(string? id = null)
    {
        this.Id = id ?? $"{this.GetType().Name}/{Guid.NewGuid():N}";
    }

    /// <summary>
    /// Override this method to register handlers for the executor.
    /// </summary>
    protected abstract RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder);

    private MessageRouter? _router = null;
    internal MessageRouter Router
    {
        get
        {
            if (this._router == null)
            {
                RouteBuilder routeBuilder = this.ConfigureRoutes(new RouteBuilder());
                this._router = routeBuilder.Build();
            }

            return this._router;
        }
    }

    /// <summary>
    /// Process an incoming message using the registered handlers.
    /// </summary>
    /// <param name="message">The message to be processed by the executor.</param>
    /// <param name="context">The workflow context in which the executor executes.</param>
    /// <returns>A ValueTask representing the asynchronous operation, wrapping the output from the executor.</returns>
    /// <exception cref="NotSupportedException">No handler found for the message type.</exception>
    /// <exception cref="TargetInvocationException">An exception is generated while handling the message.</exception>
    public async ValueTask<object?> ExecuteAsync(object message, IWorkflowContext context)
    {
        await context.AddEventAsync(new ExecutorInvokeEvent(this.Id, message)).ConfigureAwait(false);

        CallResult? result = await this.Router.RouteMessageAsync(message, context, requireRoute: true)
                                              .ConfigureAwait(false);

        ExecutorEvent executionResult;
        if (result == null || result.IsSuccess)
        {
            executionResult = new ExecutorCompleteEvent(this.Id, result?.Result);
        }
        else
        {
            executionResult = new ExecutorFailureEvent(this.Id, result.Exception);
        }

        await context.AddEventAsync(executionResult).ConfigureAwait(false);

        if (result == null)
        {
            throw new NotSupportedException(
                $"No handler found for message type {message.GetType().Name} in executor {this.GetType().Name}.");
        }

        if (!result.IsSuccess)
        {
            throw new TargetInvocationException($"Error invoking handler for {message.GetType()}", result.Exception!);
        }

        if (result.IsVoid)
        {
            return null; // Void result.
        }

        // If we had a real return type, raise it as a SendMessage; TODO: Should we have a way to disable this behaviour?
        if (result.Result != null && ExecutorOptions.Default.AutoSendMessageHandlerResultObject)
        {
            await context.SendMessageAsync(result.Result).ConfigureAwait(false);
        }

        return result.Result;
    }

    /// <summary>
    /// A set of <see cref="Type"/>s, representing the messages this executor can handle.
    /// </summary>
    public ISet<Type> InputTypes => this.Router.IncomingTypes;

    /// <summary>
    /// A set of <see cref="Type"/>s, representing the messages this executor can produce as output.
    /// </summary>
    public virtual ISet<Type> OutputTypes { get; } = new HashSet<Type>([typeof(object)]);

    /// <summary>
    /// Checks if the executor can handle a specific message type.
    /// </summary>
    /// <param name="messageType"></param>
    /// <returns></returns>
    public bool CanHandle(Type messageType) => this.Router.CanHandle(messageType);
}
