// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// Provides a unique identifier for an actor instance within an agent runtime,
/// serving as the "address" of the actor instance for receiving messages.
/// </summary>
[JsonConverter(typeof(Converter))]
public readonly struct ActorId : IEquatable<ActorId>
{
    /// <summary>
    /// Initializes a new instance of the <see cref="ActorId"/> struct from an <see cref="ActorType"/>.
    /// </summary>
    /// <param name="type">The actor type.</param>
    /// <param name="key">Actor instance identifier.</param>
    public ActorId(string type, string key) : this(new ActorType(type), key)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="ActorId"/> struct from an <see cref="ActorType"/>.
    /// </summary>
    /// <param name="type">The actor type.</param>
    /// <param name="key">Actor instance identifier.</param>
    public ActorId(ActorType type, string key)
    {
        if (!IsValidKey(key))
        {
            throw new ArgumentException($"Invalid {nameof(ActorId)} key.", nameof(key));
        }

        this.Type = type;
        this.Key = key;
    }

    /// <summary>
    /// Gets an identifier that associates an actor with a specific factory function.
    /// </summary>
    /// <remarks>
    /// Strings may only be composed of alphanumeric letters (a-z) and (0-9), or underscores (_).
    /// </remarks>
    public ActorType Type { get; }

    /// <summary>
    /// Gets an actor instance identifier.
    /// </summary>
    /// <remarks>
    /// Strings may only be composed of alphanumeric letters (a-z) and (0-9), or underscores (_).
    /// </remarks>
    public string Key { get; }

    /// <summary>
    /// Convert a string of the format "type/key" into an <see cref="ActorId"/>.
    /// </summary>
    /// <param name="value">The actor ID string.</param>
    /// <returns>An instance of <see cref="ActorId"/>.</returns>
    public static ActorId Parse(string value)
    {
        if (!TryParse(value, out var result))
        {
            throw new FormatException($"Invalid actor ID: '{value}'. Expected format is 'type/key'.");
        }

        return result;
    }

    private static bool TryParse(string input, out ActorId actorId)
    {
        if (!string.IsNullOrEmpty(input))
        {
            int separatorIndex = input.IndexOf('/');
            if (separatorIndex >= 0)
            {
                var type = input.Substring(0, separatorIndex);
                var key = input.Substring(separatorIndex + 1);
                actorId = new ActorId(type, key);
                return true;
            }
        }

        actorId = default;
        return false;
    }

    /// <inheritdoc />
    public override readonly string ToString() => $"{this.Type}/{this.Key}";

    /// <inheritdoc />
    public override readonly bool Equals([NotNullWhen(true)] object? obj) =>
        obj is ActorId other && this.Equals(other);

    /// <inheritdoc/>
    public readonly bool Equals(ActorId other) =>
        this.Type == other.Type && this.Key == other.Key;

    /// <inheritdoc />
    public override readonly int GetHashCode() =>
        HashCode.Combine(this.Type, this.Key);

    /// <inheritdoc />
    public static bool operator ==(ActorId left, ActorId right) =>
        left.Equals(right);

    /// <inheritdoc />
    public static bool operator !=(ActorId left, ActorId right) =>
        !left.Equals(right);

    /// <summary>Determines whether the specified key is valid.</summary>
    /// <remarks>It must be non-null, not be only whitespace, and only contain printable ASCII characters.</remarks>
    internal static bool IsValidKey(string key)
    {
        if (string.IsNullOrWhiteSpace(key))
        {
            return false;
        }

#if NET
        return !key.AsSpan().ContainsAnyExceptInRange((char)32, (char)126);
#else
        foreach (char c in key)
        {
            if ((int)c is < 32 or > 126)
            {
                return false;
            }
        }

        return true;
#endif
    }

    /// <summary>
    /// JSON converter for <see cref="ActorId"/>.
    /// </summary>
    public sealed class Converter : JsonConverter<ActorId>
    {
        /// <inheritdoc/>
        public override ActorId Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
        {
            if (reader.TokenType != JsonTokenType.String)
            {
                throw new JsonException("Expected string value for ActorId");
            }

            string? actorIdString = reader.GetString() ?? throw new JsonException("ActorId cannot be null");
            return Parse(actorIdString);
        }

        /// <inheritdoc/>
        public override void Write(Utf8JsonWriter writer, ActorId value, JsonSerializerOptions options) =>
            writer.WriteStringValue(value.ToString());
    }
}
