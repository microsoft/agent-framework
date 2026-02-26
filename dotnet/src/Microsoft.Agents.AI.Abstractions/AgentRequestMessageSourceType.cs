// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents the source of an agent request message.
/// </summary>
/// <remarks>
/// Input messages for a specific agent run can originate from various sources.
/// This type helps to identify whether a message came from outside the agent pipeline,
/// whether it was produced by middleware, or came from chat history.
/// </remarks>
public readonly struct AgentRequestMessageSourceType : IEquatable<AgentRequestMessageSourceType>
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentRequestMessageSourceType"/> struct.
    /// </summary>
    /// <param name="value">The string value representing the source of the agent request message.</param>
    public AgentRequestMessageSourceType(string value) => this.Value = Throw.IfNullOrWhitespace(value);

    /// <summary>
    /// Get the string value representing the source of the agent request message.
    /// </summary>
    public string Value { get { return field ?? External.Value; } }

    /// <summary>
    /// The message came from outside the agent pipeline (e.g., user input).
    /// </summary>
    public static AgentRequestMessageSourceType External { get; } = new AgentRequestMessageSourceType(nameof(External));

    /// <summary>
    /// The message was produced by middleware.
    /// </summary>
    public static AgentRequestMessageSourceType AIContextProvider { get; } = new AgentRequestMessageSourceType(nameof(AIContextProvider));

    /// <summary>
    /// The message came from chat history.
    /// </summary>
    public static AgentRequestMessageSourceType ChatHistory { get; } = new AgentRequestMessageSourceType(nameof(ChatHistory));

    /// <summary>
    /// Determines whether this instance and another specified <see cref="AgentRequestMessageSourceType"/> object have the same value.
    /// </summary>
    /// <param name="other">The <see cref="AgentRequestMessageSourceType"/> to compare to this instance.</param>
    /// <returns><see langword="true"/> if the value of the <paramref name="other"/> parameter is the same as the value of this instance; otherwise, <see langword="false"/>.</returns>
    public bool Equals(AgentRequestMessageSourceType other)
    {
        return string.Equals(this.Value, other.Value, StringComparison.Ordinal);
    }

    /// <summary>
    /// Determines whether this instance and a specified object have the same value.
    /// </summary>
    /// <param name="obj">The object to compare to this instance.</param>
    /// <returns><see langword="true"/> if <paramref name="obj"/> is a <see cref="AgentRequestMessageSourceType"/> and its value is the same as this instance; otherwise, <see langword="false"/>.</returns>
    public override bool Equals(object? obj) => obj is AgentRequestMessageSourceType other && this.Equals(other);

    /// <summary>
    /// Returns the string representation of this instance.
    /// </summary>
    /// <returns>The string value representing the source of the agent request message.</returns>
    public override string ToString() => this.Value;

    /// <summary>
    /// Returns the hash code for this instance.
    /// </summary>
    /// <returns>A 32-bit signed integer hash code.</returns>
    public override int GetHashCode() => this.Value?.GetHashCode() ?? 0;

    /// <summary>
    /// Determines whether two specified <see cref="AgentRequestMessageSourceType"/> objects have the same value.
    /// </summary>
    /// <param name="left">The first <see cref="AgentRequestMessageSourceType"/> to compare.</param>
    /// <param name="right">The second <see cref="AgentRequestMessageSourceType"/> to compare.</param>
    /// <returns><see langword="true"/> if the value of <paramref name="left"/> is the same as the value of <paramref name="right"/>; otherwise, <see langword="false"/>.</returns>
    public static bool operator ==(AgentRequestMessageSourceType left, AgentRequestMessageSourceType right)
    {
        return left.Equals(right);
    }

    /// <summary>
    /// Determines whether two specified <see cref="AgentRequestMessageSourceType"/> objects have different values.
    /// </summary>
    /// <param name="left">The first <see cref="AgentRequestMessageSourceType"/> to compare.</param>
    /// <param name="right">The second <see cref="AgentRequestMessageSourceType"/> to compare.</param>
    /// <returns><see langword="true"/> if the value of <paramref name="left"/> is different from the value of <paramref name="right"/>; otherwise, <see langword="false"/>.</returns>
    public static bool operator !=(AgentRequestMessageSourceType left, AgentRequestMessageSourceType right) => !(left == right);
}
