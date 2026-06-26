// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Hosting.Channels;

/// <summary>
/// A discoverable command a channel exposes to its users (e.g. a Telegram <c>/reset</c> slash command or a
/// Discord application command). Channels emit these from <see cref="Channel.Contribute"/> as metadata for
/// native registration with the protocol, and dispatch a matched command by invoking <see cref="Handler"/>
/// with a <see cref="ChannelCommandContext"/>.
/// </summary>
public sealed class ChannelCommand
{
    /// <summary>Gets the command name without any leading sentinel (e.g. "reset" not "/reset").</summary>
    public string Name { get; }

    /// <summary>Gets the short description surfaced in the protocol's UI.</summary>
    public string Description { get; }

    /// <summary>Gets the handler invoked when the channel dispatches this command.</summary>
    public Func<ChannelCommandContext, ValueTask> Handler { get; }

    /// <summary>Initializes a new instance of <see cref="ChannelCommand"/>.</summary>
    /// <param name="name">The command name without any leading sentinel (e.g. "reset" not "/reset").</param>
    /// <param name="description">Short description surfaced in the protocol's UI.</param>
    /// <param name="handler">The handler invoked when the channel dispatches this command.</param>
    public ChannelCommand(string name, string description, Func<ChannelCommandContext, ValueTask> handler)
    {
        this.Name = Throw.IfNullOrEmpty(name);
        this.Description = Throw.IfNull(description);
        this.Handler = Throw.IfNull(handler);
    }
}
