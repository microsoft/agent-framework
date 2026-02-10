// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents attribution information for the source of an agent request message for a specific run, including the component type and
/// identifier.
/// </summary>
/// <remarks>
/// Use this struct to identify which component provided a message during an agent run.
/// This is useful to allow filtering of messages based on their source, such as distinguishing between user input, middleware-generated messages, and chat history.
/// </remarks>
public readonly struct AgentRequestMessageSourceAttribution : IEquatable<AgentRequestMessageSourceAttribution>
{
    /// <summary>
    /// Provides the key used in <see cref="ChatMessage.AdditionalProperties"/> to store the <see cref="AgentRequestMessageSourceAttribution"/>
    /// associated with the agent request message.
    /// </summary>
    public static readonly string AdditionalPropertiesKey = "_attribution";

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentRequestMessageSourceAttribution"/> struct with the specified source type and identifier.
    /// </summary>
    /// <param name="sourceType">The <see cref="AgentRequestMessageSourceType"/> of the component that provided the message.</param>
    /// <param name="sourceId">The unique identifier of the component that provided the message.</param>
    public AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType sourceType, string? sourceId)
    {
        this.SourceType = sourceType;
        this.SourceId = sourceId;
    }

    /// <summary>
    /// Gets the type of component that provided the message for the current agent run.
    /// </summary>
    public AgentRequestMessageSourceType SourceType { get; }

    /// <summary>
    /// Gets the unique identifier of the component that provided the message for the current agent run.
    /// </summary>
    public string? SourceId { get; }

    /// <summary>
    /// Determines whether the specified <see cref="AgentRequestMessageSourceAttribution"/> is equal to the current instance.
    /// </summary>
    /// <param name="other">The <see cref="AgentRequestMessageSourceAttribution"/> to compare with the current instance.</param>
    /// <returns><see langword="true"/> if the specified instance is equal to the current instance; otherwise, <see langword="false"/>.</returns>
    public bool Equals(AgentRequestMessageSourceAttribution other)
    {
        return this.SourceType == other.SourceType &&
               string.Equals(this.SourceId, other.SourceId, StringComparison.Ordinal);
    }

    /// <summary>
    /// Determines whether the specified object is equal to the current instance.
    /// </summary>
    /// <param name="obj">The object to compare with the current instance.</param>
    /// <returns><see langword="true"/> if the specified object is equal to the current instance; otherwise, <see langword="false"/>.</returns>
    public override bool Equals(object? obj)
    {
        return obj is AgentRequestMessageSourceAttribution other && this.Equals(other);
    }

    /// <summary>
    /// Returns a hash code for the current instance.
    /// </summary>
    /// <returns>A hash code for the current instance.</returns>
    public override int GetHashCode()
    {
        unchecked
        {
            int hash = 17;
            hash = (hash * 31) + this.SourceType.GetHashCode();
            hash = (hash * 31) + (this.SourceId?.GetHashCode() ?? 0);
            return hash;
        }
    }

    /// <summary>
    /// Determines whether two <see cref="AgentRequestMessageSourceAttribution"/> instances are equal.
    /// </summary>
    /// <param name="left">The first instance to compare.</param>
    /// <param name="right">The second instance to compare.</param>
    /// <returns><see langword="true"/> if the instances are equal; otherwise, <see langword="false"/>.</returns>
    public static bool operator ==(AgentRequestMessageSourceAttribution left, AgentRequestMessageSourceAttribution right)
    {
        return left.Equals(right);
    }

    /// <summary>
    /// Determines whether two <see cref="AgentRequestMessageSourceAttribution"/> instances are not equal.
    /// </summary>
    /// <param name="left">The first instance to compare.</param>
    /// <param name="right">The second instance to compare.</param>
    /// <returns><see langword="true"/> if the instances are not equal; otherwise, <see langword="false"/>.</returns>
    public static bool operator !=(AgentRequestMessageSourceAttribution left, AgentRequestMessageSourceAttribution right)
    {
        return !left.Equals(right);
    }
}
