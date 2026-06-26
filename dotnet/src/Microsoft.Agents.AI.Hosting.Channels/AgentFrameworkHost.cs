// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Hosting.Channels;

/// <summary>
/// The channel-neutral host composed by <c>AddAgentFrameworkHost(...)</c> and surfaced via DI. Owns target
/// invocation, the channels collection, the host state store, and <see cref="ResetSessionAsync"/>. v1 has no
/// authorization pipeline, response routing, or background delivery (those are ADR-0028).
/// </summary>
public sealed class AgentFrameworkHost
{
    internal AgentFrameworkHost(
        IServiceProvider services,
        IHostedTargetRunner targetRunner,
        IReadOnlyList<Channel> channels,
        IHostStateStore stateStore,
        AgentFrameworkHostOptions options)
    {
        this.Services = Throw.IfNull(services);
        this.TargetRunner = Throw.IfNull(targetRunner);
        this.Channels = Throw.IfNull(channels);
        this.StateStore = Throw.IfNull(stateStore);
        this.Options = Throw.IfNull(options);
    }

    /// <summary>Application service provider.</summary>
    public IServiceProvider Services { get; }

    /// <summary>Registered channels in registration order.</summary>
    public IReadOnlyList<Channel> Channels { get; }

    /// <summary>The configured target runner.</summary>
    public IHostedTargetRunner TargetRunner { get; }

    /// <summary>The shared host state store.</summary>
    public IHostStateStore StateStore { get; }

    /// <summary>Composition-time options.</summary>
    public AgentFrameworkHostOptions Options { get; }

    /// <summary>Run the target with the given request.</summary>
    public ValueTask<HostedRunResult> RunAsync(ChannelRequest request, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(request);
        return this.TargetRunner.RunAsync(request, cancellationToken);
    }

    /// <summary>Stream the target's response.</summary>
    public IAsyncEnumerable<HostedStreamItem> StreamAsync(ChannelRequest request, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(request);
        return this.TargetRunner.StreamAsync(request, cancellationToken);
    }

    /// <summary>Rotate the active session alias for an isolation key (host-tracked channels' <c>/new</c>).</summary>
    public ValueTask ResetSessionAsync(string isolationKey, CancellationToken cancellationToken = default)
        => this.StateStore.RotateSessionAliasAsync(isolationKey, cancellationToken);
}
