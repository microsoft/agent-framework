// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Collections.Immutable;

namespace Microsoft.Agents.AI.Hosting.Channels;

/// <summary>
/// Channel-native user identity observed on a <see cref="ChannelRequest"/>.
/// </summary>
public sealed class ChannelIdentity
{
    /// <summary>Gets the originating channel name (matches <see cref="Channel.Name"/>).</summary>
    public string Channel { get; }

    /// <summary>Gets the channel-native USER identifier (never the chat or conversation id).</summary>
    public string NativeId { get; }

    /// <summary>
    /// Gets or sets the channel-defined attributes attached to this identity (e.g. display name, language).
    /// </summary>
    public IReadOnlyDictionary<string, string> Attributes { get; set; } =
        ImmutableDictionary<string, string>.Empty;

    /// <summary>Initializes a new instance of <see cref="ChannelIdentity"/>.</summary>
    /// <param name="channel">The originating channel name (matches <see cref="Channel.Name"/>).</param>
    /// <param name="nativeId">The channel-native USER identifier (never the chat or conversation id).</param>
    public ChannelIdentity(string channel, string nativeId)
    {
        this.Channel = channel;
        this.NativeId = nativeId;
    }
}
