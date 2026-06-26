// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;

namespace Microsoft.Agents.AI.Hosting.Channels;

/// <summary>
/// Capability interface: rewrite the upstream agent-update stream before it is projected onto
/// the channel wire. Hooks may filter, debounce, or annotate updates.
/// </summary>
public interface IChannelStreamTransformHook
{
    /// <summary>Wrap the upstream stream with the transform.</summary>
    IAsyncEnumerable<AgentResponseUpdate> TransformAsync(
        IAsyncEnumerable<AgentResponseUpdate> upstream,
        CancellationToken cancellationToken);
}
