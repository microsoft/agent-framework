// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Execution;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Specialized;

internal class RequestInputExecutor : Executor
{
    private InputPort Port { get; }
    private IExternalRequestSink? RequestSink { get; set; }

    public RequestInputExecutor(InputPort port) : base(port.Id)
    {
        this.Port = port;
    }

    protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder)
    {
        return routeBuilder
                  // Handle incoming requests (as raw request payloads)
                  .AddHandler(this.Port.Request, this.HandleAsync)
                  .AddHandler(typeof(object), this.HandleAsync)
                  // Handle incoming responses (as wrapped Response object)
                  .AddHandler<ExternalResponse, ExternalResponse>(this.HandleAsync);
    }

    internal void AttachRequestSink(IExternalRequestSink requestSink)
    {
        this.RequestSink = Throw.IfNull(requestSink);
    }

    public async ValueTask<ExternalRequest> HandleAsync(object message, IWorkflowContext context)
    {
        Throw.IfNull(message);

        ExternalRequest request = ExternalRequest.Create(this.Port, message);
        await this.RequestSink!.PostAsync(request).ConfigureAwait(false);

        return request;
    }

    public async ValueTask<ExternalResponse> HandleAsync(ExternalResponse message, IWorkflowContext context)
    {
        Throw.IfNull(message);
        Throw.IfNull(message.Data);

        if (!this.Port.Response.IsAssignableFrom(message.Data.GetType()))
        {
            throw new InvalidOperationException(
                $"Message type {message.Data.GetType().Name} is not assignable to the response type {this.Port.Response.Name} of input port {this.Port.Id}.");
        }

        await context.SendMessageAsync(message.Data).ConfigureAwait(false);

        return message;
    }
}
