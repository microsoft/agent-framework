// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Collections.Immutable;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Hosting.Channels;

/// <summary>
/// Channel-neutral request envelope handed to <see cref="ChannelContext.RunAsync"/> /
/// <see cref="ChannelContext.StreamAsync"/>. Channels build this from their wire format.
/// </summary>
public sealed class ChannelRequest
{
    /// <summary>Gets the originating channel name (matches <see cref="Channel.Name"/>).</summary>
    public string Channel { get; }

    /// <summary>Gets the operation kind: "message.create", "command.invoke", ...</summary>
    public string Operation { get; }

    /// <summary>Gets or sets the target input: string, <see cref="ChatMessage"/>, <see cref="ChatMessage"/> sequence, or workflow input.</summary>
    public object Input { get; set; }

    /// <summary>Gets or sets the session hint. <see langword="null"/> for ephemeral requests.</summary>
    public ChannelSession? Session { get; set; }

    /// <summary>Gets or sets the channel-native user identity. Request metadata only; not a linking, authorization, or delivery key.</summary>
    public ChannelIdentity? Identity { get; set; }

    /// <summary>Gets or sets the protocol-visible conversation / thread id, when distinct from <see cref="ChannelIdentity.NativeId"/>.</summary>
    public string? ConversationId { get; set; }

    /// <summary>Gets or sets the caller-derived chat options forwarded onto the runner's <see cref="ChatOptions"/>.</summary>
    public ChatOptions? Options { get; set; }

    /// <summary>Gets or sets how the host resolves session continuity for this request.</summary>
    public SessionMode SessionMode { get; set; } = SessionMode.Auto;

    /// <summary>Gets or sets the protocol-level metadata for telemetry. The host never reads this.</summary>
    public IReadOnlyDictionary<string, object?> Metadata { get; set; } = ImmutableDictionary<string, object?>.Empty;

    /// <summary>
    /// Gets or sets the channel-specific structured values surfaced to the run hook. Reserved key for workflow targets:
    /// <c>"workflow.checkpoint_id"</c> (caller-supplied checkpoint resume).
    /// </summary>
    public IReadOnlyDictionary<string, object?> Attributes { get; set; } = ImmutableDictionary<string, object?>.Empty;

    /// <summary>Gets or sets a value indicating whether the channel is calling <see cref="ChannelContext.StreamAsync"/> rather than <see cref="ChannelContext.RunAsync"/>.</summary>
    public bool Stream { get; set; }

    /// <summary>Initializes a new instance of <see cref="ChannelRequest"/>.</summary>
    /// <param name="channel">Originating channel name (matches <see cref="Channel.Name"/>).</param>
    /// <param name="operation">Operation kind: "message.create", "command.invoke", ...</param>
    /// <param name="input">Target input: string, <see cref="ChatMessage"/>, <see cref="ChatMessage"/> sequence, or workflow input.</param>
    public ChannelRequest(string channel, string operation, object input)
    {
        this.Channel = Throw.IfNullOrEmpty(channel);
        this.Operation = Throw.IfNullOrEmpty(operation);
        this.Input = Throw.IfNull(input);
    }

    /// <summary>Initializes a new instance of <see cref="ChannelRequest"/> by copying an existing instance.</summary>
    /// <param name="other">The instance to copy.</param>
    public ChannelRequest(ChannelRequest other)
    {
        Throw.IfNull(other);
        this.Channel = other.Channel;
        this.Operation = other.Operation;
        this.Input = other.Input;
        this.Session = other.Session;
        this.Identity = other.Identity;
        this.ConversationId = other.ConversationId;
        this.Options = other.Options;
        this.SessionMode = other.SessionMode;
        this.Metadata = other.Metadata;
        this.Attributes = other.Attributes;
        this.Stream = other.Stream;
    }
}
