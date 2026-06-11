// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Reflection;

namespace Microsoft.Agents.AI.Workflows.Reflection;

/// <summary>
/// A component that processes messages in a <see cref="Workflow"/>.
/// </summary>
/// <typeparam name="TExecutor">The actual type of the <see cref="ReflectingExecutor{TExecutor}"/>.
/// This is used to reflectively discover handlers for messages without violating ILTrim requirements.
/// </typeparam>
/// <remarks>
/// This type is obsolete. Use the <see cref="MessageHandlerAttribute"/> on methods in a partial class
/// deriving from <see cref="Executor"/> instead.
/// </remarks>
[Obsolete("Use [MessageHandler] attribute on methods in a partial class deriving from Executor. " +
          "This type will be removed in a future version.")]
public class ReflectingExecutor<
    [DynamicallyAccessedMembers(
        ReflectionDemands.RuntimeInterfaceDiscoveryAndInvocation)
    ] TExecutor
    > : Executor where TExecutor : ReflectingExecutor<TExecutor>
{
    /// <inheritdoc cref="Executor(string, ExecutorOptions?, bool)"/>
    protected ReflectingExecutor(string id, ExecutorOptions? options = null, bool declareCrossRunShareable = false)
        : base(id, options, declareCrossRunShareable)
    {
    }

    /// <inheritdoc/>
    protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
    {
        protocolBuilder.SendsMessageTypes(typeof(TExecutor).GetCustomAttributes<SendsMessageAttribute>(inherit: true)
                                                           .Select(attr => attr.Type))
                       .YieldsOutputTypes(typeof(TExecutor).GetCustomAttributes<YieldsOutputAttribute>(inherit: true)
                                                           .Select(attr => attr.Type));

        List<MessageHandlerInfo> messageHandlers = typeof(TExecutor).GetHandlerInfos().ToList();
        foreach (MessageHandlerInfo handlerInfo in messageHandlers)
        {
            protocolBuilder.RouteBuilder.AddHandlerInternal(handlerInfo.InType, handlerInfo.Bind(this, checkType: true), handlerInfo.OutType);

            if (handlerInfo.OutType != null)
            {
                if (this.Options.AutoSendMessageHandlerResultObject)
                {
                    protocolBuilder.SendsMessageType(handlerInfo.OutType);
                }

                if (this.Options.AutoYieldOutputHandlerResultObject)
                {
                    protocolBuilder.YieldsOutputType(handlerInfo.OutType);
                }
            }
        }

        if (messageHandlers.Count > 0)
        {
            var handlerAnnotatedTypes =
                messageHandlers.Select(mhi => (SendTypes: mhi.HandlerInfo.GetCustomAttributes<SendsMessageAttribute>().Select(attr => attr.Type),
                                               YieldTypes: mhi.HandlerInfo.GetCustomAttributes<YieldsOutputAttribute>().Select(attr => attr.Type)))
                               .Aggregate((accumulate, next) => (accumulate.SendTypes == null ? next.SendTypes : accumulate.SendTypes.Concat(next.SendTypes),
                                                                 accumulate.YieldTypes == null ? next.YieldTypes : accumulate.YieldTypes.Concat(next.YieldTypes)));

            protocolBuilder.SendsMessageTypes(handlerAnnotatedTypes.SendTypes)
                           .YieldsOutputTypes(handlerAnnotatedTypes.YieldTypes);
        }

        return protocolBuilder;
    }
}
