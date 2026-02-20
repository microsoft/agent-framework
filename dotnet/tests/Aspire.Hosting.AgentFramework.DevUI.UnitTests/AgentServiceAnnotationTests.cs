// Copyright (c) Microsoft. All rights reserved.

using System;
using Aspire.Hosting.ApplicationModel;
using Moq;

namespace Aspire.Hosting.AgentFramework.DevUI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="AgentServiceAnnotation"/> class.
/// </summary>
public class AgentServiceAnnotationTests
{
    #region Constructor Validation Tests

    /// <summary>
    /// Verifies that passing null for agentService throws ArgumentNullException.
    /// </summary>
    [Fact]
    public void Constructor_NullAgentService_ThrowsArgumentNullException()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new AgentServiceAnnotation(null!));
    }

    /// <summary>
    /// Verifies that a valid agentService can be used to create the annotation.
    /// </summary>
    [Fact]
    public void Constructor_ValidAgentService_CreatesAnnotation()
    {
        // Arrange
        var mockResource = new Mock<IResource>();
        mockResource.Setup(r => r.Name).Returns("test-service");

        // Act
        var annotation = new AgentServiceAnnotation(mockResource.Object);

        // Assert
        Assert.NotNull(annotation);
        Assert.Same(mockResource.Object, annotation.AgentService);
    }

    #endregion

    #region Property Tests

    /// <summary>
    /// Verifies that AgentService property returns the value passed to constructor.
    /// </summary>
    [Fact]
    public void AgentService_ReturnsConstructorValue()
    {
        // Arrange
        var mockResource = new Mock<IResource>();
        mockResource.Setup(r => r.Name).Returns("my-service");

        // Act
        var annotation = new AgentServiceAnnotation(mockResource.Object);

        // Assert
        Assert.Same(mockResource.Object, annotation.AgentService);
    }

    /// <summary>
    /// Verifies that EntityIdPrefix returns null when not specified.
    /// </summary>
    [Fact]
    public void EntityIdPrefix_NotSpecified_ReturnsNull()
    {
        // Arrange
        var mockResource = new Mock<IResource>();
        mockResource.Setup(r => r.Name).Returns("test-service");

        // Act
        var annotation = new AgentServiceAnnotation(mockResource.Object);

        // Assert
        Assert.Null(annotation.EntityIdPrefix);
    }

    /// <summary>
    /// Verifies that EntityIdPrefix returns the value passed to constructor.
    /// </summary>
    [Fact]
    public void EntityIdPrefix_Specified_ReturnsValue()
    {
        // Arrange
        var mockResource = new Mock<IResource>();
        mockResource.Setup(r => r.Name).Returns("test-service");

        // Act
        var annotation = new AgentServiceAnnotation(mockResource.Object, entityIdPrefix: "custom-prefix");

        // Assert
        Assert.Equal("custom-prefix", annotation.EntityIdPrefix);
    }

    /// <summary>
    /// Verifies that Agents returns empty collection when not specified.
    /// </summary>
    [Fact]
    public void Agents_NotSpecified_ReturnsEmptyCollection()
    {
        // Arrange
        var mockResource = new Mock<IResource>();
        mockResource.Setup(r => r.Name).Returns("test-service");

        // Act
        var annotation = new AgentServiceAnnotation(mockResource.Object);

        // Assert
        Assert.NotNull(annotation.Agents);
        Assert.Empty(annotation.Agents);
    }

    /// <summary>
    /// Verifies that Agents returns the list passed to constructor.
    /// </summary>
    [Fact]
    public void Agents_Specified_ReturnsValue()
    {
        // Arrange
        var mockResource = new Mock<IResource>();
        mockResource.Setup(r => r.Name).Returns("test-service");
        var agents = new[] { new AgentEntityInfo("agent1"), new AgentEntityInfo("agent2") };

        // Act
        var annotation = new AgentServiceAnnotation(mockResource.Object, agents: agents);

        // Assert
        Assert.Equal(2, annotation.Agents.Count);
        Assert.Equal("agent1", annotation.Agents[0].Id);
        Assert.Equal("agent2", annotation.Agents[1].Id);
    }

    #endregion

    #region Full Constructor Tests

    /// <summary>
    /// Verifies that all constructor parameters are correctly stored.
    /// </summary>
    [Fact]
    public void Constructor_AllParameters_SetsAllProperties()
    {
        // Arrange
        var mockResource = new Mock<IResource>();
        mockResource.Setup(r => r.Name).Returns("full-service");
        var agents = new[] { new AgentEntityInfo("writer", "Writes stories") };

        // Act
        var annotation = new AgentServiceAnnotation(
            mockResource.Object,
            entityIdPrefix: "writer-backend",
            agents: agents);

        // Assert
        Assert.Same(mockResource.Object, annotation.AgentService);
        Assert.Equal("writer-backend", annotation.EntityIdPrefix);
        Assert.Single(annotation.Agents);
        Assert.Equal("writer", annotation.Agents[0].Id);
        Assert.Equal("Writes stories", annotation.Agents[0].Description);
    }

    #endregion
}
