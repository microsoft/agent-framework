// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// Represents the type of an actor.
/// </summary>
[JsonConverter(typeof(Converter))]
public readonly partial struct ActorType : IEquatable<ActorType>
{
#if NET7_0_OR_GREATER
    [System.Diagnostics.CodeAnalysis.StringSyntax("Regex")]
#endif
    private const string AgentTypeValidationRegex = "^[a-zA-Z_][a-zA-Z._:\\-0-9]*$";

    /// <summary>
    /// Initializes a new instance of the <see cref="ActorId"/> struct.
    /// </summary>
    /// <param name="type">The actor type.</param>
    public ActorType(string type)
    {
        Throw.IfNullOrEmpty(type);
        if (!IsValidType(type))
        {
            throw new ArgumentException($"Invalid type: '{type}'. Must start with a letter or underscore, and can only contain letters, dots, underscores, colons, hyphens, and numbers.", nameof(type));
        }

        this.Name = type;
    }

    /// <summary>
    /// The string representation of this actor type.
    /// </summary>
    public string Name { get; }

    /// <summary>
    /// Returns the string representation of the <see cref="ActorType"/>.
    /// </summary>
    /// <returns>A string in the format "type/source".</returns>
    public override readonly string ToString() =>
        this.Name;

    /// <inheritdoc/>
    public override bool Equals(object? obj) =>
        obj is ActorType other && this.Equals(other);

    /// <inheritdoc/>
    public bool Equals(ActorType other) =>
        this.Name.Equals(other.Name, StringComparison.Ordinal);

    /// <inheritdoc/>
    public override int GetHashCode() =>
        this.Name.GetHashCode();

    /// <inheritdoc/>
    public static bool operator ==(ActorType left, ActorType right) =>
        left.Equals(right);

    /// <inheritdoc/>
    public static bool operator !=(ActorType left, ActorType right) =>
        !(left == right);

#if NET7_0_OR_GREATER
    [GeneratedRegex(AgentTypeValidationRegex)]
    private static partial Regex TypeRegex();
#else
    private static readonly Regex s_typeRegex = new(AgentTypeValidationRegex, RegexOptions.Compiled);
    private static Regex TypeRegex() => s_typeRegex;
#endif

    /// <summary>
    /// Validates whether the provided type string is a valid actor type.
    /// </summary>
    public static bool IsValidType(string type)
    {
        Throw.IfNullOrEmpty(type);
        return TypeRegex().IsMatch(type);
    }

    /// <summary>
    /// JSON converter for <see cref="ActorType"/>.
    /// </summary>
    public sealed class Converter : JsonConverter<ActorType>
    {
        /// <inheritdoc/>
        public override ActorType Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
        {
            if (reader.TokenType != JsonTokenType.String)
            {
                throw new JsonException("Expected string value for ActorType");
            }

            string? actorTypeString = reader.GetString() ?? throw new JsonException("ActorType cannot be null");
            return new ActorType(actorTypeString);
        }

        /// <inheritdoc/>
        public override void Write(Utf8JsonWriter writer, ActorType value, JsonSerializerOptions options) =>
            writer.WriteStringValue(value.Name);
    }
}
