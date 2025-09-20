// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Execution;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Specialized;

internal sealed class RequestInfoExecutor : Executor
{
    private InputPort Port { get; }
    private IExternalRequestSink? RequestSink { get; set; }

    private static ExecutorOptions DefaultOptions => new()
    {
        // We need to be able to return the ExternalRequest/Result objects so they can be bubbled up
        // through the event system, but we do not want to forward the Request message.
        AutoSendMessageHandlerResultObject = false
    };

    private readonly bool _allowWrapped;
    public RequestInfoExecutor(InputPort port, bool allowWrapped = true) : base(port.Id, DefaultOptions)
    {
        this.Port = port;

        this._allowWrapped = allowWrapped;
    }

    protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder)
    {
        routeBuilder = routeBuilder
            // Handle incoming requests (as raw request payloads)
            .AddHandler(this.Port.Request, this.HandleAsync)
            .AddHandler(typeof(object), this.HandleAsync);

        if (this._allowWrapped)
        {
            routeBuilder = routeBuilder
                .AddHandler<ExternalRequest, ExternalRequest>((request, context) => this.HandleAsync(request.Data, context));
        }

        return routeBuilder
            // Handle incoming responses (as wrapped Response object)
            .AddHandler<ExternalResponse, ExternalResponse>(this.HandleAsync);
    }

    internal void AttachRequestSink(IExternalRequestSink requestSink) => this.RequestSink = Throw.IfNull(requestSink);

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

        object data = message.DataAs(this.Port.Response) ??
            throw new InvalidOperationException(
                $"Message type {message.Data.TypeId} is not assignable to the response type {this.Port.Response.Name} of input port {this.Port.Id}.");

        await context.SendMessageAsync(message).ConfigureAwait(false);
        await context.SendMessageAsync(data).ConfigureAwait(false);

        return message;
    }
}
