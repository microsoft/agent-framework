// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Extensions.AI.Agents.Runtime.InProcess.Tests;

public class TestSubscription(string topicType, ActorType agentType, string? id = null) : ISubscriptionDefinition
{
    public string Id { get; } = id ?? Guid.NewGuid().ToString();

    public string TopicType { get; } = topicType;

    public ActorId MapToActor(TopicId topic)
    {
        if (!this.Matches(topic))
        {
            throw new InvalidOperationException("TopicId does not match the subscription.");
        }

        return new ActorId(agentType, topic.Source);
    }

    public bool Equals(ISubscriptionDefinition? other) => this.Id == other?.Id;

    public override bool Equals(object? obj) => obj is TestSubscription other && other.Equals(this);

    public override int GetHashCode() => this.Id.GetHashCode();

    public bool Matches(TopicId topic)
    {
        return topic.Type == this.TopicType;
    }
}
