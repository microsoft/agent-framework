// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.DurableTask.Entities;

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Represents an agent session ID, which is used to identify a long-running agent session.
/// </summary>
[JsonConverter(typeof(AgentSessionIdJsonConverter))]
public readonly struct AgentSessionId : IEquatable<AgentSessionId>
{
    private const string EntityNamePrefix = "dafx-";
    private readonly EntityInstanceId _entityId;

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentSessionId"/> struct.
    /// </summary>
    /// <param name="name">The name of the agent that owns the session (case-insensitive).</param>
    /// <param name="key">The unique key of the agent session (case-sensitive).</param>
    public AgentSessionId(string name, string key)
    {
        this.Name = name;
        this._entityId = new EntityInstanceId(ToEntityName(name), key);
    }

    /// <summary>
    /// Converts an agent name to its underlying entity name representation.
    /// </summary>
    /// <param name="name">The agent name.</param>
    /// <returns>The entity name used by Durable Task for this agent.</returns>
    public static string ToEntityName(string name) => $"{EntityNamePrefix}{name}";

    /// <summary>
    /// Gets the name of the agent that owns the session. Names are case-insensitive.
    /// </summary>
    public string Name { get; }

    /// <summary>
    /// Gets the unique key of the agent session. Keys are case-sensitive and are used to identify the session.
    /// </summary>
    public string Key => this._entityId.Key;

    internal EntityInstanceId ToEntityId() => this._entityId;

    /// <summary>
    /// Creates a new <see cref="AgentSessionId"/> with the specified name and a randomly generated key.
    /// </summary>
    /// <param name="name">The name of the agent that owns the session.</param>
    /// <returns>A new <see cref="AgentSessionId"/> with the specified name and a random key.</returns>
    public static AgentSessionId WithRandomKey(string name) =>
        new(name, Guid.NewGuid().ToString("N"));

    /// <summary>
    /// Determines whether two <see cref="AgentSessionId"/> instances are equal.
    /// </summary>
    /// <param name="left">The first <see cref="AgentSessionId"/> to compare.</param>
    /// <param name="right">The second <see cref="AgentSessionId"/> to compare.</param>
    /// <returns><c>true</c> if the two instances are equal; otherwise, <c>false</c>.</returns>
    public static bool operator ==(AgentSessionId left, AgentSessionId right) =>
        left._entityId == right._entityId;

    /// <summary>
    /// Determines whether two <see cref="AgentSessionId"/> instances are not equal.
    /// </summary>
    /// <param name="left">The first <see cref="AgentSessionId"/> to compare.</param>
    /// <param name="right">The second <see cref="AgentSessionId"/> to compare.</param>
    /// <returns><c>true</c> if the two instances are not equal; otherwise, <c>false</c>.</returns>
    public static bool operator !=(AgentSessionId left, AgentSessionId right) =>
        left._entityId != right._entityId;

    /// <summary>
    /// Determines whether the specified <see cref="AgentSessionId"/> is equal to the current <see cref="AgentSessionId"/>.
    /// </summary>
    /// <param name="other">The <see cref="AgentSessionId"/> to compare with the current <see cref="AgentSessionId"/>.</param>
    /// <returns><c>true</c> if the specified <see cref="AgentSessionId"/> is equal to the current <see cref="AgentSessionId"/>; otherwise, <c>false</c>.</returns>
    public bool Equals(AgentSessionId other) => this == other;

    /// <summary>
    /// Determines whether the specified object is equal to the current <see cref="AgentSessionId"/>.
    /// </summary>
    /// <param name="obj">The object to compare with the current <see cref="AgentSessionId"/>.</param>
    /// <returns><c>true</c> if the specified object is equal to the current <see cref="AgentSessionId"/>; otherwise, <c>false</c>.</returns>
    public override bool Equals(object? obj) => obj is AgentSessionId other && this == other;

    /// <summary>
    /// Returns the hash code for this <see cref="AgentSessionId"/>.
    /// </summary>
    /// <returns>A hash code for the current <see cref="AgentSessionId"/>.</returns>
    public override int GetHashCode() => this._entityId.GetHashCode();

    /// <summary>
    /// Returns a string representation of this <see cref="AgentSessionId"/> in the form of @name@key.
    /// </summary>
    /// <returns>A string representation of the current <see cref="AgentSessionId"/>.</returns>
    public override string ToString() => this._entityId.ToString();

    /// <summary>
    /// Converts the string representation of an agent session ID to its <see cref="AgentSessionId"/> equivalent.
    /// The input string must be in the form of @name@key.
    /// </summary>
    /// <param name="sessionIdString">A string containing an agent session ID to convert.</param>
    /// <returns>A <see cref="AgentSessionId"/> equivalent to the agent session ID contained in <paramref name="sessionIdString"/>.</returns>
    /// <exception cref="ArgumentException">Thrown when <paramref name="sessionIdString"/> is not a valid agent session ID format.</exception>
    public static AgentSessionId Parse(string sessionIdString)
    {
        EntityInstanceId entityId = EntityInstanceId.FromString(sessionIdString);
        if (!entityId.Name.StartsWith(EntityNamePrefix, StringComparison.OrdinalIgnoreCase))
        {
            throw new ArgumentException($"'{sessionIdString}' is not a valid agent session ID.", nameof(sessionIdString));
        }

        return new AgentSessionId(entityId.Name[EntityNamePrefix.Length..], entityId.Key);
    }

    /// <summary>
    /// Implicitly converts an <see cref="AgentSessionId"/> to an <see cref="EntityInstanceId"/>.
    /// This conversion is useful for entity API interoperability.
    /// </summary>
    /// <param name="agentSessionId">The <see cref="AgentSessionId"/> to convert.</param>
    /// <returns>The equivalent <see cref="EntityInstanceId"/>.</returns>
    public static implicit operator EntityInstanceId(AgentSessionId agentSessionId) => agentSessionId.ToEntityId();

    /// <summary>
    /// Implicitly converts an <see cref="EntityInstanceId"/> to an <see cref="AgentSessionId"/>.
    /// </summary>
    /// <param name="entityId">The <see cref="EntityInstanceId"/> to convert.</param>
    /// <returns>The equivalent <see cref="AgentSessionId"/>.</returns>
    [System.Diagnostics.CodeAnalysis.SuppressMessage("Design", "CA1065:Do not raise exceptions in unexpected locations", Justification = "Implicit conversion must validate format.")]
    public static implicit operator AgentSessionId(EntityInstanceId entityId)
    {
        if (!entityId.Name.StartsWith(EntityNamePrefix, StringComparison.OrdinalIgnoreCase))
        {
            throw new ArgumentException($"'{entityId}' is not a valid agent session ID.", nameof(entityId));
        }
        return new AgentSessionId(entityId.Name[EntityNamePrefix.Length..], entityId.Key);
    }

    /// <summary>
    /// Custom JSON converter for <see cref="AgentSessionId"/> to ensure proper serialization and deserialization.
    /// </summary>
    public sealed class AgentSessionIdJsonConverter : JsonConverter<AgentSessionId>
    {
        /// <inheritdoc/>
        public override AgentSessionId Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
        {
            if (reader.TokenType != JsonTokenType.String)
            {
                throw new JsonException("Expected string value");
            }

            string value = reader.GetString() ?? string.Empty;

            return Parse(value);
        }

        /// <inheritdoc/>
        public override void Write(Utf8JsonWriter writer, AgentSessionId value, JsonSerializerOptions options)
        {
            writer.WriteStringValue(value.ToString());
        }
    }
}
