// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Hosting.Channels;

/// <summary>
/// Per-call context passed to <see cref="IChannelRunHook.OnRequestAsync"/>.
/// </summary>
public sealed class ChannelRunHookContext
{
    /// <summary>Gets the runner target: an <see cref="AIAgent"/>, a workflow, or a hosted-agent handle.</summary>
    public object Target { get; }

    /// <summary>Gets or sets the raw inbound payload as it arrived on the wire. Loosely typed.</summary>
    public object? ProtocolRequest { get; set; }

    /// <summary>Initializes a new instance of <see cref="ChannelRunHookContext"/>.</summary>
    /// <param name="target">The runner target: an <see cref="AIAgent"/>, a workflow, or a hosted-agent handle.</param>
    public ChannelRunHookContext(object target)
    {
        this.Target = Throw.IfNull(target);
    }
}
