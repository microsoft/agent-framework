// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// An enumeration representing the source of an agent request message.
/// </summary>
/// <remarks>
/// Input messages for a specific agent run can originate from various sources.
/// This enumeration helps to identify whether a message came from outside the agent pipeline,
/// whether it was produced by middleware, or came from chat history.
/// </remarks>
public sealed class AgentRequestMessageSource : IEquatable<AgentRequestMessageSource>
{
    /// <summary>
    /// Provides the key used in <see cref="ChatMessage.AdditionalProperties"/> to store the source of the agent request message.
    /// </summary>
    public static readonly string AdditionalPropertiesKey = "Agent.RequestMessageSource";

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentRequestMessageSource"/> class.
    /// </summary>
    /// <param name="value">The string value representing the source of the agent request message.</param>
    public AgentRequestMessageSource(string value) => this.Value = Throw.IfNullOrWhitespace(value);

    /// <summary>
    /// Get the string value representing the source of the agent request message.
    /// </summary>
    public string Value { get; }

    /// <summary>
    /// The message came from outside the agent pipeline (e.g., user input).
    /// </summary>
    public static AgentRequestMessageSource External { get; } = new AgentRequestMessageSource(nameof(External));

    /// <summary>
    /// The message was produced by middleware.
    /// </summary>
    public static AgentRequestMessageSource AIContextProvider { get; } = new AgentRequestMessageSource(nameof(AIContextProvider));

    /// <summary>
    /// The message came from chat history.
    /// </summary>
    public static AgentRequestMessageSource ChatHistory { get; } = new AgentRequestMessageSource(nameof(ChatHistory));

    /// <summary>
    /// Determines whether this instance and another specified <see cref="AgentRequestMessageSource"/> object have the same value.
    /// </summary>
    /// <param name="other">The <see cref="AgentRequestMessageSource"/> to compare to this instance.</param>
    /// <returns><see langword="true"/> if the value of the <paramref name="other"/> parameter is the same as the value of this instance; otherwise, <see langword="false"/>.</returns>
    public bool Equals(AgentRequestMessageSource? other)
    {
        if (other is null)
        {
            return false;
        }

        if (ReferenceEquals(this, other))
        {
            return true;
        }

        return string.Equals(this.Value, other.Value, StringComparison.Ordinal);
    }

    /// <summary>
    /// Determines whether this instance and a specified object have the same value.
    /// </summary>
    /// <param name="obj">The object to compare to this instance.</param>
    /// <returns><see langword="true"/> if <paramref name="obj"/> is a <see cref="AgentRequestMessageSource"/> and its value is the same as this instance; otherwise, <see langword="false"/>.</returns>
    public override bool Equals(object? obj) => this.Equals(obj as AgentRequestMessageSource);

    /// <summary>
    /// Returns the hash code for this instance.
    /// </summary>
    /// <returns>A 32-bit signed integer hash code.</returns>
    public override int GetHashCode() => this.Value?.GetHashCode() ?? 0;

    /// <summary>
    /// Determines whether two specified <see cref="AgentRequestMessageSource"/> objects have the same value.
    /// </summary>
    /// <param name="left">The first <see cref="AgentRequestMessageSource"/> to compare.</param>
    /// <param name="right">The second <see cref="AgentRequestMessageSource"/> to compare.</param>
    /// <returns><see langword="true"/> if the value of <paramref name="left"/> is the same as the value of <paramref name="right"/>; otherwise, <see langword="false"/>.</returns>
    public static bool operator ==(AgentRequestMessageSource? left, AgentRequestMessageSource? right)
    {
        if (left is null)
        {
            return right is null;
        }

        return left.Equals(right);
    }

    /// <summary>
    /// Determines whether two specified <see cref="AgentRequestMessageSource"/> objects have different values.
    /// </summary>
    /// <param name="left">The first <see cref="AgentRequestMessageSource"/> to compare.</param>
    /// <param name="right">The second <see cref="AgentRequestMessageSource"/> to compare.</param>
    /// <returns><see langword="true"/> if the value of <paramref name="left"/> is different from the value of <paramref name="right"/>; otherwise, <see langword="false"/>.</returns>
    public static bool operator !=(AgentRequestMessageSource? left, AgentRequestMessageSource? right) => !(left == right);
}
