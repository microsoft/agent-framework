// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.Hosting.Channels;

/// <summary>
/// Base type for hosting channels. Authors derive from this to expose an inbound surface (HTTP routes,
/// long-poll loops, ...) and optionally mix in <see cref="IChannelRunHook"/> / <see cref="IChannelResponseHook"/> /
/// <see cref="IChannelStreamTransformHook"/>.
/// </summary>
/// <remarks>
/// Two-phase lifecycle: <see cref="ConfigureServices"/> runs at <c>AddXxxChannel</c> time (pre-Build);
/// <see cref="Contribute"/> runs at <c>MapAgentFrameworkHost</c> time (post-Build).
/// </remarks>
public abstract class Channel
{
    /// <summary>Stable channel name. Matches <see cref="ChannelRequest.Channel"/> / <see cref="ChannelIdentity.Channel"/>.</summary>
    public abstract string Name { get; }

    /// <summary>
    /// Mount root for the channel's routes. The host wraps <see cref="ChannelContribution.Routes"/> in
    /// <c>endpoints.MapGroup(Path)</c>. Empty mounts at the host root.
    /// </summary>
    public virtual string Path => string.Empty;

    /// <summary>Registers DI services the channel needs. Runs pre-Build.</summary>
    public virtual void ConfigureServices(IServiceCollection services)
    {
    }

    /// <summary>Returns the channel's contribution (routes, commands, lifecycle hooks, endpoint filters). Runs post-Build.</summary>
    public abstract ChannelContribution Contribute(ChannelContext context);
}
