// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.Runtime.Core.Tests;

[Trait("Category", "Unit")]
public class TypePrefixSubscriptionAttributeTests
{
    [Fact]
    public void ConstructorSetsTopicCorrectly()
    {
        // Arrange & Act
        TypePrefixSubscriptionAttribute attribute = new("test-topic");

        // Assert
        Assert.Equal("test-topic", attribute.Topic);
    }

    [Fact]
    public void BindCreatesTypeSubscription()
    {
        // Arrange
        TypePrefixSubscriptionAttribute attribute = new("test");
        AgentType agentType = new("testagent");

        // Act
        ISubscriptionDefinition subscription = attribute.Bind(agentType);

        // Assert
        Assert.NotNull(subscription);
        TypePrefixSubscription typeSubscription = Assert.IsType<TypePrefixSubscription>(subscription);
        Assert.Equal("test", typeSubscription.TopicTypePrefix);
        Assert.Equal(agentType, typeSubscription.AgentType);
    }

    [Fact]
    public void AttributeUsageAllowsOnlyClasses()
    {
        // Arrange
        Type attributeType = typeof(TypePrefixSubscriptionAttribute);

        // Act
        AttributeUsageAttribute usageAttribute =
            (AttributeUsageAttribute)Attribute.GetCustomAttribute(
                attributeType,
                typeof(AttributeUsageAttribute))!;

        // Assert
        Assert.NotNull(usageAttribute);
        Assert.Equal(AttributeTargets.Class, usageAttribute.ValidOn);
    }
}
