// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Core;
using Microsoft.Agents.Workflows.Execution;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Specialized;

internal class RequestInputExecutor : Executor, IMessageHandler<object>, IMessageHandler<ExternalResponse>
{
    private InputPort Port { get; }
    private IExternalRequestSink? RequestSink { get; set; }

    public RequestInputExecutor(InputPort port) : base(port.Id)
    {
        this.Port = port;
    }

    internal void AttachRequestSink(IExternalRequestSink requestSink)
    {
        this.RequestSink = Throw.IfNull(requestSink);
    }

    public ValueTask HandleAsync(object message, IWorkflowContext context)
    {
        Throw.IfNull(message);

        return this.RequestSink!.PostAsync(ExternalRequest.Create(this.Port, message));
    }

    public ValueTask HandleAsync(ExternalResponse message, IWorkflowContext context)
    {
        Throw.IfNull(message);
        Throw.IfNull(message.Data);

        if (!this.Port.Response.IsAssignableFrom(message.Data.GetType()))
        {
            throw new InvalidOperationException(
                $"Message type {message.Data.GetType().Name} is not assignable to the response type {this.Port.Response.Name} of input port {this.Port.Id}.");
        }

        return context.SendMessageAsync(message.Data);
    }
}
