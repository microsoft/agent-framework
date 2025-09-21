// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Execution;
using Microsoft.Shared.Diagnostics;

using MessageHandlerF =
    System.Func<
        object, // message
        Microsoft.Agents.Workflows.IWorkflowContext, // context
        System.Threading.Tasks.ValueTask<Microsoft.Agents.Workflows.Execution.CallResult>
    >;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Provides a builder for configuring message type handlers for an <see cref="Executor"/>.
/// </summary>
/// <remarks>
/// Override the <see cref="Executor.ConfigureRoutes"/> method to customize the routing of messages to handlers.
/// </remarks>
public class RouteBuilder
{
    private readonly Dictionary<Type, MessageHandlerF> _typedHandlers = [];

    internal RouteBuilder AddHandler(Type messageType, MessageHandlerF handler, bool overwrite = false)
    {
        Throw.IfNull(messageType);
        Throw.IfNull(handler);

        // Overwrite must be false if the type is not registered. Overwrite must be true if the type is registered.
        if (this._typedHandlers.ContainsKey(messageType) == overwrite)
        {
            this._typedHandlers[messageType] = handler;
        }
        else if (overwrite)
        {
            // overwrite is true, but the type is not registered.
            throw new ArgumentException($"A handler for message type {messageType.FullName} has not yet been registered (overwrite = true).");
        }
        else if (!overwrite)
        {
            throw new ArgumentException($"A handler for message type {messageType.FullName} is already registered (overwrite = false).");
        }

        return this;
    }

    internal RouteBuilder AddHandler(Type type, Func<object, IWorkflowContext, ValueTask> handler, bool overwrite = false)
    {
        Throw.IfNull(handler);

        return this.AddHandler(type, WrappedHandlerAsync, overwrite);

        async ValueTask<CallResult> WrappedHandlerAsync(object msg, IWorkflowContext ctx)
        {
            await handler.Invoke(msg, ctx).ConfigureAwait(false);
            return CallResult.ReturnVoid();
        }
    }

    internal RouteBuilder AddHandler<TResult>(Type type, Func<object, IWorkflowContext, ValueTask<TResult>> handler, bool overwrite = false)
    {
        Throw.IfNull(handler);

        return this.AddHandler(type, WrappedHandlerAsync, overwrite);

        async ValueTask<CallResult> WrappedHandlerAsync(object msg, IWorkflowContext ctx)
        {
            TResult result = await handler.Invoke(msg, ctx).ConfigureAwait(false);
            return CallResult.ReturnResult(result);
        }
    }

    /// <summary>
    /// Registers a handler for messages of the specified input type in the workflow route.
    /// </summary>
    /// <remarks>If a handler for the specified input type already exists and <paramref name="overwrite"/> is
    /// <see langword="false"/>, the existing handler will not be replaced. Handlers are invoked asynchronously and are
    /// expected to complete their processing before the workflow continues.</remarks>
    /// <typeparam name="TInput"></typeparam>
    /// <param name="handler">A delegate that processes messages of type <typeparamref name="TInput"/> within the workflow context. The
    /// delegate is invoked for each incoming message of the specified type.</param>
    /// <param name="overwrite"><see langword="true"/> to replace any existing handler for the specified input type; otherwise, <see
    /// langword="false"/> to preserve the existing handler.</param>
    /// <returns>The current <see cref="RouteBuilder"/> instance, enabling fluent configuration of additional handlers or route
    /// options.</returns>
    public RouteBuilder AddHandler<TInput>(Action<TInput, IWorkflowContext> handler, bool overwrite = false)
    {
        Throw.IfNull(handler);

        return this.AddHandler(typeof(TInput), WrappedHandlerAsync, overwrite);

        async ValueTask<CallResult> WrappedHandlerAsync(object msg, IWorkflowContext ctx)
        {
            handler.Invoke((TInput)msg, ctx);
            return CallResult.ReturnVoid();
        }
    }

    /// <summary>
    /// Registers a handler for messages of the specified input type in the workflow route.
    /// </summary>
    /// <remarks>If a handler for the specified input type already exists and <paramref name="overwrite"/> is
    /// <see langword="false"/>, the existing handler will not be replaced. Handlers are invoked asynchronously and are
    /// expected to complete their processing before the workflow continues.</remarks>
    /// <typeparam name="TInput"></typeparam>
    /// <param name="handler">A delegate that processes messages of type <typeparamref name="TInput"/> within the workflow context. The
    /// delegate is invoked for each incoming message of the specified type.</param>
    /// <param name="overwrite"><see langword="true"/> to replace any existing handler for the specified input type; otherwise, <see
    /// langword="false"/> to preserve the existing handler.</param>
    /// <returns>The current <see cref="RouteBuilder"/> instance, enabling fluent configuration of additional handlers or route
    /// options.</returns>
    public RouteBuilder AddHandler<TInput>(Func<TInput, IWorkflowContext, ValueTask> handler, bool overwrite = false)
    {
        Throw.IfNull(handler);

        return this.AddHandler(typeof(TInput), WrappedHandlerAsync, overwrite);

        async ValueTask<CallResult> WrappedHandlerAsync(object msg, IWorkflowContext ctx)
        {
            await handler.Invoke((TInput)msg, ctx).ConfigureAwait(false);
            return CallResult.ReturnVoid();
        }
    }

    /// <summary>
    /// Registers a handler function for messages of the specified input type in the workflow route.
    /// </summary>
    /// <remarks>If a handler for the given input type already exists, setting <paramref name="overwrite"/> to
    /// <see langword="true"/> will replace the existing handler; otherwise, an exception may be thrown. The handler
    /// receives the input message and workflow context, and returns a result asynchronously.</remarks>
    /// <typeparam name="TInput">The type of input message the handler will process.</typeparam>
    /// <typeparam name="TResult">The type of result produced by the handler.</typeparam>
    /// <param name="handler">A function that processes messages of type <typeparamref name="TInput"/> within the workflow context and returns
    /// a <see cref="ValueTask{TResult}"/> representing the asynchronous result.</param>
    /// <param name="overwrite"><see langword="true"/> to replace any existing handler for the input type; otherwise, <see langword="false"/> to
    /// preserve existing handlers.</param>
    /// <returns>The current <see cref="RouteBuilder"/> instance, enabling fluent configuration of workflow routes.</returns>
    public RouteBuilder AddHandler<TInput, TResult>(Func<TInput, IWorkflowContext, TResult> handler, bool overwrite = false)
    {
        Throw.IfNull(handler);

        return this.AddHandler(typeof(TInput), WrappedHandlerAsync, overwrite);

        async ValueTask<CallResult> WrappedHandlerAsync(object msg, IWorkflowContext ctx)
        {
            TResult result = handler.Invoke((TInput)msg, ctx);
            return CallResult.ReturnResult(result);
        }
    }

    /// <summary>
    /// Registers a handler function for messages of the specified input type in the workflow route.
    /// </summary>
    /// <remarks>If a handler for the given input type already exists, setting <paramref name="overwrite"/> to
    /// <see langword="true"/> will replace the existing handler; otherwise, an exception may be thrown. The handler
    /// receives the input message and workflow context, and returns a result asynchronously.</remarks>
    /// <typeparam name="TInput">The type of input message the handler will process.</typeparam>
    /// <typeparam name="TResult">The type of result produced by the handler.</typeparam>
    /// <param name="handler">A function that processes messages of type <typeparamref name="TInput"/> within the workflow context and returns
    /// a <see cref="ValueTask{TResult}"/> representing the asynchronous result.</param>
    /// <param name="overwrite"><see langword="true"/> to replace any existing handler for the input type; otherwise, <see langword="false"/> to
    /// preserve existing handlers.</param>
    /// <returns>The current <see cref="RouteBuilder"/> instance, enabling fluent configuration of workflow routes.</returns>
    public RouteBuilder AddHandler<TInput, TResult>(Func<TInput, IWorkflowContext, ValueTask<TResult>> handler, bool overwrite = false)
    {
        Throw.IfNull(handler);

        return this.AddHandler(typeof(TInput), WrappedHandlerAsync, overwrite);

        async ValueTask<CallResult> WrappedHandlerAsync(object msg, IWorkflowContext ctx)
        {
            TResult result = await handler.Invoke((TInput)msg, ctx).ConfigureAwait(false);
            return CallResult.ReturnResult(result);
        }
    }

    internal MessageRouter Build() => new(this._typedHandlers);
}
