// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Hosting.Channels;

/// <summary>
/// Pluggable adapter that drives the actual target (AI agent, workflow, Foundry hosted agent).
/// Channels never branch on target type; they go through this seam.
/// </summary>
public interface IHostedTargetRunner
{
    /// <summary>Run the target.</summary>
    ValueTask<HostedRunResult> RunAsync(ChannelRequest request, CancellationToken cancellationToken);

    /// <summary>Stream the target's response.</summary>
    IAsyncEnumerable<HostedStreamItem> StreamAsync(ChannelRequest request, CancellationToken cancellationToken);
}
