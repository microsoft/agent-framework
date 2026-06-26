// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Collections.Immutable;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Hosting.Channels;

/// <summary>
/// Session hint carried on a <see cref="ChannelRequest"/>. All fields nullable to support
/// caller-supplied (Responses, Invocations) and host-tracked (Telegram, Activity Protocol) channels.
/// </summary>
public sealed class ChannelSession
{
    /// <summary>
    /// Gets or sets the stable host lookup key for an <see cref="AgentSession"/>. Caller-supplied channels populate
    /// from the wire (<c>previous_response_id</c>, <c>conversation_id</c>); host-tracked channels
    /// leave this <see langword="null"/> and let the per-isolation-key alias decide.
    /// </summary>
    public string? Key { get; set; }

    /// <summary>Gets or sets the protocol-visible conversation or thread identifier when one exists.</summary>
    public string? ConversationId { get; set; }

    /// <summary>Gets or sets the opaque isolation boundary (user, tenant, chat, ...) using hosted-agent terminology.</summary>
    public string? IsolationKey { get; set; }

    /// <summary>Gets or sets the channel-defined attributes; not interpreted by the host.</summary>
    public IReadOnlyDictionary<string, object?> Attributes { get; set; } =
        ImmutableDictionary<string, object?>.Empty;

    /// <summary>Initializes a new instance of <see cref="ChannelSession"/>.</summary>
    public ChannelSession() { }

    /// <summary>Initializes a new instance of <see cref="ChannelSession"/> by copying an existing instance.</summary>
    /// <param name="other">The instance to copy.</param>
    public ChannelSession(ChannelSession other)
    {
        Throw.IfNull(other);
        this.Key = other.Key;
        this.ConversationId = other.ConversationId;
        this.IsolationKey = other.IsolationKey;
        this.Attributes = other.Attributes;
    }
}
