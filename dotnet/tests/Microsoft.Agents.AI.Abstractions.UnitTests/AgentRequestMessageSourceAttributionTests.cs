// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Contains tests for the <see cref="AgentRequestMessageSourceAttribution"/> struct.
/// </summary>
public sealed class AgentRequestMessageSourceAttributionTests
{
    #region Constructor Tests

    [Fact]
    public void Constructor_SetsSourceTypeAndSourceId()
    {
        // Arrange
        AgentRequestMessageSourceType expectedType = AgentRequestMessageSourceType.AIContextProvider;
        const string ExpectedId = "MyProvider";

        // Act
        AgentRequestMessageSourceAttribution attribution = new(expectedType, ExpectedId);

        // Assert
        Assert.Equal(expectedType, attribution.SourceType);
        Assert.Equal(ExpectedId, attribution.SourceId);
    }

    [Fact]
    public void Constructor_WithNullSourceId_SetsNullSourceId()
    {
        // Arrange
        AgentRequestMessageSourceType sourceType = AgentRequestMessageSourceType.ChatHistory;

        // Act
        AgentRequestMessageSourceAttribution attribution = new(sourceType, null);

        // Assert
        Assert.Equal(sourceType, attribution.SourceType);
        Assert.Null(attribution.SourceId);
    }

    #endregion

    #region AdditionalPropertiesKey Tests

    [Fact]
    public void AdditionalPropertiesKey_IsAttribution()
    {
        // Assert
        Assert.Equal("_attribution", AgentRequestMessageSourceAttribution.AdditionalPropertiesKey);
    }

    #endregion

    #region Default Value Tests

    [Fact]
    public void Default_HasDefaultSourceTypeAndNullSourceId()
    {
        // Arrange & Act
        AgentRequestMessageSourceAttribution attribution = default;

        // Assert
        Assert.Equal(default, attribution.SourceType);
        Assert.Null(attribution.SourceId);
    }

    #endregion

    #region Equals (IEquatable) Tests

    [Fact]
    public void Equals_WithSameSourceTypeAndSourceId_ReturnsTrue()
    {
        // Arrange
        AgentRequestMessageSourceAttribution attribution1 = new(AgentRequestMessageSourceType.AIContextProvider, "Provider1");
        AgentRequestMessageSourceAttribution attribution2 = new(AgentRequestMessageSourceType.AIContextProvider, "Provider1");

        // Act
        bool result = attribution1.Equals(attribution2);

        // Assert
        Assert.True(result);
    }

    [Fact]
    public void Equals_WithDifferentSourceType_ReturnsFalse()
    {
        // Arrange
        AgentRequestMessageSourceAttribution attribution1 = new(AgentRequestMessageSourceType.AIContextProvider, "Provider1");
        AgentRequestMessageSourceAttribution attribution2 = new(AgentRequestMessageSourceType.ChatHistory, "Provider1");

        // Act
        bool result = attribution1.Equals(attribution2);

        // Assert
        Assert.False(result);
    }

    [Fact]
    public void Equals_WithDifferentSourceId_ReturnsFalse()
    {
        // Arrange
        AgentRequestMessageSourceAttribution attribution1 = new(AgentRequestMessageSourceType.AIContextProvider, "Provider1");
        AgentRequestMessageSourceAttribution attribution2 = new(AgentRequestMessageSourceType.AIContextProvider, "Provider2");

        // Act
        bool result = attribution1.Equals(attribution2);

        // Assert
        Assert.False(result);
    }

    [Fact]
    public void Equals_WithDifferentSourceTypeAndSourceId_ReturnsFalse()
    {
        // Arrange
        AgentRequestMessageSourceAttribution attribution1 = new(AgentRequestMessageSourceType.AIContextProvider, "Provider1");
        AgentRequestMessageSourceAttribution attribution2 = new(AgentRequestMessageSourceType.ChatHistory, "Provider2");

        // Act
        bool result = attribution1.Equals(attribution2);

        // Assert
        Assert.False(result);
    }

    [Fact]
    public void Equals_WithDifferentCaseSourceId_ReturnsFalse()
    {
        // Arrange
        AgentRequestMessageSourceAttribution attribution1 = new(AgentRequestMessageSourceType.AIContextProvider, "Provider");
        AgentRequestMessageSourceAttribution attribution2 = new(AgentRequestMessageSourceType.AIContextProvider, "provider");

        // Act
        bool result = attribution1.Equals(attribution2);

        // Assert
        Assert.False(result);
    }

    [Fact]
    public void Equals_BothDefaultValues_ReturnsTrue()
    {
        // Arrange
        AgentRequestMessageSourceAttribution attribution1 = default;
        AgentRequestMessageSourceAttribution attribution2 = default;

        // Act
        bool result = attribution1.Equals(attribution2);

        // Assert
        Assert.True(result);
    }

    [Fact]
    public void Equals_WithBothNullSourceIds_ReturnsTrue()
    {
        // Arrange
        AgentRequestMessageSourceAttribution attribution1 = new(AgentRequestMessageSourceType.External, null!);
        AgentRequestMessageSourceAttribution attribution2 = new(AgentRequestMessageSourceType.External, null!);

        // Act
        bool result = attribution1.Equals(attribution2);

        // Assert
        Assert.True(result);
    }

    [Fact]
    public void Equals_WithOneNullSourceId_ReturnsFalse()
    {
        // Arrange
        AgentRequestMessageSourceAttribution attribution1 = new(AgentRequestMessageSourceType.External, "Provider1");
        AgentRequestMessageSourceAttribution attribution2 = new(AgentRequestMessageSourceType.External, null!);

        // Act
        bool result = attribution1.Equals(attribution2);

        // Assert
        Assert.False(result);
    }

    #endregion

    #region Object.Equals Tests

    [Fact]
    public void ObjectEquals_WithEqualAttribution_ReturnsTrue()
    {
        // Arrange
        AgentRequestMessageSourceAttribution attribution1 = new(AgentRequestMessageSourceType.ChatHistory, "Provider");
        object attribution2 = new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.ChatHistory, "Provider");

        // Act
        bool result = attribution1.Equals(attribution2);

        // Assert
        Assert.True(result);
    }

    [Fact]
    public void ObjectEquals_WithDifferentType_ReturnsFalse()
    {
        // Arrange
        AgentRequestMessageSourceAttribution attribution = new(AgentRequestMessageSourceType.ChatHistory, "Provider");
        object other = "NotAnAttribution";

        // Act
        bool result = attribution.Equals(other);

        // Assert
        Assert.False(result);
    }

    [Fact]
    public void ObjectEquals_WithNullObject_ReturnsFalse()
    {
        // Arrange
        AgentRequestMessageSourceAttribution attribution = new(AgentRequestMessageSourceType.ChatHistory, "Provider");
        object? other = null;

        // Act
        bool result = attribution.Equals(other);

        // Assert
        Assert.False(result);
    }

    [Fact]
    public void ObjectEquals_WithBoxedDifferentAttribution_ReturnsFalse()
    {
        // Arrange
        AgentRequestMessageSourceAttribution attribution1 = new(AgentRequestMessageSourceType.ChatHistory, "Provider1");
        object attribution2 = new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.ChatHistory, "Provider2");

        // Act
        bool result = attribution1.Equals(attribution2);

        // Assert
        Assert.False(result);
    }

    #endregion

    #region GetHashCode Tests

    [Fact]
    public void GetHashCode_WithSameValues_ReturnsSameHashCode()
    {
        // Arrange
        AgentRequestMessageSourceAttribution attribution1 = new(AgentRequestMessageSourceType.AIContextProvider, "Provider");
        AgentRequestMessageSourceAttribution attribution2 = new(AgentRequestMessageSourceType.AIContextProvider, "Provider");

        // Act
        int hashCode1 = attribution1.GetHashCode();
        int hashCode2 = attribution2.GetHashCode();

        // Assert
        Assert.Equal(hashCode1, hashCode2);
    }

    [Fact]
    public void GetHashCode_WithDifferentSourceType_ReturnsDifferentHashCode()
    {
        // Arrange
        AgentRequestMessageSourceAttribution attribution1 = new(AgentRequestMessageSourceType.AIContextProvider, "Provider");
        AgentRequestMessageSourceAttribution attribution2 = new(AgentRequestMessageSourceType.ChatHistory, "Provider");

        // Act
        int hashCode1 = attribution1.GetHashCode();
        int hashCode2 = attribution2.GetHashCode();

        // Assert
        Assert.NotEqual(hashCode1, hashCode2);
    }

    [Fact]
    public void GetHashCode_WithDifferentSourceId_ReturnsDifferentHashCode()
    {
        // Arrange
        AgentRequestMessageSourceAttribution attribution1 = new(AgentRequestMessageSourceType.AIContextProvider, "Provider1");
        AgentRequestMessageSourceAttribution attribution2 = new(AgentRequestMessageSourceType.AIContextProvider, "Provider2");

        // Act
        int hashCode1 = attribution1.GetHashCode();
        int hashCode2 = attribution2.GetHashCode();

        // Assert
        Assert.NotEqual(hashCode1, hashCode2);
    }

    [Fact]
    public void GetHashCode_ConsistentWithEquals()
    {
        // Arrange
        AgentRequestMessageSourceAttribution attribution1 = new(AgentRequestMessageSourceType.External, "Provider");
        AgentRequestMessageSourceAttribution attribution2 = new(AgentRequestMessageSourceType.External, "Provider");

        // Act & Assert
        Assert.True(attribution1.Equals(attribution2));
        Assert.Equal(attribution1.GetHashCode(), attribution2.GetHashCode());
    }

    [Fact]
    public void GetHashCode_WithNullSourceId_DoesNotThrow()
    {
        // Arrange
        AgentRequestMessageSourceAttribution attribution = new(AgentRequestMessageSourceType.External, null!);

        // Act
        int hashCode = attribution.GetHashCode();

        // Assert
        Assert.IsType<int>(hashCode);
    }

    #endregion

    #region Equality Operator Tests

    [Fact]
    public void EqualityOperator_WithEqualValues_ReturnsTrue()
    {
        // Arrange
        AgentRequestMessageSourceAttribution attribution1 = new(AgentRequestMessageSourceType.AIContextProvider, "Provider");
        AgentRequestMessageSourceAttribution attribution2 = new(AgentRequestMessageSourceType.AIContextProvider, "Provider");

        // Act
        bool result = attribution1 == attribution2;

        // Assert
        Assert.True(result);
    }

    [Fact]
    public void EqualityOperator_WithDifferentValues_ReturnsFalse()
    {
        // Arrange
        AgentRequestMessageSourceAttribution attribution1 = new(AgentRequestMessageSourceType.AIContextProvider, "Provider1");
        AgentRequestMessageSourceAttribution attribution2 = new(AgentRequestMessageSourceType.ChatHistory, "Provider2");

        // Act
        bool result = attribution1 == attribution2;

        // Assert
        Assert.False(result);
    }

    [Fact]
    public void EqualityOperator_WithBothDefault_ReturnsTrue()
    {
        // Arrange
        AgentRequestMessageSourceAttribution attribution1 = default;
        AgentRequestMessageSourceAttribution attribution2 = default;

        // Act
        bool result = attribution1 == attribution2;

        // Assert
        Assert.True(result);
    }

    [Fact]
    public void EqualityOperator_WithDifferentSourceTypeOnly_ReturnsFalse()
    {
        // Arrange
        AgentRequestMessageSourceAttribution attribution1 = new(AgentRequestMessageSourceType.AIContextProvider, "Provider");
        AgentRequestMessageSourceAttribution attribution2 = new(AgentRequestMessageSourceType.External, "Provider");

        // Act
        bool result = attribution1 == attribution2;

        // Assert
        Assert.False(result);
    }

    [Fact]
    public void EqualityOperator_WithDifferentSourceIdOnly_ReturnsFalse()
    {
        // Arrange
        AgentRequestMessageSourceAttribution attribution1 = new(AgentRequestMessageSourceType.AIContextProvider, "Provider1");
        AgentRequestMessageSourceAttribution attribution2 = new(AgentRequestMessageSourceType.AIContextProvider, "Provider2");

        // Act
        bool result = attribution1 == attribution2;

        // Assert
        Assert.False(result);
    }

    #endregion

    #region ToString Tests

    [Fact]
    public void ToString_WithSourceId_ReturnsTypeColonId()
    {
        // Arrange
        AgentRequestMessageSourceAttribution attribution = new(AgentRequestMessageSourceType.AIContextProvider, "MyProvider");

        // Act
        string result = attribution.ToString();

        // Assert
        Assert.Equal("AIContextProvider:MyProvider", result);
    }

    [Fact]
    public void ToString_WithNullSourceId_ReturnsTypeOnly()
    {
        // Arrange
        AgentRequestMessageSourceAttribution attribution = new(AgentRequestMessageSourceType.ChatHistory, null);

        // Act
        string result = attribution.ToString();

        // Assert
        Assert.Equal("ChatHistory", result);
    }

    [Fact]
    public void ToString_Default_ReturnsExternalOnly()
    {
        // Arrange
        AgentRequestMessageSourceAttribution attribution = default;

        // Act
        string result = attribution.ToString();

        // Assert
        Assert.Equal("External", result);
    }

    #endregion

    #region Inequality Operator Tests

    [Fact]
    public void InequalityOperator_WithEqualValues_ReturnsFalse()
    {
        // Arrange
        AgentRequestMessageSourceAttribution attribution1 = new(AgentRequestMessageSourceType.AIContextProvider, "Provider");
        AgentRequestMessageSourceAttribution attribution2 = new(AgentRequestMessageSourceType.AIContextProvider, "Provider");

        // Act
        bool result = attribution1 != attribution2;

        // Assert
        Assert.False(result);
    }

    [Fact]
    public void InequalityOperator_WithDifferentValues_ReturnsTrue()
    {
        // Arrange
        AgentRequestMessageSourceAttribution attribution1 = new(AgentRequestMessageSourceType.AIContextProvider, "Provider1");
        AgentRequestMessageSourceAttribution attribution2 = new(AgentRequestMessageSourceType.ChatHistory, "Provider2");

        // Act
        bool result = attribution1 != attribution2;

        // Assert
        Assert.True(result);
    }

    [Fact]
    public void InequalityOperator_WithBothDefault_ReturnsFalse()
    {
        // Arrange
        AgentRequestMessageSourceAttribution attribution1 = default;
        AgentRequestMessageSourceAttribution attribution2 = default;

        // Act
        bool result = attribution1 != attribution2;

        // Assert
        Assert.False(result);
    }

    [Fact]
    public void InequalityOperator_WithDifferentSourceTypeOnly_ReturnsTrue()
    {
        // Arrange
        AgentRequestMessageSourceAttribution attribution1 = new(AgentRequestMessageSourceType.AIContextProvider, "Provider");
        AgentRequestMessageSourceAttribution attribution2 = new(AgentRequestMessageSourceType.External, "Provider");

        // Act
        bool result = attribution1 != attribution2;

        // Assert
        Assert.True(result);
    }

    [Fact]
    public void InequalityOperator_WithDifferentSourceIdOnly_ReturnsTrue()
    {
        // Arrange
        AgentRequestMessageSourceAttribution attribution1 = new(AgentRequestMessageSourceType.AIContextProvider, "Provider1");
        AgentRequestMessageSourceAttribution attribution2 = new(AgentRequestMessageSourceType.AIContextProvider, "Provider2");

        // Act
        bool result = attribution1 != attribution2;

        // Assert
        Assert.True(result);
    }

    #endregion
}
