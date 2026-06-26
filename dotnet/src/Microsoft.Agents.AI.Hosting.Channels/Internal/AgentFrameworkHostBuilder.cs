// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Hosting.Channels;

internal sealed class AgentFrameworkHostBuilder : IAgentFrameworkHostBuilder
{
    private readonly List<Channel> _channels = [];

    public AgentFrameworkHostBuilder(IServiceCollection services, AgentFrameworkHostOptions options)
    {
        this.Services = Throw.IfNull(services);
        this.Options = Throw.IfNull(options);
        services.AddSingleton<IReadOnlyList<Channel>>(_ => this._channels);
    }

    public IServiceCollection Services { get; }

    public AgentFrameworkHostOptions Options { get; }

    public IAgentFrameworkHostBuilder AddChannel(Channel channel)
    {
        Throw.IfNull(channel);
        channel.ConfigureServices(this.Services);
        this._channels.Add(channel);
        return this;
    }

    public IAgentFrameworkHostBuilder AddChannel<TChannel>(Func<IServiceProvider, TChannel> factory) where TChannel : Channel
    {
        Throw.IfNull(factory);

        using var probeProvider = this.Services.BuildServiceProvider();
        var probe = factory(probeProvider);
        probe.ConfigureServices(this.Services);

        this.Services.AddSingleton(factory);
        this.Services.AddSingleton<Channel>(sp => sp.GetRequiredService<TChannel>());
        this._channels.Add(probe);
        return this;
    }

    public IAgentFrameworkHostBuilder UseHostStateStore<[DynamicallyAccessedMembers(DynamicallyAccessedMemberTypes.PublicConstructors)] TStore>()
        where TStore : class, IHostStateStore
    {
        this.Services.Replace(ServiceDescriptor.Singleton<IHostStateStore, TStore>());
        return this;
    }
}
