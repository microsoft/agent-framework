// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using Microsoft.Agents.AI.Workflows.Execution;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

internal static class MemberAttributeExtensions
{
    public static (IEnumerable<Type> Sent, IEnumerable<Type> Yielded) GetAttributeTypes(this MemberInfo memberInfo)
    {
        IEnumerable<SendsMessageAttribute> sendsMessageAttrs = memberInfo.GetCustomAttributes<SendsMessageAttribute>();
        IEnumerable<YieldsOutputAttribute> yieldsOutputAttrs = memberInfo.GetCustomAttributes<YieldsOutputAttribute>();
        // TODO: Should we include [MessageHandler]?

        return (Sent: sendsMessageAttrs.Select(attr => attr.Type), Yielded: yieldsOutputAttrs.Select(attr => attr.Type));
    }
}

/// <summary>
/// .
/// </summary>
public sealed class ProtocolBuilder
{
    private readonly HashSet<Type> _sendTypes = [];
    private readonly HashSet<Type> _yieldTypes = [];

    internal ProtocolBuilder(DelayedExternalRequestContext delayRequestContext)
    {
        this.RouteBuilder = new RouteBuilder(delayRequestContext);
    }

    /// <summary>
    /// Adds types registered in <see cref="SendsMessageAttribute"/> or <see cref="YieldsOutputAttribute"/>
    /// on the target <see cref="Delegate"/>. This can be used to implement delegate-based request handling akin
    /// to what is provided by <see cref="Executor{TInput}"/> or <see cref="Executor{TIn,TOut}"/>.
    /// </summary>
    /// <param name="delegate">The delegate to be registered.</param>
    /// <returns></returns>
    public ProtocolBuilder AddDelegateAttributeTypes(Delegate @delegate)
        => this.AddMethodAttributeTypes(Throw.IfNull(@delegate).Method);

    /// <summary>
    /// Adds types registered in <see cref="SendsMessageAttribute"/> or <see cref="YieldsOutputAttribute"/>
    /// on the target <see cref="MethodInfo"/>. This can be used to implement delegate-based request handling akin
    /// to what is provided by <see cref="Executor{TInput}"/> or <see cref="Executor{TIn,TOut}"/>.
    /// </summary>
    /// <param name="method">The method to be registered.</param>
    /// <returns></returns>
    public ProtocolBuilder AddMethodAttributeTypes(MethodInfo method)
    {
        (IEnumerable<Type> sentTypes, IEnumerable<Type> yieldTypes) = method.GetAttributeTypes();

        this._sendTypes.UnionWith(sentTypes);
        this._yieldTypes.UnionWith(yieldTypes);

        return method.DeclaringType != null ? this.AddClassAttributeTypes(method.DeclaringType)
                                            : this;
    }

    /// <summary>
    /// Adds types registered in <see cref="SendsMessageAttribute"/> or <see cref="YieldsOutputAttribute"/>
    /// on the target <see cref="Type"/>. This can be used to implement delegate-based request handling akin
    /// to what is provided by <see cref="Executor{TInput}"/> or <see cref="Executor{TIn,TOut}"/>.
    /// </summary>
    /// <param name="executorType">The type to be registered.</param>
    /// <returns></returns>
    public ProtocolBuilder AddClassAttributeTypes(Type executorType)
    {
        (IEnumerable<Type> sentTypes, IEnumerable<Type> yieldTypes) = executorType.GetAttributeTypes();

        this._sendTypes.UnionWith(sentTypes);
        this._yieldTypes.UnionWith(yieldTypes);

        return this;
    }

    /// <summary>
    /// Adds the specified type to the set of declared "sent" message types for the protocol. Objects of these types will be allowed to be
    /// sent through the Executor's outgoing edges, via <see cref="IWorkflowContext.SendMessageAsync"/>.
    /// </summary>
    /// <typeparam name="TMessage">The type to be declared.</typeparam>
    /// <returns></returns>
    public ProtocolBuilder SendsMessage<TMessage>() where TMessage : notnull => this.SendsMessageTypes([typeof(TMessage)]);

    /// <summary>
    /// Adds the specified type to the set of declared "sent" messagetypes for the protocol. Objects of these types will be allowed to be
    /// sent through the Executor's outgoing edges, via <see cref="IWorkflowContext.SendMessageAsync"/>.
    /// </summary>
    /// <param name="messageType">The type to be declared.</param>
    /// <returns></returns>
    public ProtocolBuilder SendsMessageType(Type messageType) => this.SendsMessageTypes([messageType]);

    /// <summary>
    /// Adds the specified types to the set of declared "sent" message types for the protocol. Objects of these types will be allowed to be
    /// sent through the Executor's outgoing edges, via <see cref="IWorkflowContext.SendMessageAsync"/>.
    /// </summary>
    /// <param name="messageTypes">A set of types to be declared.</param>
    /// <returns></returns>
    public ProtocolBuilder SendsMessageTypes(IEnumerable<Type> messageTypes)
    {
        Throw.IfNull(messageTypes);
        this._sendTypes.UnionWith(messageTypes);
        return this;
    }

    /// <summary>
    /// Adds the specified output type to the set of declared "yielded" output types for the protocol. Objects of this type will be
    /// allowed to be output from the executor through the <see cref="WorkflowOutputEvent"/>, via <see cref="IWorkflowContext.YieldOutputAsync"/>.
    /// </summary>
    /// <typeparam name="TOutput">The type to be declared.</typeparam>
    /// <returns></returns>
    public ProtocolBuilder YieldsOutput<TOutput>() where TOutput : notnull => this.YieldsOutputTypes([typeof(TOutput)]);

    /// <summary>
    /// Adds the specified output type to the set of declared "yielded" output types for the protocol. Objects of this type will be
    /// allowed to be output from the executor through the <see cref="WorkflowOutputEvent"/>, via <see cref="IWorkflowContext.YieldOutputAsync"/>.
    /// </summary>
    /// <param name="outputType">The type to be declared.</param>
    /// <returns></returns>
    public ProtocolBuilder YieldsOutputType(Type outputType) => this.YieldsOutputTypes([outputType]);

    /// <summary>
    /// Adds the specified types to the set of declared "yielded" output types for the protocol. Objects of these types will be allowed to be
    /// output from the executor through the <see cref="WorkflowOutputEvent"/>, via <see cref="IWorkflowContext.YieldOutputAsync"/>.
    /// </summary>
    /// <param name="yieldedTypes">A set of types to be declared.</param>
    /// <returns></returns>
    public ProtocolBuilder YieldsOutputTypes(IEnumerable<Type> yieldedTypes)
    {
        Throw.IfNull(yieldedTypes);
        this._yieldTypes.UnionWith(yieldedTypes);
        return this;
    }

    /// <summary>
    /// Gets a route builder to configure message handlers.
    /// </summary>
    public RouteBuilder RouteBuilder { get; }

    /// <summary>
    /// Fluently configures message handlers.
    /// </summary>
    /// <param name="configureAction">The handler configuration callback.</param>
    /// <returns></returns>
    public ProtocolBuilder ConfigureRoutes(Action<RouteBuilder> configureAction)
    {
        configureAction(this.RouteBuilder);
        return this;
    }

    internal ExecutorProtocol Build(ExecutorOptions options)
    {
        MessageRouter router = this.RouteBuilder.Build();

        HashSet<Type> sendTypes = new(this._sendTypes);
        if (options.AutoSendMessageHandlerResultObject)
        {
            sendTypes.UnionWith(router.DefaultOutputTypes);
        }

        HashSet<Type> yieldTypes = new(this._yieldTypes);
        if (options.AutoYieldOutputHandlerResultObject)
        {
            yieldTypes.UnionWith(router.DefaultOutputTypes);
        }

        return new(router, sendTypes, yieldTypes);
    }
}
