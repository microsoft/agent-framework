// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting.Channels;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.Hosting;

/// <summary>
/// Extension methods on <see cref="IHostApplicationBuilder"/> for composing an
/// <see cref="AgentFrameworkHost"/> with channels.
/// </summary>
public static class HostApplicationBuilderHostingChannelsExtensions
{
    /// <summary>Adds an agent-framework host whose target is the supplied <see cref="AIAgent"/>.</summary>
    public static IAgentFrameworkHostBuilder AddAgentFrameworkHost(
        this IHostApplicationBuilder builder,
        AIAgent target,
        Action<AgentFrameworkHostOptions>? configure = null)
    {
        Throw.IfNull(builder);
        Throw.IfNull(target);
        return AddCore(builder, configure, services => services.TryAddSingleton<IHostedTargetRunner>(sp => new AIAgentRunner(target, sp.GetRequiredService<IHostStateStore>())));
    }

    /// <summary>Adds an agent-framework host whose target is the supplied <see cref="Workflow"/>.</summary>
    public static IAgentFrameworkHostBuilder AddAgentFrameworkHost(
        this IHostApplicationBuilder builder,
        Workflow target,
        Action<AgentFrameworkHostOptions>? configure = null)
    {
        Throw.IfNull(builder);
        Throw.IfNull(target);
        return AddCore(builder, configure, services => services.TryAddSingleton<IHostedTargetRunner>(sp => new WorkflowRunner(target, sp.GetRequiredService<IHostStateStore>())));
    }

    /// <summary>Adds an agent-framework host whose target is resolved from a factory (for alternative runners).</summary>
    public static IAgentFrameworkHostBuilder AddAgentFrameworkHost<TTarget>(
        this IHostApplicationBuilder builder,
        Func<IServiceProvider, TTarget> targetFactory,
        Action<AgentFrameworkHostOptions>? configure = null)
        where TTarget : class
    {
        Throw.IfNull(builder);
        Throw.IfNull(targetFactory);
        return AddCore(builder, configure, services => services.TryAddSingleton(targetFactory));
    }

    private static AgentFrameworkHostBuilder AddCore(
        IHostApplicationBuilder builder,
        Action<AgentFrameworkHostOptions>? configure,
        Action<IServiceCollection> registerTarget)
    {
        var options = new AgentFrameworkHostOptions();
        configure?.Invoke(options);

        var services = builder.Services;

        if (options.StatePaths is not null)
        {
            services.TryAddSingleton<IHostStateStore>(_ => new FileHostStateStore(options.StatePaths));
        }
        else
        {
            services.TryAddSingleton<IHostStateStore>(_ => new InMemoryHostStateStore());
        }

        services.TryAddSingleton<ChannelLifecycleRegistry>();
        services.AddHostedService<ChannelLifecycleService>();

        services.TryAddSingleton<IIsolationKeysAccessor, IsolationKeysAccessor>();

        registerTarget(services);

        services.TryAddSingleton(options);
        services.TryAddSingleton(sp => new AgentFrameworkHost(
            sp,
            sp.GetRequiredService<IHostedTargetRunner>(),
            sp.GetRequiredService<System.Collections.Generic.IReadOnlyList<Channel>>(),
            sp.GetRequiredService<IHostStateStore>(),
            sp.GetRequiredService<AgentFrameworkHostOptions>()));

        return new AgentFrameworkHostBuilder(services, options);
    }
}
