// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Hosting.Channels;

/// <summary>
/// Collects the <see cref="ChannelContribution.OnStartup"/> / <see cref="ChannelContribution.OnShutdown"/>
/// callbacks gathered while <c>MapAgentFrameworkHost</c> invokes each channel's <c>Contribute</c>, so the
/// <see cref="ChannelLifecycleService"/> can invoke them at application start / stop. Singleton.
/// </summary>
internal sealed class ChannelLifecycleRegistry
{
    private readonly object _gate = new();
    private readonly List<Func<CancellationToken, ValueTask>> _startup = [];
    private readonly List<Func<CancellationToken, ValueTask>> _shutdown = [];

    public void Add(Func<CancellationToken, ValueTask>? onStartup, Func<CancellationToken, ValueTask>? onShutdown)
    {
        lock (this._gate)
        {
            if (onStartup is not null)
            {
                this._startup.Add(onStartup);
            }

            if (onShutdown is not null)
            {
                this._shutdown.Add(onShutdown);
            }
        }
    }

    public IReadOnlyList<Func<CancellationToken, ValueTask>> StartupCallbacks
    {
        get { lock (this._gate) { return [.. this._startup]; } }
    }

    public IReadOnlyList<Func<CancellationToken, ValueTask>> ShutdownCallbacks
    {
        get { lock (this._gate) { return [.. this._shutdown]; } }
    }
}
