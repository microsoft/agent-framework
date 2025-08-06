// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

using MessageHandlerF =
    System.Func<
        object, // message
        Microsoft.Agents.Workflows.Core.IWorkflowContext, // context
        System.Threading.Tasks.ValueTask<Microsoft.Agents.Workflows.Core.CallResult>
    >;

namespace Microsoft.Agents.Workflows.Core;

/// <summary>
/// .
/// </summary>
public class RouteBuilder
{
    private readonly Dictionary<Type, MessageHandlerF> _typedHandlers = new();

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

    /// <summary>
    /// .
    /// </summary>
    /// <typeparam name="TInput"></typeparam>
    /// <param name="handler"></param>
    /// <param name="overwrite"></param>
    /// <returns></returns>
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
    /// .
    /// </summary>
    /// <typeparam name="TInput"></typeparam>
    /// <typeparam name="TResult"></typeparam>
    /// <param name="handler"></param>
    /// <param name="overwrite"></param>
    /// <returns></returns>
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

    internal MessageRouter Build()
    {
        return new MessageRouter(this._typedHandlers);
    }
}
