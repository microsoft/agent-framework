// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Hosting.Channels;

/// <summary>
/// Base type for items yielded by <see cref="ChannelContext.StreamAsync"/>.
/// Covers both normalized agent updates (<see cref="HostedStreamUpdate"/>) and protocol-specific
/// events (<see cref="HostedStreamEvent"/>) behind one stream type.
/// </summary>
/// <remarks>
/// <see cref="HostedStreamCompleted"/> is always the terminal item and carries the final
/// <see cref="HostedRunResult"/> for downstream bookkeeping (intended-targets envelope,
/// durable push scheduling).
/// </remarks>
public abstract class HostedStreamItem
{
    private protected HostedStreamItem() { }
}

/// <summary>Normalized agent stream update; lossless for messages, function calls, usage.</summary>
public sealed class HostedStreamUpdate : HostedStreamItem
{
    /// <summary>Gets the agent response update.</summary>
    public AgentResponseUpdate Update { get; }

    /// <summary>Initializes a new instance of <see cref="HostedStreamUpdate"/>.</summary>
    /// <param name="update">The agent response update.</param>
    public HostedStreamUpdate(AgentResponseUpdate update)
    {
        this.Update = update;
    }
}

/// <summary>Protocol-specific event the framework does not model (workflow events, AG-UI events).</summary>
public sealed class HostedStreamEvent : HostedStreamItem
{
    /// <summary>Gets the protocol-specific event.</summary>
    public object Event { get; }

    /// <summary>Initializes a new instance of <see cref="HostedStreamEvent"/>.</summary>
    /// <param name="event">The protocol-specific event.</param>
    public HostedStreamEvent(object @event)
    {
        this.Event = @event;
    }
}

/// <summary>Terminal item carrying the final result for post-stream bookkeeping.</summary>
public sealed class HostedStreamCompleted : HostedStreamItem
{
    /// <summary>Gets the final run result.</summary>
    public HostedRunResult Result { get; }

    /// <summary>Initializes a new instance of <see cref="HostedStreamCompleted"/>.</summary>
    /// <param name="result">The final run result.</param>
    public HostedStreamCompleted(HostedRunResult result)
    {
        this.Result = result;
    }
}
