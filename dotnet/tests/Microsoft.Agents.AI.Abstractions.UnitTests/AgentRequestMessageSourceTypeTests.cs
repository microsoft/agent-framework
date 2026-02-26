// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Contains tests for the <see cref="AgentRequestMessageSourceType"/> struct.
/// </summary>
public sealed class AgentRequestMessageSourceTypeTests
{
    #region Constructor Tests

    [Fact]
    public void Constructor_WithValue_SetsValueProperty()
    {
        // Arrange
        const string ExpectedValue = "CustomSource";

        // Act
        AgentRequestMessageSourceType source = new(ExpectedValue);

        // Assert
        Assert.Equal(ExpectedValue, source.Value);
    }

    [Fact]
    public void Constructor_WithNullValue_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new AgentRequestMessageSourceType(null!));
    }

    [Fact]
    public void Constructor_WithEmptyValue_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentException>(() => new AgentRequestMessageSourceType(string.Empty));
    }

    [Fact]
    public void Default_DefaultsToExternal()
    {
        // Act
        AgentRequestMessageSourceType defaultSource = default;

        // Assert
        Assert.Equal(AgentRequestMessageSourceType.External, defaultSource);
    }

    #endregion

    #region Static Properties Tests

    [Fact]
    public void External_ReturnsInstanceWithExternalValue()
    {
        // Arrange & Act
        AgentRequestMessageSourceType source = AgentRequestMessageSourceType.External;

        // Assert
        Assert.Equal("External", source.Value);
    }

    [Fact]
    public void AIContextProvider_ReturnsInstanceWithAIContextProviderValue()
    {
        // Arrange & Act
        AgentRequestMessageSourceType source = AgentRequestMessageSourceType.AIContextProvider;

        // Assert
        Assert.Equal("AIContextProvider", source.Value);
    }

    [Fact]
    public void ChatHistory_ReturnsInstanceWithChatHistoryValue()
    {
        // Arrange & Act
        AgentRequestMessageSourceType source = AgentRequestMessageSourceType.ChatHistory;

        // Assert
        Assert.Equal("ChatHistory", source.Value);
    }

    [Fact]
    public void StaticProperties_ReturnEqualValuesOnMultipleCalls()
    {
        // Arrange & Act
        AgentRequestMessageSourceType external1 = AgentRequestMessageSourceType.External;
        AgentRequestMessageSourceType external2 = AgentRequestMessageSourceType.External;
        AgentRequestMessageSourceType aiContextProvider1 = AgentRequestMessageSourceType.AIContextProvider;
        AgentRequestMessageSourceType aiContextProvider2 = AgentRequestMessageSourceType.AIContextProvider;
        AgentRequestMessageSourceType chatHistory1 = AgentRequestMessageSourceType.ChatHistory;
        AgentRequestMessageSourceType chatHistory2 = AgentRequestMessageSourceType.ChatHistory;

        // Assert
        Assert.Equal(external1, external2);
        Assert.Equal(aiContextProvider1, aiContextProvider2);
        Assert.Equal(chatHistory1, chatHistory2);
    }

    #endregion

    #region Equals Tests

    [Fact]
    public void Equals_WithSameInstance_ReturnsTrue()
    {
        // Arrange
        AgentRequestMessageSourceType source = new("Test");

        // Act
        bool result = source.Equals(source);

        // Assert
        Assert.True(result);
    }

    [Fact]
    public void Equals_WithEqualValue_ReturnsTrue()
    {
        // Arrange
        AgentRequestMessageSourceType source1 = new("Test");
        AgentRequestMessageSourceType source2 = new("Test");

        // Act
        bool result = source1.Equals(source2);

        // Assert
        Assert.True(result);
    }

    [Fact]
    public void Equals_WithDifferentValue_ReturnsFalse()
    {
        // Arrange
        AgentRequestMessageSourceType source1 = new("Test1");
        AgentRequestMessageSourceType source2 = new("Test2");

        // Act
        bool result = source1.Equals(source2);

        // Assert
        Assert.False(result);
    }

    [Fact]
    public void Equals_WithNullObject_ReturnsFalse()
    {
        // Arrange
        AgentRequestMessageSourceType source = new("Test");

        // Act
        bool result = source.Equals(null);

        // Assert
        Assert.False(result);
    }

    [Fact]
    public void Equals_WithDifferentCase_ReturnsFalse()
    {
        // Arrange
        AgentRequestMessageSourceType source1 = new("Test");
        AgentRequestMessageSourceType source2 = new("test");

        // Act
        bool result = source1.Equals(source2);

        // Assert
        Assert.False(result);
    }

    [Fact]
    public void Equals_StaticExternalWithNewInstanceHavingSameValue_ReturnsTrue()
    {
        // Arrange
        AgentRequestMessageSourceType external = AgentRequestMessageSourceType.External;
        AgentRequestMessageSourceType newExternal = new("External");

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
        AgentRequestMessageSourceType source1 = new("Test");
        object source2 = new AgentRequestMessageSourceType("Test");

        // Act
        bool result = source1.Equals(source2);

        // Assert
        Assert.True(result);
    }

    [Fact]
    public void ObjectEquals_WithDifferentType_ReturnsFalse()
    {
        // Arrange
        AgentRequestMessageSourceType source = new("Test");
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
        AgentRequestMessageSourceType source = new("Test");
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
        AgentRequestMessageSourceType source1 = new("Test");
        AgentRequestMessageSourceType source2 = new("Test");

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
        AgentRequestMessageSourceType source1 = new("Test1");
        AgentRequestMessageSourceType source2 = new("Test2");

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
        AgentRequestMessageSourceType source1 = new("Test");
        AgentRequestMessageSourceType source2 = new("Test");

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
        AgentRequestMessageSourceType source1 = new("Test");
        AgentRequestMessageSourceType source2 = new("Test");

        // Act
        bool result = source1 == source2;

        // Assert
        Assert.True(result);
    }

    [Fact]
    public void EqualityOperator_WithDifferentValues_ReturnsFalse()
    {
        // Arrange
        AgentRequestMessageSourceType source1 = new("Test1");
        AgentRequestMessageSourceType source2 = new("Test2");

        // Act
        bool result = source1 == source2;

        // Assert
        Assert.False(result);
    }

    [Fact]
    public void EqualityOperator_WithDefaultValues_ReturnsTrue()
    {
        // Arrange
        AgentRequestMessageSourceType source1 = default;
        AgentRequestMessageSourceType source2 = default;

        // Act
        bool result = source1 == source2;

        // Assert
        Assert.True(result);
    }

    [Fact]
    public void EqualityOperator_WithStaticInstances_ReturnsTrue()
    {
        // Arrange
        AgentRequestMessageSourceType external1 = AgentRequestMessageSourceType.External;
        AgentRequestMessageSourceType external2 = AgentRequestMessageSourceType.External;

        // Act
        bool result = external1 == external2;

        // Assert
        Assert.True(result);
    }

    [Fact]
    public void EqualityOperator_StaticWithNewInstanceHavingSameValue_ReturnsTrue()
    {
        // Arrange
        AgentRequestMessageSourceType external = AgentRequestMessageSourceType.External;
        AgentRequestMessageSourceType newExternal = new("External");

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
        AgentRequestMessageSourceType source1 = new("Test");
        AgentRequestMessageSourceType source2 = new("Test");

        // Act
        bool result = source1 != source2;

        // Assert
        Assert.False(result);
    }

    [Fact]
    public void InequalityOperator_WithDifferentValues_ReturnsTrue()
    {
        // Arrange
        AgentRequestMessageSourceType source1 = new("Test1");
        AgentRequestMessageSourceType source2 = new("Test2");

        // Act
        bool result = source1 != source2;

        // Assert
        Assert.True(result);
    }

    [Fact]
    public void InequalityOperator_WithBothDefault_ReturnsFalse()
    {
        // Arrange
        AgentRequestMessageSourceType source1 = default;
        AgentRequestMessageSourceType source2 = default;

        // Act
        bool result = source1 != source2;

        // Assert
        Assert.False(result);
    }

    [Fact]
    public void InequalityOperator_DifferentStaticInstances_ReturnsTrue()
    {
        // Arrange
        AgentRequestMessageSourceType external = AgentRequestMessageSourceType.External;
        AgentRequestMessageSourceType chatHistory = AgentRequestMessageSourceType.ChatHistory;

        // Act
        bool result = external != chatHistory;

        // Assert
        Assert.True(result);
    }

    #endregion

    #region ToString Tests

    [Fact]
    public void ToString_ReturnsValue()
    {
        // Arrange
        AgentRequestMessageSourceType source = new("CustomSource");

        // Act
        string result = source.ToString();

        // Assert
        Assert.Equal("CustomSource", result);
    }

    [Fact]
    public void ToString_StaticExternal_ReturnsExternal()
    {
        // Arrange & Act
        string result = AgentRequestMessageSourceType.External.ToString();

        // Assert
        Assert.Equal("External", result);
    }

    [Fact]
    public void ToString_Default_ReturnsExternal()
    {
        // Arrange
        AgentRequestMessageSourceType source = default;

        // Act
        string result = source.ToString();

        // Assert
        Assert.Equal("External", result);
    }

    #endregion

    #region IEquatable Tests

    [Fact]
    public void IEquatable_ImplementedCorrectly()
    {
        // Arrange
        AgentRequestMessageSourceType source = new("Test");

        // Act & Assert
        Assert.IsAssignableFrom<IEquatable<AgentRequestMessageSourceType>>(source);
    }

    #endregion
}
