// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Hosting.Channels;

/// <summary>
/// Capability interface: receive a per-destination clone of the run result and return a possibly
/// rewritten replacement. Hooks rebind via <see cref="HostedRunResult{TResult}.Replace{TNew}"/>
/// rather than mutating in place.
/// </summary>
public interface IChannelResponseHook
{
    /// <summary>Return the (possibly rewritten) result for this destination.</summary>
    ValueTask<HostedRunResult> OnResponseAsync(
        HostedRunResult result,
        ChannelResponseContext context,
        CancellationToken cancellationToken);
}
