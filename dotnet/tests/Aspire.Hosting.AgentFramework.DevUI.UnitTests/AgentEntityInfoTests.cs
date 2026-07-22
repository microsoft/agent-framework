// Copyright (c) Microsoft. All rights reserved.

namespace Aspire.Hosting.AgentFramework.DevUI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="AgentEntityInfo"/> record.
/// </summary>
public class AgentEntityInfoTests
{
    #region Constructor Tests

    /// <summary>
    /// Verifies that the Id property is set from the constructor parameter.
    /// </summary>
    [Fact]
    public void Constructor_WithId_SetsIdProperty()
    {
        // Arrange & Act
        var info = new AgentEntityInfo("test-agent");

        // Assert
        Assert.Equal("test-agent", info.Id);
    }

    /// <summary>
    /// Verifies that the Description property is set when provided.
    /// </summary>
    [Fact]
    public void Constructor_WithDescription_SetsDescriptionProperty()
    {
        // Arrange & Act
        var info = new AgentEntityInfo("test-agent", "A test agent");

        // Assert
        Assert.Equal("A test agent", info.Description);
    }

    /// <summary>
    /// Verifies that the Description property is null when not provided.
    /// </summary>
    [Fact]
    public void Constructor_WithoutDescription_DescriptionIsNull()
    {
        // Arrange & Act
        var info = new AgentEntityInfo("test-agent");

        // Assert
        Assert.Null(info.Description);
    }

    #endregion

    #region Default Value Tests

    /// <summary>
    /// Verifies that Name defaults to the Id value when not explicitly set.
    /// </summary>
    [Fact]
    public void Name_NotSet_DefaultsToId()
    {
        // Arrange & Act
        var info = new AgentEntityInfo("test-agent");

        // Assert
        Assert.Equal("test-agent", info.Name);
    }

    /// <summary>
    /// Verifies that Name can be overridden with a custom value.
    /// </summary>
    [Fact]
    public void Name_Set_ReturnsCustomValue()
    {
        // Arrange & Act
        var info = new AgentEntityInfo("test-agent") { Name = "Custom Name" };

        // Assert
        Assert.Equal("Custom Name", info.Name);
    }

    /// <summary>
    /// Verifies that Type defaults to "agent".
    /// </summary>
    [Fact]
    public void Type_NotSet_DefaultsToAgent()
    {
        // Arrange & Act
        var info = new AgentEntityInfo("test-agent");

        // Assert
        Assert.Equal("agent", info.Type);
    }

    /// <summary>
    /// Verifies that Type can be overridden with a custom value.
    /// </summary>
    [Fact]
    public void Type_Set_ReturnsCustomValue()
    {
        // Arrange & Act
        var info = new AgentEntityInfo("test-agent") { Type = "workflow" };

        // Assert
        Assert.Equal("workflow", info.Type);
    }

    /// <summary>
    /// Verifies that Framework defaults to "agent_framework".
    /// </summary>
    [Fact]
    public void Framework_NotSet_DefaultsToAgentFramework()
    {
        // Arrange & Act
        var info = new AgentEntityInfo("test-agent");

        // Assert
        Assert.Equal("agent_framework", info.Framework);
    }

    /// <summary>
    /// Verifies that Framework can be overridden with a custom value.
    /// </summary>
    [Fact]
    public void Framework_Set_ReturnsCustomValue()
    {
        // Arrange & Act
        var info = new AgentEntityInfo("test-agent") { Framework = "custom_framework" };

        // Assert
        Assert.Equal("custom_framework", info.Framework);
    }

    #endregion

    #region Record Equality Tests

    /// <summary>
    /// Verifies that two AgentEntityInfo records with identical values are equal.
    /// </summary>
    [Fact]
    public void Equality_SameValues_AreEqual()
    {
        // Arrange
        var info1 = new AgentEntityInfo("agent", "description");
        var info2 = new AgentEntityInfo("agent", "description");

        // Assert
        Assert.Equal(info1, info2);
    }

    /// <summary>
    /// Verifies that two AgentEntityInfo records with different Ids are not equal.
    /// </summary>
    [Fact]
    public void Equality_DifferentIds_AreNotEqual()
    {
        // Arrange
        var info1 = new AgentEntityInfo("agent1");
        var info2 = new AgentEntityInfo("agent2");

        // Assert
        Assert.NotEqual(info1, info2);
    }

    /// <summary>
    /// Verifies that with-expression creates a modified copy.
    /// </summary>
    [Fact]
    public void WithExpression_ModifiesProperty_CreatesNewInstance()
    {
        // Arrange
        var original = new AgentEntityInfo("agent", "Original description");

        // Act
        var modified = original with { Description = "Modified description" };

        // Assert
        Assert.Equal("Original description", original.Description);
        Assert.Equal("Modified description", modified.Description);
        Assert.Equal(original.Id, modified.Id);
    }

    #endregion
}
