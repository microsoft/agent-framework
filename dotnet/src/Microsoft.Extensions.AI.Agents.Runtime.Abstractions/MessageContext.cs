﻿// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// Represents the context of a message being sent within the agent runtime.
/// </summary>
/// <remarks>
/// This includes metadata such as the sender, topic, ahd RPC status.
/// </remarks>
public sealed class MessageContext
{
    private string? _messageId;

    /// <summary>
    /// Gets or sets the unique identifier for this message.
    /// </summary>
    public string MessageId
    {
        get => this._messageId ?? Interlocked.CompareExchange(ref this._messageId, Guid.NewGuid().ToString(), null) ?? this._messageId;
        set
        {
            if (string.IsNullOrEmpty(value))
            {
                throw new ArgumentException("MessageId cannot be null or empty.", nameof(value));
            }

            this._messageId = value;
        }
    }

    /// <summary>
    /// Gets or sets the sender of the message.
    /// If <c>null</c>, the sender is unspecified.
    /// </summary>
    public ActorId? Sender { get; set; }

    /// <summary>
    /// Gets or sets the topic associated with the message.
    /// If <c>null</c>, the message is not tied to a specific topic.
    /// </summary>
    public TopicId? Topic { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether this message is part of an RPC (Remote Procedure Call).
    /// </summary>
    public bool IsRpc { get; set; }
}
