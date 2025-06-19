﻿// Copyright (c) Microsoft. All rights reserved.

using System;
using FluentAssertions;

namespace Microsoft.Agents.Runtime.Core.Tests;

[Trait("Category", "Unit")]
public class TypeSubscriptionTests
{
    [Fact]
    public void ConstructorWithProvidedIdShouldSetProperties()
    {
        // Arrange
        string topicType = "testTopic";
        AgentType agentType = new("testAgent");
        string id = "custom-id";

        // Act
        TypeSubscription subscription = new(topicType, agentType, id);

        // Assert
        subscription.TopicType.Should().Be(topicType);
        subscription.AgentType.Should().Be(agentType);
        subscription.Id.Should().Be(id);
    }

    [Fact]
    public void ConstructorWithoutIdShouldGenerateGuid()
    {
        // Arrange
        string topicType = "testTopic";
        AgentType agentType = new("testAgent");

        // Act
        TypeSubscription subscription = new(topicType, agentType);

        // Assert
        subscription.TopicType.Should().Be(topicType);
        subscription.AgentType.Should().Be(agentType);
        subscription.Id.Should().NotBeNullOrEmpty();
        Guid.TryParse(subscription.Id, out _).Should().BeTrue();
    }

    [Fact]
    public void MatchesTopicWithMatchingTypeShouldReturnTrue()
    {
        // Arrange
        string topicType = "testTopic";
        TypeSubscription subscription = new(topicType, new AgentType("testAgent"));
        TopicId topic = new(topicType, "source1");

        // Act
        bool result = subscription.Matches(topic);

        // Assert
        result.Should().BeTrue();
    }

    [Fact]
    public void MatchesTopicWithDifferentTypeShouldReturnFalse()
    {
        // Arrange
        TypeSubscription subscription = new("testTopic", new AgentType("testAgent"));
        TopicId topic = new("differentTopic", "source1");

        // Act
        bool result = subscription.Matches(topic);

        // Assert
        result.Should().BeFalse();
    }

    [Fact]
    public void MapToAgentMatchingTopicShouldReturnCorrectAgentId()
    {
        // Arrange
        string topicType = "testTopic";
        string source = "source1";
        AgentType agentType = new("testAgent");
        TypeSubscription subscription = new(topicType, agentType);
        TopicId topic = new(topicType, source);

        // Act
        var agentId = subscription.MapToAgent(topic);

        // Assert
        agentId.Type.Should().Be(agentType.Name);
        agentId.Key.Should().Be(source);
    }

    [Fact]
    public void MapToAgentNonMatchingTopicShouldThrowInvalidOperationException()
    {
        // Arrange
        TypeSubscription subscription = new("testTopic", new AgentType("testAgent"));
        TopicId topic = new("differentTopic", "source1");

        // Act & Assert
        Action action = () => subscription.MapToAgent(topic);
        action.Should().Throw<InvalidOperationException>()
            .WithMessage("TopicId does not match the subscription.");
    }

    [Fact]
    public void EqualsSameIdShouldReturnTrue()
    {
        // Arrange
        string id = "custom-id";
        TypeSubscription subscription1 = new("topic1", new AgentType("agent1"), id);
        TypeSubscription subscription2 = new("topic2", new AgentType("agent2"), id);

        // Act & Assert
        subscription1.Equals((object)subscription2).Should().BeTrue();
        subscription1.Equals(subscription2 as ISubscriptionDefinition).Should().BeTrue();
    }

    [Fact]
    public void EqualsSameTypeAndAgentTypeShouldReturnTrue()
    {
        // Arrange
        string topicType = "topic1";
        AgentType agentType = new("agent1");
        TypeSubscription subscription1 = new(topicType, agentType, "id1");
        TypeSubscription subscription2 = new(topicType, agentType, "id2");

        // Act & Assert
        subscription1.Equals((object)subscription2).Should().BeTrue();
    }

    [Fact]
    public void EqualsDifferentIdAndPropertiesShouldReturnFalse()
    {
        // Arrange
        TypeSubscription subscription1 = new("topic1", new AgentType("agent1"), "id1");
        TypeSubscription subscription2 = new("topic2", new AgentType("agent2"), "id2");

        // Act & Assert
        subscription1.Equals((object)subscription2).Should().BeFalse();
        subscription1.Equals(subscription2 as ISubscriptionDefinition).Should().BeFalse();
    }

    [Fact]
    public void EqualsWithNullShouldReturnFalse()
    {
        // Arrange
        TypeSubscription subscription = new("topic1", new AgentType("agent1"));

        // Act & Assert
        subscription.Equals(null as object).Should().BeFalse();
        subscription.Equals(null as ISubscriptionDefinition).Should().BeFalse();
    }

    [Fact]
    public void EqualsWithDifferentTypeShouldReturnFalse()
    {
        // Arrange
        TypeSubscription subscription = new("topic1", new AgentType("agent1"));
        object differentObject = new();

        // Act & Assert
        subscription.Equals(differentObject).Should().BeFalse();
    }

    [Fact]
    public void GetHashCodeSameValuesShouldReturnSameHashCode()
    {
        // Arrange
        string id = "custom-id";
        string topicType = "topic1";
        AgentType agentType = new("agent1");
        TypeSubscription subscription1 = new(topicType, agentType, id);
        TypeSubscription subscription2 = new(topicType, agentType, id);

        // Act & Assert
        subscription1.GetHashCode().Should().Be(subscription2.GetHashCode());
    }

    [Fact]
    public void GetHashCodeDifferentValuesShouldReturnDifferentHashCodes()
    {
        // Arrange
        TypeSubscription subscription1 = new("topic1", new AgentType("agent1"), "id1");
        TypeSubscription subscription2 = new("topic2", new AgentType("agent2"), "id2");

        // Act & Assert
        subscription1.GetHashCode().Should().NotBe(subscription2.GetHashCode());
    }
}
