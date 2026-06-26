// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Hosting.Channels;

/// <summary>
/// Context passed to a <see cref="ChannelCommand.Handler"/> when a channel dispatches a recognized command.
/// Carries the originating request and a protocol-native <see cref="Reply"/> callback the handler uses to
/// respond.
/// </summary>
public sealed class ChannelCommandContext
{
    /// <summary>Gets the originating channel request.</summary>
    public ChannelRequest Request { get; }

    /// <summary>Gets the channel-supplied callback the handler invokes to send a reply.</summary>
    public Func<string, ValueTask> Reply { get; }

    /// <summary>Initializes a new instance of <see cref="ChannelCommandContext"/>.</summary>
    /// <param name="request">The originating channel request.</param>
    /// <param name="reply">The channel-supplied callback the handler invokes to send a reply.</param>
    public ChannelCommandContext(ChannelRequest request, Func<string, ValueTask> reply)
    {
        this.Request = Throw.IfNull(request);
        this.Reply = Throw.IfNull(reply);
    }
}
