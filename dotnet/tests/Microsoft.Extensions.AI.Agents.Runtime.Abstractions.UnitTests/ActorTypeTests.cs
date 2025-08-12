// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;

namespace Microsoft.Extensions.AI.Agents.Runtime.UnitTests;

public class ActorTypeTests
{
    /// <summary>
    /// Provides valid ActorType names that conform to the regex pattern ^[a-zA-Z_][a-zA-Z._:\-0-9]*$.
    /// </summary>
    public static IEnumerable<object[]> ValidActorTypeNames => new List<object[]>
        {
            new object[] { "a" }, // Single letter
            new object[] { "A" }, // Single uppercase letter
            new object[] { "_" }, // Single underscore
            new object[] { "agent" }, // Simple name
            new object[] { "Agent" }, // Capitalized name
            new object[] { "AGENT" }, // All caps name
            new object[] { "my_agent" }, // With underscore
            new object[] { "MyAgent" }, // Camel case
            new object[] { "agent1" }, // With number
            new object[] { "agent_1" }, // With underscore and number
            new object[] { "agent:type" }, // With colon
            new object[] { "agent-type" }, // With hyphen
            new object[] { "my_agent:type-1" }, // Complex valid name
            new object[] { "A1_test:complex-name" }, // Very complex valid name
            new object[] { "_private_agent" }, // Starting with underscore
            new object[] { "agent_with_many_underscores" }, // Multiple underscores
            new object[] { "agent:with:colons" }, // Multiple colons
            new object[] { "agent-with-hyphens" }, // Multiple hyphens
            new object[] { "agent123456789" }, // With many numbers
            new object[] { "agent.type" }, // With dot
            new object[] { "agent.sub.type" }, // With multiple dots
            new object[] { "my.agent_1:type-name" }, // Complex with dots
        };

    /// <summary>
    /// Provides invalid ActorType names that violate the regex pattern ^[a-zA-Z_][a-zA-Z._:\-0-9]*$.
    /// </summary>
    public static IEnumerable<object[]> InvalidActorTypeNames => new List<object[]>
        {
            new object[] { "1agent" }, // Starting with number
            new object[] { "9test" }, // Starting with number
            new object[] { "-agent" }, // Starting with hyphen
            new object[] { ":agent" }, // Starting with colon
            new object[] { " agent" }, // Starting with space
            new object[] { "agent " }, // Trailing space
            new object[] { "agent agent" }, // Space in middle
            new object[] { "agent@type" }, // Invalid character @
            new object[] { "agent#type" }, // Invalid character #
            new object[] { "agent$type" }, // Invalid character $
            new object[] { "agent%type" }, // Invalid character %
            new object[] { "agent^type" }, // Invalid character ^
            new object[] { "agent&type" }, // Invalid character &
            new object[] { "agent*type" }, // Invalid character *
            new object[] { "agent(type)" }, // Invalid characters ( )
            new object[] { "agent[type]" }, // Invalid characters [ ]
            new object[] { "agent{type}" }, // Invalid characters { }
            new object[] { "agent+type" }, // Invalid character +
            new object[] { "agent=type" }, // Invalid character =
            new object[] { "agent\\type" }, // Invalid character \
            new object[] { "agent/type" }, // Invalid character /
            new object[] { "agent?type" }, // Invalid character ?
            new object[] { "agent,type" }, // Invalid character ,
            new object[] { "agent;type" }, // Invalid character ;
            new object[] { "agent\"type" }, // Invalid character "
            new object[] { "agent'type" }, // Invalid character '
            new object[] { "agent`type" }, // Invalid character `
            new object[] { "agent~type" }, // Invalid character ~
            new object[] { "agent!type" }, // Invalid character !
            new object[] { "agent\ttype" }, // Tab character
            new object[] { "agent\ntype" }, // Newline character
        };

    /// <summary>
    /// Verifies that providing valid actor type name to <see cref="ActorType"/> constructor sets the Name property correctly.
    /// </summary>
    /// <param name="typeName">The valid type name to test.</param>
    [Theory]
    [MemberData(nameof(ValidActorTypeNames))]
    public void Constructor_ValidTypeName_SetsNameProperty(string typeName)
    {
        // Act
        var actorType = new ActorType(typeName);

        // Assert
        Assert.Equal(typeName, actorType.Name);
    }

    /// <summary>
    /// Verifies that providing invalid actor type name to <see cref="ActorType"/> constructor throws an <see cref="ArgumentException"/>.
    /// </summary>
    /// <param name="typeName">The invalid type name to test.</param>
    [Theory]
    [MemberData(nameof(InvalidActorTypeNames))]
    public void Constructor_InvalidTypeName_ThrowsArgumentException(string typeName)
    {
        // Act & Assert
        var exception = Assert.Throws<ArgumentException>(() => new ActorType(typeName));
        Assert.Contains("Invalid type", exception.Message);
        Assert.Contains("Must start with a letter or underscore, and can only contain letters, dots, underscores, colons, hyphens, and numbers", exception.Message);
    }

    /// <summary>
    /// Verifies that providing a null type name to <see cref="ActorType"/> constructor throws an <see cref="ArgumentNullException"/>.
    /// </summary>
    [Fact]
    public void Constructor_NullTypeName_ThrowsArgumentNullException()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new ActorType(null!));
    }

    /// <summary>
    /// Verifies that providing an empty type name to <see cref="ActorType"/> constructor throws an <see cref="ArgumentException"/>.
    /// </summary>
    [Fact]
    public void Constructor_EmptyTypeName_ThrowsArgumentException()
    {
        // Act & Assert
        Assert.Throws<ArgumentException>(() => new ActorType(""));
    }

    /// <summary>
    /// Verifies specific edge cases for valid type names.
    /// </summary>
    [Theory]
    [InlineData("a")]
    [InlineData("Z")]
    [InlineData("_")]
    [InlineData("a1")]
    [InlineData("_1")]
    [InlineData("agent_123")]
    [InlineData("MyAgent:SubType")]
    [InlineData("my-agent")]
    [InlineData("agent_type:sub-type_123")]
    [InlineData("agent.type")]
    [InlineData("my.agent.name")]
    [InlineData("complex.name_1:type-sub")]
    public void Constructor_ValidTypeNameEdgeCases_SetsNameProperty(string typeName)
    {
        // Act
        var actorType = new ActorType(typeName);

        // Assert
        Assert.Equal(typeName, actorType.Name);
    }

    /// <summary>
    /// Verifies specific edge cases for invalid type names.
    /// </summary>
    [Theory]
    [InlineData("1")]
    [InlineData("9")]
    [InlineData("-")]
    [InlineData(":")]
    [InlineData("1agent")]
    [InlineData("-agent")]
    [InlineData(":agent")]
    [InlineData(" ")]
    [InlineData("agent ")]
    [InlineData(" agent")]
    [InlineData("a b")]
    [InlineData("agent@type")]
    [InlineData("agent/type")]
    public void Constructor_InvalidTypeNameEdgeCases_ThrowsArgumentException(string typeName)
    {
        // Act & Assert
        var exception = Assert.Throws<ArgumentException>(() => new ActorType(typeName));
        Assert.Contains("Invalid type", exception.Message);
        Assert.Contains("Must start with a letter or underscore", exception.Message);
    }

    /// <summary>
    /// Verifies that ToString returns the type name.
    /// </summary>
    [Fact]
    public void ToString_ReturnsTypeName()
    {
        // Arrange
        const string TypeName = "test_agent";
        var actorType = new ActorType(TypeName);

        // Act
        string result = actorType.ToString();

        // Assert
        Assert.Equal(TypeName, result);
    }

    /// <summary>
    /// Verifies equality comparison between ActorType instances.
    /// </summary>
    [Fact]
    public void Equals_SameTypeName_ReturnsTrue()
    {
        // Arrange
        var actorType1 = new ActorType("test_agent");
        var actorType2 = new ActorType("test_agent");

        // Act & Assert
        Assert.True(actorType1.Equals(actorType2));
        Assert.True(actorType1 == actorType2);
        Assert.False(actorType1 != actorType2);
    }

    /// <summary>
    /// Verifies inequality comparison between ActorType instances.
    /// </summary>
    [Fact]
    public void Equals_DifferentTypeName_ReturnsFalse()
    {
        // Arrange
        var actorType1 = new ActorType("test_agent1");
        var actorType2 = new ActorType("test_agent2");

        // Act & Assert
        Assert.False(actorType1.Equals(actorType2));
        Assert.False(actorType1 == actorType2);
        Assert.True(actorType1 != actorType2);
    }

    /// <summary>
    /// Verifies that GetHashCode returns same value for equal instances.
    /// </summary>
    [Fact]
    public void GetHashCode_SameTypeName_ReturnsSameHashCode()
    {
        // Arrange
        var actorType1 = new ActorType("test_agent");
        var actorType2 = new ActorType("test_agent");

        // Act & Assert
        Assert.Equal(actorType1.GetHashCode(), actorType2.GetHashCode());
    }

    /// <summary>
    /// Verifies that ActorType is case sensitive.
    /// </summary>
    [Fact]
    public void Equality_IsCaseSensitive()
    {
        // Arrange
        var actorType1 = new ActorType("TestAgent");
        var actorType2 = new ActorType("testagent");

        // Act & Assert
        Assert.False(actorType1.Equals(actorType2));
        Assert.False(actorType1 == actorType2);
        Assert.True(actorType1 != actorType2);
        Assert.NotEqual(actorType1.GetHashCode(), actorType2.GetHashCode());
    }

    /// <summary>
    /// Verifies that IsValidType static method works correctly for valid names.
    /// </summary>
    [Theory]
    [MemberData(nameof(ValidActorTypeNames))]
    public void IsValidType_ValidTypeName_ReturnsTrue(string typeName)
    {
        // Act & Assert
        Assert.True(ActorType.IsValidType(typeName));
    }

    /// <summary>
    /// Verifies that IsValidType static method works correctly for invalid names.
    /// </summary>
    [Theory]
    [MemberData(nameof(InvalidActorTypeNames))]
    public void IsValidType_InvalidTypeName_ReturnsFalse(string typeName)
    {
        // Act & Assert
        Assert.False(ActorType.IsValidType(typeName));
    }

    /// <summary>
    /// Verifies that IsValidType throws for null.
    /// </summary>
    [Fact]
    public void IsValidType_NullTypeName_ThrowsArgumentNullException()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => ActorType.IsValidType(null!));
    }

    /// <summary>
    /// Verifies that IsValidType throws for empty string.
    /// </summary>
    [Fact]
    public void IsValidType_EmptyTypeName_ThrowsArgumentException()
    {
        // Act & Assert
        Assert.Throws<ArgumentException>(() => ActorType.IsValidType(""));
    }
}
