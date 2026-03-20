// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

internal sealed class DynamicPortsExecutor<TRequest, TResponse>(string id, params IEnumerable<string> ports) : Executor(id)
{
    public Dictionary<string, PortBinding> PortBindings { get; } = new();

    public ConcurrentDictionary<string, ConcurrentQueue<TResponse>> ReceivedResponses { get; } = new();

    protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
    {
        return protocolBuilder.ConfigureRoutes(ConfigureRoutes);

        void ConfigureRoutes(RouteBuilder routeBuilder)
        {
            foreach (string portId in ports)
            {
                routeBuilder = routeBuilder
                    .AddPortHandler<TRequest, TResponse>(portId,
                        (response, context, cancellationToken) =>
                        {
                            this.ReceivedResponses.GetOrAdd(portId, _ => new()).Enqueue(response);
                            return default;
                        }, out PortBinding? binding);

                this.PortBindings[portId] = binding;
            }
        }
    }

    public ValueTask PostRequestAsync(string portId, TRequest request, TestRunContext testContext, string? requestId = null)
    {
        PortBinding binding = this.PortBindings[portId];
        return binding.Sink.PostAsync(ExternalRequest.Create(binding.Port, request, requestId));
    }
}
