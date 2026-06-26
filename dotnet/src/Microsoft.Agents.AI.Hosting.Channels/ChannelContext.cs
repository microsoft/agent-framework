// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Hosting.Channels;

/// <summary>
/// Handed to <see cref="Channel.Contribute"/>. Exposes the host's run / stream surface plus the host and
/// its state store. The host owns construction; channels consume it (they never create or derive from it),
/// so this is a sealed concrete type rather than an interface.
/// </summary>
public sealed class ChannelContext
{
    internal ChannelContext(IServiceProvider services, AgentFrameworkHost host)
    {
        this.Services = Throw.IfNull(services);
        this.Host = Throw.IfNull(host);
    }

    /// <summary>Gets the application service provider.</summary>
    public IServiceProvider Services { get; }

    /// <summary>Gets the host this channel was added to.</summary>
    public AgentFrameworkHost Host { get; }

    /// <summary>Gets the host state store.</summary>
    public IHostStateStore StateStore => this.Host.StateStore;

    /// <summary>Runs the host target and returns the (non-streaming) result.</summary>
    public ValueTask<HostedRunResult> RunAsync(ChannelRequest request, CancellationToken cancellationToken = default)
        => this.Host.RunAsync(request, cancellationToken);

    /// <summary>Streams the host target's response as <see cref="HostedStreamItem"/> envelopes.</summary>
    public IAsyncEnumerable<HostedStreamItem> StreamAsync(ChannelRequest request, CancellationToken cancellationToken = default)
        => this.Host.StreamAsync(request, cancellationToken);
}
