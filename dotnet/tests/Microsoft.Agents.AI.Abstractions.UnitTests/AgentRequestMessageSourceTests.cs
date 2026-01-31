// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Contains tests for the <see cref="AgentRequestMessageSource"/> class.
/// </summary>
public sealed class AgentRequestMessageSourceTests
{
    #region Constructor Tests

    [Fact]
    public void Constructor_WithValue_SetsValueProperty()
    {
        // Arrange
        const string ExpectedValue = "CustomSource";

        // Act
        AgentRequestMessageSource source = new(ExpectedValue);

        // Assert
        Assert.Equal(ExpectedValue, source.Value);
    }

    [Fact]
    public void Constructor_WithNullValue_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new AgentRequestMessageSource(null!));
    }

    [Fact]
    public void Constructor_WithEmptyValue_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentException>(() => new AgentRequestMessageSource(string.Empty));
    }

    #endregion

    #region Static Properties Tests

    [Fact]
    public void External_ReturnsInstanceWithExternalValue()
    {
        // Arrange & Act
        AgentRequestMessageSource source = AgentRequestMessageSource.External;

        // Assert
        Assert.NotNull(source);
        Assert.Equal("External", source.Value);
    }

    [Fact]
    public void AIContextProvider_ReturnsInstanceWithAIContextProviderValue()
    {
        // Arrange & Act
        AgentRequestMessageSource source = AgentRequestMessageSource.AIContextProvider;

        // Assert
        Assert.NotNull(source);
        Assert.Equal("AIContextProvider", source.Value);
    }

    [Fact]
    public void ChatHistory_ReturnsInstanceWithChatHistoryValue()
    {
        // Arrange & Act
        AgentRequestMessageSource source = AgentRequestMessageSource.ChatHistory;

        // Assert
        Assert.NotNull(source);
        Assert.Equal("ChatHistory", source.Value);
    }

    [Fact]
    public void AdditionalPropertiesKey_ReturnsExpectedValue()
    {
        // Arrange & Act
        string key = AgentRequestMessageSource.AdditionalPropertiesKey;

        // Assert
        Assert.Equal("Agent.RequestMessageSource", key);
    }

    [Fact]
    public void StaticProperties_ReturnSameInstanceOnMultipleCalls()
    {
        // Arrange & Act
        AgentRequestMessageSource external1 = AgentRequestMessageSource.External;
        AgentRequestMessageSource external2 = AgentRequestMessageSource.External;
        AgentRequestMessageSource aiContextProvider1 = AgentRequestMessageSource.AIContextProvider;
        AgentRequestMessageSource aiContextProvider2 = AgentRequestMessageSource.AIContextProvider;
        AgentRequestMessageSource chatHistory1 = AgentRequestMessageSource.ChatHistory;
        AgentRequestMessageSource chatHistory2 = AgentRequestMessageSource.ChatHistory;

        // Assert
        Assert.Same(external1, external2);
        Assert.Same(aiContextProvider1, aiContextProvider2);
        Assert.Same(chatHistory1, chatHistory2);
    }

    #endregion

    #region Equals Tests

    [Fact]
    public void Equals_WithSameInstance_ReturnsTrue()
    {
        // Arrange
        AgentRequestMessageSource source = new("Test");

        // Act
        bool result = source.Equals(source);

        // Assert
        Assert.True(result);
    }

    [Fact]
    public void Equals_WithEqualValue_ReturnsTrue()
    {
        // Arrange
        AgentRequestMessageSource source1 = new("Test");
        AgentRequestMessageSource source2 = new("Test");

        // Act
        bool result = source1.Equals(source2);

        // Assert
        Assert.True(result);
    }

    [Fact]
    public void Equals_WithDifferentValue_ReturnsFalse()
    {
        // Arrange
        AgentRequestMessageSource source1 = new("Test1");
        AgentRequestMessageSource source2 = new("Test2");

        // Act
        bool result = source1.Equals(source2);

        // Assert
        Assert.False(result);
    }

    [Fact]
    public void Equals_WithNull_ReturnsFalse()
    {
        // Arrange
        AgentRequestMessageSource source = new("Test");

        // Act
        bool result = source.Equals(null);

        // Assert
        Assert.False(result);
    }

    [Fact]
    public void Equals_WithDifferentCase_ReturnsFalse()
    {
        // Arrange
        AgentRequestMessageSource source1 = new("Test");
        AgentRequestMessageSource source2 = new("test");

        // Act
        bool result = source1.Equals(source2);

        // Assert
        Assert.False(result);
    }

    [Fact]
    public void Equals_StaticExternalWithNewInstanceHavingSameValue_ReturnsTrue()
    {
        // Arrange
        AgentRequestMessageSource external = AgentRequestMessageSource.External;
        AgentRequestMessageSource newExternal = new("External");

        // Act
        bool result = external.Equals(newExternal);

        // Assert
        Assert.True(result);
    }

    #endregion

    #region Object.Equals Tests

    [Fact]
    public void ObjectEquals_WithEqualAgentRequestMessageSource_ReturnsTrue()
    {
        // Arrange
        AgentRequestMessageSource source1 = new("Test");
        object source2 = new AgentRequestMessageSource("Test");

        // Act
        bool result = source1.Equals(source2);

        // Assert
        Assert.True(result);
    }

    [Fact]
    public void ObjectEquals_WithDifferentType_ReturnsFalse()
    {
        // Arrange
        AgentRequestMessageSource source = new("Test");
        object other = "Test";

        // Act
        bool result = source.Equals(other);

        // Assert
        Assert.False(result);
    }

    [Fact]
    public void ObjectEquals_WithNullObject_ReturnsFalse()
    {
        // Arrange
        AgentRequestMessageSource source = new("Test");
        object? other = null;

        // Act
        bool result = source.Equals(other);

        // Assert
        Assert.False(result);
    }

    #endregion

    #region GetHashCode Tests

    [Fact]
    public void GetHashCode_WithSameValue_ReturnsSameHashCode()
    {
        // Arrange
        AgentRequestMessageSource source1 = new("Test");
        AgentRequestMessageSource source2 = new("Test");

        // Act
        int hashCode1 = source1.GetHashCode();
        int hashCode2 = source2.GetHashCode();

        // Assert
        Assert.Equal(hashCode1, hashCode2);
    }

    [Fact]
    public void GetHashCode_WithDifferentValue_ReturnsDifferentHashCode()
    {
        // Arrange
        AgentRequestMessageSource source1 = new("Test1");
        AgentRequestMessageSource source2 = new("Test2");

        // Act
        int hashCode1 = source1.GetHashCode();
        int hashCode2 = source2.GetHashCode();

        // Assert
        Assert.NotEqual(hashCode1, hashCode2);
    }

    [Fact]
    public void GetHashCode_ConsistentWithEquals()
    {
        // Arrange
        AgentRequestMessageSource source1 = new("Test");
        AgentRequestMessageSource source2 = new("Test");

        // Act & Assert
        // If two objects are equal, they must have the same hash code
        Assert.True(source1.Equals(source2));
        Assert.Equal(source1.GetHashCode(), source2.GetHashCode());
    }

    #endregion

    #region Equality Operator Tests

    [Fact]
    public void EqualityOperator_WithEqualValues_ReturnsTrue()
    {
        // Arrange
        AgentRequestMessageSource source1 = new("Test");
        AgentRequestMessageSource source2 = new("Test");

        // Act
        bool result = source1 == source2;

        // Assert
        Assert.True(result);
    }

    [Fact]
    public void EqualityOperator_WithDifferentValues_ReturnsFalse()
    {
        // Arrange
        AgentRequestMessageSource source1 = new("Test1");
        AgentRequestMessageSource source2 = new("Test2");

        // Act
        bool result = source1 == source2;

        // Assert
        Assert.False(result);
    }

    [Fact]
    public void EqualityOperator_WithBothNull_ReturnsTrue()
    {
        // Arrange
        AgentRequestMessageSource? source1 = null;
        AgentRequestMessageSource? source2 = null;

        // Act
        bool result = source1 == source2;

        // Assert
        Assert.True(result);
    }

    [Fact]
    public void EqualityOperator_WithLeftNull_ReturnsFalse()
    {
        // Arrange
        AgentRequestMessageSource? source1 = null;
        AgentRequestMessageSource source2 = new("Test");

        // Act
        bool result = source1 == source2;

        // Assert
        Assert.False(result);
    }

    [Fact]
    public void EqualityOperator_WithRightNull_ReturnsFalse()
    {
        // Arrange
        AgentRequestMessageSource source1 = new("Test");
        AgentRequestMessageSource? source2 = null;

        // Act
        bool result = source1 == source2;

        // Assert
        Assert.False(result);
    }

    [Fact]
    public void EqualityOperator_WithStaticInstances_ReturnsTrue()
    {
        // Arrange
        AgentRequestMessageSource external1 = AgentRequestMessageSource.External;
        AgentRequestMessageSource external2 = AgentRequestMessageSource.External;

        // Act
        bool result = external1 == external2;

        // Assert
        Assert.True(result);
    }

    [Fact]
    public void EqualityOperator_StaticWithNewInstanceHavingSameValue_ReturnsTrue()
    {
        // Arrange
        AgentRequestMessageSource external = AgentRequestMessageSource.External;
        AgentRequestMessageSource newExternal = new("External");

        // Act
        bool result = external == newExternal;

        // Assert
        Assert.True(result);
    }

    #endregion

    #region Inequality Operator Tests

    [Fact]
    public void InequalityOperator_WithEqualValues_ReturnsFalse()
    {
        // Arrange
        AgentRequestMessageSource source1 = new("Test");
        AgentRequestMessageSource source2 = new("Test");

        // Act
        bool result = source1 != source2;

        // Assert
        Assert.False(result);
    }

    [Fact]
    public void InequalityOperator_WithDifferentValues_ReturnsTrue()
    {
        // Arrange
        AgentRequestMessageSource source1 = new("Test1");
        AgentRequestMessageSource source2 = new("Test2");

        // Act
        bool result = source1 != source2;

        // Assert
        Assert.True(result);
    }

    [Fact]
    public void InequalityOperator_WithBothNull_ReturnsFalse()
    {
        // Arrange
        AgentRequestMessageSource? source1 = null;
        AgentRequestMessageSource? source2 = null;

        // Act
        bool result = source1 != source2;

        // Assert
        Assert.False(result);
    }

    [Fact]
    public void InequalityOperator_WithLeftNull_ReturnsTrue()
    {
        // Arrange
        AgentRequestMessageSource? source1 = null;
        AgentRequestMessageSource source2 = new("Test");

        // Act
        bool result = source1 != source2;

        // Assert
        Assert.True(result);
    }

    [Fact]
    public void InequalityOperator_WithRightNull_ReturnsTrue()
    {
        // Arrange
        AgentRequestMessageSource source1 = new("Test");
        AgentRequestMessageSource? source2 = null;

        // Act
        bool result = source1 != source2;

        // Assert
        Assert.True(result);
    }

    [Fact]
    public void InequalityOperator_DifferentStaticInstances_ReturnsTrue()
    {
        // Arrange
        AgentRequestMessageSource external = AgentRequestMessageSource.External;
        AgentRequestMessageSource chatHistory = AgentRequestMessageSource.ChatHistory;

        // Act
        bool result = external != chatHistory;

        // Assert
        Assert.True(result);
    }

    #endregion

    #region IEquatable Tests

    [Fact]
    public void IEquatable_ImplementedCorrectly()
    {
        // Arrange
        AgentRequestMessageSource source = new("Test");

        // Act & Assert
        Assert.IsAssignableFrom<IEquatable<AgentRequestMessageSource>>(source);
    }

    #endregion
}
