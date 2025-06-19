// Copyright (c) Microsoft. All rights reserved.

using System;
using FluentAssertions;

namespace Microsoft.Agents.Runtime.Core.Tests;

[Trait("Category", "Unit")]
public class TypePrefixSubscriptionTests
{
    [Fact]
    public void ConstructorWithProvidedIdShouldSetProperties()
    {
        // Arrange
        string topicTypePrefix = "testPrefix";
        AgentType agentType = new("testAgent");
        string id = "custom-id";

        // Act
        TypePrefixSubscription subscription = new(topicTypePrefix, agentType, id);

        // Assert
        subscription.TopicTypePrefix.Should().Be(topicTypePrefix);
        subscription.AgentType.Should().Be(agentType);
        subscription.Id.Should().Be(id);
    }

    [Fact]
    public void ConstructorWithoutIdShouldGenerateGuid()
    {
        // Arrange
        string topicTypePrefix = "testPrefix";
        AgentType agentType = new("testAgent");

        // Act
        TypePrefixSubscription subscription = new(topicTypePrefix, agentType);

        // Assert
        subscription.TopicTypePrefix.Should().Be(topicTypePrefix);
        subscription.AgentType.Should().Be(agentType);
        subscription.Id.Should().NotBeNullOrEmpty();
        Guid.TryParse(subscription.Id, out _).Should().BeTrue();
    }

    [Fact]
    public void MatchesTopicWithMatchingPrefixShouldReturnTrue()
    {
        // Arrange
        string topicTypePrefix = "testPrefix";
        TypePrefixSubscription subscription = new(topicTypePrefix, new AgentType("testAgent"));
        TopicId topic = new(topicTypePrefix, "source1");

        // Act
        bool result = subscription.Matches(topic);

        // Assert
        result.Should().BeTrue();
    }

    [Fact]
    public void MatchesTopicWithMatchingPrefixAndAdditionalSuffixShouldReturnTrue()
    {
        // Arrange
        string topicTypePrefix = "testPrefix";
        TypePrefixSubscription subscription = new(topicTypePrefix, new AgentType("testAgent"));
        TopicId topic = new($"{topicTypePrefix}Suffix", "source1");

        // Act
        bool result = subscription.Matches(topic);

        // Assert
        result.Should().BeTrue();
    }

    [Fact]
    public void MatchesTopicWithDifferentPrefixShouldReturnFalse()
    {
        // Arrange
        TypePrefixSubscription subscription = new("testPrefix", new AgentType("testAgent"));
        TopicId topic = new("differentPrefix", "source1");

        // Act
        bool result = subscription.Matches(topic);

        // Assert
        result.Should().BeFalse();
    }

    [Fact]
    public void MapToAgentMatchingTopicShouldReturnCorrectAgentId()
    {
        // Arrange
        string topicTypePrefix = "testPrefix";
        string source = "source1";
        AgentType agentType = new("testAgent");
        TypePrefixSubscription subscription = new(topicTypePrefix, agentType);
        TopicId topic = new(topicTypePrefix, source);

        // Act
        var agentId = subscription.MapToAgent(topic);

        // Assert
        agentId.Type.Should().Be(agentType.Name);
        agentId.Key.Should().Be(source);
    }

    [Fact]
    public void MapToAgentTopicWithMatchingPrefixAndSuffixShouldReturnCorrectAgentId()
    {
        // Arrange
        string topicTypePrefix = "testPrefix";
        string source = "source1";
        AgentType agentType = new("testAgent");
        TypePrefixSubscription subscription = new(topicTypePrefix, agentType);
        TopicId topic = new($"{topicTypePrefix}Suffix", source);

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
        TypePrefixSubscription subscription = new("testPrefix", new AgentType("testAgent"));
        TopicId topic = new("differentPrefix", "source1");

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
        TypePrefixSubscription subscription1 = new("prefix1", new AgentType("agent1"), id);
        TypePrefixSubscription subscription2 = new("prefix2", new AgentType("agent2"), id);

        // Act & Assert
        subscription1.Equals((object)subscription2).Should().BeTrue();
        subscription1.Equals(subscription2 as ISubscriptionDefinition).Should().BeTrue();
    }

    [Fact]
    public void EqualsSameTypeAndAgentTypeShouldReturnTrue()
    {
        // Arrange
        string topicTypePrefix = "prefix1";
        AgentType agentType = new("agent1");
        TypePrefixSubscription subscription1 = new(topicTypePrefix, agentType, "id1");
        TypePrefixSubscription subscription2 = new(topicTypePrefix, agentType, "id2");

        // Act & Assert
        subscription1.Equals((object)subscription2).Should().BeTrue();
    }

    [Fact]
    public void EqualsDifferentIdAndPropertiesShouldReturnFalse()
    {
        // Arrange
        TypePrefixSubscription subscription1 = new("prefix1", new AgentType("agent1"), "id1");
        TypePrefixSubscription subscription2 = new("prefix2", new AgentType("agent2"), "id2");

        // Act & Assert
        subscription1.Equals((object)subscription2).Should().BeFalse();
    }

    [Fact]
    public void EqualsISubscriptionDefinitionWithDifferentIdShouldReturnFalse()
    {
        // Arrange
        TypePrefixSubscription subscription1 = new("prefix1", new AgentType("agent1"), "id1");
        TypePrefixSubscription subscription2 = new("prefix1", new AgentType("agent1"), "id2");

        // Act & Assert
        subscription1.Equals(subscription2 as ISubscriptionDefinition).Should().BeFalse();
    }

    [Fact]
    public void EqualsWithNullShouldReturnFalse()
    {
        // Arrange
        TypePrefixSubscription subscription = new("prefix1", new AgentType("agent1"));

        // Act & Assert
        subscription.Equals(null as object).Should().BeFalse();
        subscription.Equals(null as ISubscriptionDefinition).Should().BeFalse();
    }

    [Fact]
    public void EqualsWithDifferentTypeShouldReturnFalse()
    {
        // Arrange
        TypePrefixSubscription subscription = new("prefix1", new AgentType("agent1"));
        object differentObject = new();

        // Act & Assert
        subscription.Equals(differentObject).Should().BeFalse();
    }

    [Fact]
    public void GetHashCodeSameValuesShouldReturnSameHashCode()
    {
        // Arrange
        string id = "custom-id";
        string topicTypePrefix = "prefix1";
        AgentType agentType = new("agent1");
        TypePrefixSubscription subscription1 = new(topicTypePrefix, agentType, id);
        TypePrefixSubscription subscription2 = new(topicTypePrefix, agentType, id);

        // Act & Assert
        subscription1.GetHashCode().Should().Be(subscription2.GetHashCode());
    }

    [Fact]
    public void GetHashCodeDifferentValuesShouldReturnDifferentHashCodes()
    {
        // Arrange
        TypePrefixSubscription subscription1 = new("prefix1", new AgentType("agent1"), "id1");
        TypePrefixSubscription subscription2 = new("prefix2", new AgentType("agent2"), "id2");

        // Act & Assert
        subscription1.GetHashCode().Should().NotBe(subscription2.GetHashCode());
    }
}
