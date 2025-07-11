// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// Represents metadata associated with an actor, including its type, unique key, and description.
/// </summary>
public readonly struct ActorMetadata : IEquatable<ActorMetadata>
{
    /// <summary>
    /// Initializes a new instance of the <see cref="ActorMetadata"/> class with the specified type, key, and description.
    /// </summary>
    /// <param name="type">The type of the actor.</param>
    /// <param name="key">The unique key associated with the actor.</param>
    /// <param name="description">A brief description of the actor.</param>
    public ActorMetadata(ActorType type, string key, string? description = null)
    {
        if (!ActorId.IsValidKey(key))
        {
            throw new ArgumentException("Invalid actor key.", nameof(key));
        }

        this.Type = type;
        this.Key = key;
        this.Description = description;
    }

    /// <summary>
    /// Gets an identifier that associates an actor with a specific factory function.
    /// </summary>
    public ActorType Type { get; }

    /// <summary>
    /// A unique key identifying the actor instance.
    /// Strings may only be composed of alphanumeric letters (a-z, 0-9), or underscores (_).
    /// </summary>
    public string Key { get; }

    /// <summary>
    /// A brief description of the actor's purpose or functionality.
    /// </summary>
    public string? Description { get; }

    /// <inheritdoc/>
    public override readonly bool Equals(object? obj) =>
        obj is ActorMetadata actorMetadata && this.Equals(actorMetadata);

    /// <inheritdoc/>
    public readonly bool Equals(ActorMetadata other) =>
        this.Type == other.Type &&
        this.Key == other.Key &&
        this.Description == other.Description;

    /// <inheritdoc/>
    public override readonly int GetHashCode() =>
        HashCode.Combine(this.Type, this.Key, this.Description);

    /// <inheritdoc/>
    public static bool operator ==(ActorMetadata left, ActorMetadata right) =>
        left.Equals(right);

    /// <inheritdoc/>
    public static bool operator !=(ActorMetadata left, ActorMetadata right) =>
        !(left == right);
}
