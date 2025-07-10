// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.RegularExpressions;

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// Represents the type of an actor.
/// </summary>
public readonly partial struct ActorType : IEquatable<ActorType>
{
    /// <summary>
    /// Initializes a new instance of the <see cref="ActorId"/> struct.
    /// </summary>
    /// <param name="type">The actor type.</param>
    public ActorType(string type)
    {
        if (!IsValid(type))
        {
            throw new ArgumentException($"Invalid type: '{type}'. Must be alphanumeric (a-z, 0-9, _) and cannot start with a number or contain spaces.");
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

    internal static bool IsValid(string type) =>
        type is not null && TypeRegex().IsMatch(type);

#if NET
    [GeneratedRegex("^[a-zA-Z_][a-zA-Z_0-9]*$")]
    private static partial Regex TypeRegex();
#else
    private static Regex TypeRegex() => new("^[a-zA-Z_][a-zA-Z_0-9]*$", RegexOptions.Compiled);
#endif
}
