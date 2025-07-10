// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// This subscription matches on topics based on the exact type and maps to actors using the source of the topic as the actor key.
/// This subscription causes each source to have its own actor instance.
/// </summary>
/// <remarks>
/// Example:
/// <code>
/// var subscription = new TypeSubscription("t1", "a1");
/// </code>
/// In this case:
/// - A <see cref="TopicId"/> with type `"t1"` and source `"s1"` will be handled by an actor of type `"a1"` with key `"s1"`.
/// - A <see cref="TopicId"/> with type `"t1"` and source `"s2"` will be handled by an actor of type `"a1"` with key `"s2"`.
/// </remarks>
public sealed class TypeSubscription : ISubscriptionDefinition
{
    /// <summary>
    /// Initializes a new instance of the <see cref="TypeSubscription"/> class.
    /// </summary>
    /// <param name="topicType">The exact topic type to match against.</param>
    /// <param name="actorType">Actor type to handle this subscription.</param>
    /// <param name="id">Unique identifier for the subscription. If not provided, a new UUID will be generated.</param>
    public TypeSubscription(string topicType, ActorType actorType, string? id = null)
    {
        this.TopicType = topicType;
        this.ActorType = actorType;
        this.Id = id ?? Guid.NewGuid().ToString();
    }

    /// <summary>
    /// Gets the unique identifier of the subscription.
    /// </summary>
    public string Id { get; }

    /// <summary>
    /// Gets the exact topic type used for matching.
    /// </summary>
    public string TopicType { get; }

    /// <summary>
    /// Gets the actor type that handles this subscription.
    /// </summary>
    public ActorType ActorType { get; }

    /// <summary>
    /// Checks if a given <see cref="TopicId"/> matches the subscription based on an exact type match.
    /// </summary>
    /// <param name="topic">The topic to check.</param>
    /// <returns><c>true</c> if the topic's type matches exactly, <c>false</c> otherwise.</returns>
    public bool Matches(TopicId topic)
    {
        return topic.Type == this.TopicType;
    }

    /// <summary>
    /// Maps a <see cref="TopicId"/> to an <see cref="ActorId"/>. Should only be called if <see cref="Matches"/> returns true.
    /// </summary>
    /// <param name="topic">The topic to map.</param>
    /// <returns>An <see cref="ActorId"/> representing the actor that should handle the topic.</returns>
    /// <exception cref="InvalidOperationException">Thrown if the topic does not match the subscription.</exception>
    public ActorId MapToActor(TopicId topic)
    {
        if (!this.Matches(topic))
        {
            throw new InvalidOperationException("TopicId does not match the subscription.");
        }

        return new ActorId(this.ActorType, topic.Source);
    }

    /// <summary>
    /// Determines whether the specified object is equal to the current subscription.
    /// </summary>
    /// <param name="obj">The object to compare with the current instance.</param>
    /// <returns><c>true</c> if the specified object is equal to this instance; otherwise, <c>false</c>.</returns>
    public override bool Equals([NotNullWhen(true)] object? obj)
    {
        return
            obj is TypeSubscription other &&
                (this.Id == other.Id ||
                    (this.ActorType == other.ActorType &&
                        this.TopicType == other.TopicType));
    }

    /// <summary>
    /// Determines whether the specified subscription is equal to the current subscription.
    /// </summary>
    /// <param name="other">The subscription to compare.</param>
    /// <returns><c>true</c> if the subscriptions are equal; otherwise, <c>false</c>.</returns>
    public bool Equals(ISubscriptionDefinition? other) => this.Id == other?.Id;

    /// <summary>
    /// Returns a hash code for this instance.
    /// </summary>
    /// <returns>A hash code for this instance, suitable for use in hashing algorithms and data structures.</returns>
    public override int GetHashCode()
    {
        return HashCode.Combine(this.Id, this.ActorType, this.TopicType);
    }
}
