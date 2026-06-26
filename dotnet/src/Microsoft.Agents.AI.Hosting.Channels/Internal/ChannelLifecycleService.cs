// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Hosting;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Hosting.Channels;

/// <summary>
/// Invokes channel <see cref="ChannelContribution.OnStartup"/> callbacks when the application starts and
/// <see cref="ChannelContribution.OnShutdown"/> callbacks (in reverse registration order) when it stops.
/// Registered by <c>AddAgentFrameworkHost</c>; reads callbacks recorded by <c>MapAgentFrameworkHost</c>.
/// </summary>
internal sealed class ChannelLifecycleService : IHostedService
{
    private readonly ChannelLifecycleRegistry _registry;

    public ChannelLifecycleService(ChannelLifecycleRegistry registry)
    {
        this._registry = Throw.IfNull(registry);
    }

    public async Task StartAsync(CancellationToken cancellationToken)
    {
        foreach (var callback in this._registry.StartupCallbacks)
        {
            await callback(cancellationToken).ConfigureAwait(false);
        }
    }

    public async Task StopAsync(CancellationToken cancellationToken)
    {
        var callbacks = this._registry.ShutdownCallbacks;
        for (var i = callbacks.Count - 1; i >= 0; i--)
        {
            await callbacks[i](cancellationToken).ConfigureAwait(false);
        }
    }
}
