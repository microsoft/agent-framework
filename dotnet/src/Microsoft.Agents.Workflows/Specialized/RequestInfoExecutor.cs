// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Execution;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Specialized;

internal sealed class RequestInfoExecutor : Executor
{
    private readonly Dictionary<string, ExternalRequest> _wrappedRequests = new();
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
            .AddCatchAll(this.HandleCatchAllAsync);

        if (this._allowWrapped)
        {
            routeBuilder = routeBuilder
                .AddHandler<ExternalRequest, ExternalRequest>(this.HandleAsync);
        }

        return routeBuilder
            // Handle incoming responses (as wrapped Response object)
            .AddHandler<ExternalResponse, ExternalResponse>(this.HandleAsync);
    }

    internal void AttachRequestSink(IExternalRequestSink requestSink) => this.RequestSink = Throw.IfNull(requestSink);

    public async ValueTask<ExternalRequest> HandleCatchAllAsync(PortableValue message, IWorkflowContext context)
    {
        Throw.IfNull(message);

        object? maybeRequest = message.AsType(this.Port.Request);
        if (maybeRequest != null)
        {
            Debug.Assert(this.Port.Request.IsAssignableFrom(maybeRequest.GetType()));

            ExternalRequest request = ExternalRequest.Create(this.Port, maybeRequest!);
            await this.RequestSink!.PostAsync(request).ConfigureAwait(false);
        }

        throw new InvalidOperationException($"Message type {message.TypeId} could not be interpreted as a value of Request Type {this.Port.Request}");
    }

    public async ValueTask<ExternalRequest> HandleAsync(ExternalRequest message, IWorkflowContext context)
    {
        Debug.Assert(this._allowWrapped);
        Throw.IfNull(message);

        if (!message.Data.IsType(this.Port.Request))
        {
            throw new InvalidOperationException($"Message type {message.Data.TypeId} could not be interpreted as a value of Request Type {this.Port.Request}");
        }

        if (!message.PortInfo.ResponseType.IsMatchPolymorphic(this.Port.Response))
        {
            throw new InvalidOperationException($"Response type {this.Port.Response} is not a valid response for original request, whose expected response is {message.PortInfo.ResponseType}");
        }

        ExternalRequest request = ExternalRequest.Create(this.Port, message);

        this._wrappedRequests.Add(request.RequestId, message);

        await this.RequestSink!.PostAsync(request).ConfigureAwait(false);

        return request;
    }

    public async ValueTask<ExternalRequest> HandleAsync(object message, IWorkflowContext context)
    {
        Throw.IfNull(message);
        Debug.Assert(this.Port.Request.IsAssignableFrom(message.GetType()));

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

        if (this._allowWrapped && this._wrappedRequests.TryGetValue(message.RequestId, out ExternalRequest? originalRequest))
        {
            await context.SendMessageAsync(originalRequest.RewrapResponse(message)).ConfigureAwait(false);
        }
        else
        {
            await context.SendMessageAsync(message).ConfigureAwait(false);
        }

        await context.SendMessageAsync(data).ConfigureAwait(false);

        return message;
    }
}
