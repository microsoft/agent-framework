// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Hosting.Channels;

/// <summary>
/// Context passed to <see cref="IChannelResponseHook.OnResponseAsync"/>. Runs after target invocation and
/// before the originating channel serializes its response.
/// </summary>
public sealed class ChannelResponseContext
{
    /// <summary>Gets the originating request.</summary>
    public ChannelRequest Request { get; }

    /// <summary>Gets the originating channel name.</summary>
    public string ChannelName { get; }

    /// <summary>Initializes a new instance of <see cref="ChannelResponseContext"/>.</summary>
    /// <param name="request">The originating request.</param>
    /// <param name="channelName">The originating channel name.</param>
    public ChannelResponseContext(ChannelRequest request, string channelName)
    {
        this.Request = Throw.IfNull(request);
        this.ChannelName = Throw.IfNullOrEmpty(channelName);
    }
}
