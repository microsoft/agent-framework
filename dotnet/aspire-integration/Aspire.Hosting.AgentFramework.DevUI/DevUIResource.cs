// Copyright (c) Microsoft. All rights reserved.

using System.Net.Sockets;

namespace Aspire.Hosting.ApplicationModel;

/// <summary>
/// Represents a DevUI resource for testing AI agents in a distributed application.
/// </summary>
/// <remarks>
/// DevUI aggregates agents from multiple backend services and provides a unified
/// web interface for testing and debugging AI agents using the OpenAI Responses protocol.
/// The aggregator runs as an in-process reverse proxy within the AppHost, requiring no
/// external container image.
/// </remarks>
/// <param name="name">The name of the DevUI resource.</param>
public class DevUIResource(string name) : Resource(name), IResourceWithEndpoints, IResourceWithWaitSupport
{
    internal const string PrimaryEndpointName = "http";

    /// <summary>
    /// Initializes a new instance of the <see cref="DevUIResource"/> class with endpoint annotations.
    /// </summary>
    /// <param name="name">The name of the resource.</param>
    /// <param name="port">An optional fixed port. If <c>null</c>, a dynamic port is assigned.</param>
    internal DevUIResource(string name, int? port) : this(name)
    {
        this.Annotations.Add(new EndpointAnnotation(
            ProtocolType.Tcp,
            uriScheme: "http",
            name: PrimaryEndpointName,
            port: port,
            isProxied: false)
        {
            TargetHost = "localhost"
        });
    }

    /// <summary>
    /// Gets the primary HTTP endpoint for the DevUI web interface.
    /// </summary>
    public EndpointReference PrimaryEndpoint => field ??= new(this, PrimaryEndpointName);
}
