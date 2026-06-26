// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Hosting.Channels;

/// <summary>
/// Capability interface: rewrite the <see cref="ChannelRequest"/> after the channel produces its
/// default envelope and before the host calls the runner. The canonical adapter point for
/// workflow targets and prompt rewriting.
/// </summary>
public interface IChannelRunHook
{
    /// <summary>Return the (possibly rewritten) request.</summary>
    ValueTask<ChannelRequest> OnRequestAsync(
        ChannelRequest request,
        ChannelRunHookContext context,
        CancellationToken cancellationToken);
}
