// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using Aspire.Hosting.AgentFramework;
using Aspire.Hosting.ApplicationModel;
using Moq;

namespace Aspire.Hosting.AgentFramework.DevUI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="AgentFrameworkBuilderExtensions"/> class.
/// </summary>
public class AgentFrameworkBuilderExtensionsTests
{
    #region AddDevUI Validation Tests

    /// <summary>
    /// Verifies that AddDevUI throws ArgumentNullException when builder is null.
    /// </summary>
    [Fact]
    public void AddDevUI_NullBuilder_ThrowsArgumentNullException()
    {
        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(
            () => AgentFrameworkBuilderExtensions.AddDevUI(null!, "devui"));
        Assert.Equal("builder", exception.ParamName);
    }

    /// <summary>
    /// Verifies that AddDevUI throws ArgumentNullException when name is null.
    /// </summary>
    [Fact]
    public void AddDevUI_NullName_ThrowsArgumentNullException()
    {
        // Arrange
        var builder = DistributedApplication.CreateBuilder();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(
            () => builder.AddDevUI(null!));
        Assert.Equal("name", exception.ParamName);
    }

    /// <summary>
    /// Verifies that AddDevUI creates a resource with the specified name.
    /// </summary>
    [Fact]
    public void AddDevUI_ValidName_CreatesResourceWithName()
    {
        // Arrange
        var builder = DistributedApplication.CreateBuilder();

        // Act
        var resourceBuilder = builder.AddDevUI("my-devui");

        // Assert
        Assert.Equal("my-devui", resourceBuilder.Resource.Name);
    }

    /// <summary>
    /// Verifies that AddDevUI creates a DevUIResource.
    /// </summary>
    [Fact]
    public void AddDevUI_ReturnsDevUIResourceBuilder()
    {
        // Arrange
        var builder = DistributedApplication.CreateBuilder();

        // Act
        var resourceBuilder = builder.AddDevUI("devui");

        // Assert
        Assert.IsType<DevUIResource>(resourceBuilder.Resource);
    }

    /// <summary>
    /// Verifies that AddDevUI with port configures the endpoint.
    /// </summary>
    [Fact]
    public void AddDevUI_WithPort_ConfiguresEndpointWithPort()
    {
        // Arrange
        var builder = DistributedApplication.CreateBuilder();

        // Act
        var resourceBuilder = builder.AddDevUI("devui", port: 8090);

        // Assert
        var endpoint = resourceBuilder.Resource.Annotations
            .OfType<EndpointAnnotation>()
            .FirstOrDefault(e => e.Name == "http");
        Assert.NotNull(endpoint);
        Assert.Equal(8090, endpoint.Port);
    }

    /// <summary>
    /// Verifies that AddDevUI without port leaves port as null for dynamic allocation.
    /// </summary>
    [Fact]
    public void AddDevUI_WithoutPort_EndpointHasDynamicPort()
    {
        // Arrange
        var builder = DistributedApplication.CreateBuilder();

        // Act
        var resourceBuilder = builder.AddDevUI("devui");

        // Assert
        var endpoint = resourceBuilder.Resource.Annotations
            .OfType<EndpointAnnotation>()
            .FirstOrDefault(e => e.Name == "http");
        Assert.NotNull(endpoint);
        Assert.Null(endpoint.Port);
    }

    #endregion

    #region WithAgentService Validation Tests

    /// <summary>
    /// Verifies that WithAgentService throws ArgumentNullException when builder is null.
    /// </summary>
    [Fact]
    public void WithAgentService_NullBuilder_ThrowsArgumentNullException()
    {
        // Arrange
        var appBuilder = DistributedApplication.CreateBuilder();
        var mockAgentService = CreateMockAgentServiceBuilder(appBuilder, "agent-service");

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(
            () => AgentFrameworkBuilderExtensions.WithAgentService<IResourceWithEndpoints>(null!, mockAgentService));
        Assert.Equal("builder", exception.ParamName);
    }

    /// <summary>
    /// Verifies that WithAgentService throws ArgumentNullException when agentService is null.
    /// </summary>
    [Fact]
    public void WithAgentService_NullAgentService_ThrowsArgumentNullException()
    {
        // Arrange
        var appBuilder = DistributedApplication.CreateBuilder();
        var devuiBuilder = appBuilder.AddDevUI("devui");

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(
            () => devuiBuilder.WithAgentService<IResourceWithEndpoints>(null!));
        Assert.Equal("agentService", exception.ParamName);
    }

    #endregion

    #region WithAgentService Annotation Tests

    /// <summary>
    /// Verifies that WithAgentService adds an AgentServiceAnnotation to the resource.
    /// </summary>
    [Fact]
    public void WithAgentService_ValidService_AddsAnnotation()
    {
        // Arrange
        var appBuilder = DistributedApplication.CreateBuilder();
        var devuiBuilder = appBuilder.AddDevUI("devui");
        var agentService = CreateMockAgentServiceBuilder(appBuilder, "writer-agent");

        // Act
        devuiBuilder.WithAgentService(agentService);

        // Assert
        var annotation = devuiBuilder.Resource.Annotations
            .OfType<AgentServiceAnnotation>()
            .FirstOrDefault();
        Assert.NotNull(annotation);
        Assert.Same(agentService.Resource, annotation.AgentService);
    }

    /// <summary>
    /// Verifies that WithAgentService defaults to agent name being the resource name.
    /// </summary>
    [Fact]
    public void WithAgentService_NoAgents_DefaultsToResourceNameAsAgent()
    {
        // Arrange
        var appBuilder = DistributedApplication.CreateBuilder();
        var devuiBuilder = appBuilder.AddDevUI("devui");
        var agentService = CreateMockAgentServiceBuilder(appBuilder, "writer-agent");

        // Act
        devuiBuilder.WithAgentService(agentService);

        // Assert
        var annotation = devuiBuilder.Resource.Annotations
            .OfType<AgentServiceAnnotation>()
            .First();
        Assert.Single(annotation.Agents);
        Assert.Equal("writer-agent", annotation.Agents[0].Id);
    }

    /// <summary>
    /// Verifies that WithAgentService with explicit agents uses those agents.
    /// </summary>
    [Fact]
    public void WithAgentService_WithAgents_UsesProvidedAgents()
    {
        // Arrange
        var appBuilder = DistributedApplication.CreateBuilder();
        var devuiBuilder = appBuilder.AddDevUI("devui");
        var agentService = CreateMockAgentServiceBuilder(appBuilder, "multi-agent-service");
        var agents = new[]
        {
            new AgentEntityInfo("agent1", "First agent"),
            new AgentEntityInfo("agent2", "Second agent")
        };

        // Act
        devuiBuilder.WithAgentService(agentService, agents: agents);

        // Assert
        var annotation = devuiBuilder.Resource.Annotations
            .OfType<AgentServiceAnnotation>()
            .First();
        Assert.Equal(2, annotation.Agents.Count);
        Assert.Equal("agent1", annotation.Agents[0].Id);
        Assert.Equal("agent2", annotation.Agents[1].Id);
    }

    /// <summary>
    /// Verifies that WithAgentService with custom prefix uses that prefix.
    /// </summary>
    [Fact]
    public void WithAgentService_WithEntityIdPrefix_UsesProvidedPrefix()
    {
        // Arrange
        var appBuilder = DistributedApplication.CreateBuilder();
        var devuiBuilder = appBuilder.AddDevUI("devui");
        var agentService = CreateMockAgentServiceBuilder(appBuilder, "writer-agent");

        // Act
        devuiBuilder.WithAgentService(agentService, entityIdPrefix: "custom-prefix");

        // Assert
        var annotation = devuiBuilder.Resource.Annotations
            .OfType<AgentServiceAnnotation>()
            .First();
        Assert.Equal("custom-prefix", annotation.EntityIdPrefix);
    }

    /// <summary>
    /// Verifies that WithAgentService without prefix leaves EntityIdPrefix null.
    /// </summary>
    [Fact]
    public void WithAgentService_NoEntityIdPrefix_PrefixIsNull()
    {
        // Arrange
        var appBuilder = DistributedApplication.CreateBuilder();
        var devuiBuilder = appBuilder.AddDevUI("devui");
        var agentService = CreateMockAgentServiceBuilder(appBuilder, "writer-agent");

        // Act
        devuiBuilder.WithAgentService(agentService);

        // Assert
        var annotation = devuiBuilder.Resource.Annotations
            .OfType<AgentServiceAnnotation>()
            .First();
        Assert.Null(annotation.EntityIdPrefix);
    }

    #endregion

    #region Chaining Tests

    /// <summary>
    /// Verifies that WithAgentService returns the builder for chaining.
    /// </summary>
    [Fact]
    public void WithAgentService_ReturnsSameBuilder_ForChaining()
    {
        // Arrange
        var appBuilder = DistributedApplication.CreateBuilder();
        var devuiBuilder = appBuilder.AddDevUI("devui");
        var agentService = CreateMockAgentServiceBuilder(appBuilder, "writer-agent");

        // Act
        var result = devuiBuilder.WithAgentService(agentService);

        // Assert
        Assert.Same(devuiBuilder, result);
    }

    /// <summary>
    /// Verifies that multiple WithAgentService calls can be chained.
    /// </summary>
    [Fact]
    public void WithAgentService_MultipleCalls_AddsMultipleAnnotations()
    {
        // Arrange
        var appBuilder = DistributedApplication.CreateBuilder();
        var devuiBuilder = appBuilder.AddDevUI("devui");
        var writerService = CreateMockAgentServiceBuilder(appBuilder, "writer-agent");
        var editorService = CreateMockAgentServiceBuilder(appBuilder, "editor-agent");

        // Act
        devuiBuilder
            .WithAgentService(writerService)
            .WithAgentService(editorService);

        // Assert
        var annotations = devuiBuilder.Resource.Annotations
            .OfType<AgentServiceAnnotation>()
            .ToList();
        Assert.Equal(2, annotations.Count);
        Assert.Contains(annotations, a => a.AgentService.Name == "writer-agent");
        Assert.Contains(annotations, a => a.AgentService.Name == "editor-agent");
    }

    /// <summary>
    /// Verifies that AddDevUI returns a builder that can be chained with WithAgentService.
    /// </summary>
    [Fact]
    public void AddDevUI_CanChainWithAgentService()
    {
        // Arrange
        var appBuilder = DistributedApplication.CreateBuilder();
        var agentService = CreateMockAgentServiceBuilder(appBuilder, "writer-agent");

        // Act - Chain AddDevUI with WithAgentService
        var result = appBuilder.AddDevUI("devui").WithAgentService(agentService);

        // Assert
        Assert.NotNull(result);
        var annotation = result.Resource.Annotations
            .OfType<AgentServiceAnnotation>()
            .FirstOrDefault();
        Assert.NotNull(annotation);
    }

    #endregion

    #region Relationship Tests

    /// <summary>
    /// Verifies that WithAgentService creates a relationship annotation.
    /// </summary>
    [Fact]
    public void WithAgentService_CreatesRelationshipAnnotation()
    {
        // Arrange
        var appBuilder = DistributedApplication.CreateBuilder();
        var devuiBuilder = appBuilder.AddDevUI("devui");
        var agentService = CreateMockAgentServiceBuilder(appBuilder, "writer-agent");

        // Act
        devuiBuilder.WithAgentService(agentService);

        // Assert
        var relationship = devuiBuilder.Resource.Annotations
            .OfType<ResourceRelationshipAnnotation>()
            .FirstOrDefault();
        Assert.NotNull(relationship);
        Assert.Equal("agent-backend", relationship.Type);
    }

    /// <summary>
    /// Verifies that multiple WithAgentService calls create multiple relationship annotations.
    /// </summary>
    [Fact]
    public void WithAgentService_MultipleCalls_CreatesMultipleRelationships()
    {
        // Arrange
        var appBuilder = DistributedApplication.CreateBuilder();
        var devuiBuilder = appBuilder.AddDevUI("devui");
        var writerService = CreateMockAgentServiceBuilder(appBuilder, "writer-agent");
        var editorService = CreateMockAgentServiceBuilder(appBuilder, "editor-agent");

        // Act
        devuiBuilder
            .WithAgentService(writerService)
            .WithAgentService(editorService);

        // Assert
        var relationships = devuiBuilder.Resource.Annotations
            .OfType<ResourceRelationshipAnnotation>()
            .ToList();
        Assert.Equal(2, relationships.Count);
        Assert.All(relationships, r => Assert.Equal("agent-backend", r.Type));
    }

    #endregion

    #region Agent Metadata Tests

    /// <summary>
    /// Verifies that agent description is preserved when specified.
    /// </summary>
    [Fact]
    public void WithAgentService_AgentWithDescription_PreservesDescription()
    {
        // Arrange
        var appBuilder = DistributedApplication.CreateBuilder();
        var devuiBuilder = appBuilder.AddDevUI("devui");
        var agentService = CreateMockAgentServiceBuilder(appBuilder, "writer-agent");
        var agents = new[] { new AgentEntityInfo("writer", "Writes creative stories") };

        // Act
        devuiBuilder.WithAgentService(agentService, agents: agents);

        // Assert
        var annotation = devuiBuilder.Resource.Annotations
            .OfType<AgentServiceAnnotation>()
            .First();
        Assert.Equal("Writes creative stories", annotation.Agents[0].Description);
    }

    /// <summary>
    /// Verifies that custom agent properties are preserved.
    /// </summary>
    [Fact]
    public void WithAgentService_CustomAgentProperties_ArePreserved()
    {
        // Arrange
        var appBuilder = DistributedApplication.CreateBuilder();
        var devuiBuilder = appBuilder.AddDevUI("devui");
        var agentService = CreateMockAgentServiceBuilder(appBuilder, "custom-service");
        var agents = new[]
        {
            new AgentEntityInfo("custom-agent")
            {
                Name = "Custom Display Name",
                Type = "workflow",
                Framework = "custom_framework"
            }
        };

        // Act
        devuiBuilder.WithAgentService(agentService, agents: agents);

        // Assert
        var annotation = devuiBuilder.Resource.Annotations
            .OfType<AgentServiceAnnotation>()
            .First();
        var agent = annotation.Agents[0];
        Assert.Equal("custom-agent", agent.Id);
        Assert.Equal("Custom Display Name", agent.Name);
        Assert.Equal("workflow", agent.Type);
        Assert.Equal("custom_framework", agent.Framework);
    }

    /// <summary>
    /// Verifies that empty agents array can be explicitly provided and is respected.
    /// </summary>
    [Fact]
    public void WithAgentService_EmptyAgentsArray_UsesEmptyArray()
    {
        // Arrange
        var appBuilder = DistributedApplication.CreateBuilder();
        var devuiBuilder = appBuilder.AddDevUI("devui");
        var agentService = CreateMockAgentServiceBuilder(appBuilder, "writer-agent");
        var emptyAgents = Array.Empty<AgentEntityInfo>();

        // Act
        devuiBuilder.WithAgentService(agentService, agents: emptyAgents);

        // Assert
        var annotation = devuiBuilder.Resource.Annotations
            .OfType<AgentServiceAnnotation>()
            .First();
        // When explicitly passing an empty array, the extension method respects it
        // This is the expected behavior - explicit empty means "discover at runtime"
        Assert.Empty(annotation.Agents);
    }

    #endregion

    #region Edge Case Tests

    /// <summary>
    /// Verifies that AddDevUI can be called multiple times with different names.
    /// </summary>
    [Fact]
    public void AddDevUI_MultipleCalls_CreatesSeparateResources()
    {
        // Arrange
        var appBuilder = DistributedApplication.CreateBuilder();

        // Act
        var devui1 = appBuilder.AddDevUI("devui1");
        var devui2 = appBuilder.AddDevUI("devui2");

        // Assert
        Assert.NotSame(devui1.Resource, devui2.Resource);
        Assert.Equal("devui1", devui1.Resource.Name);
        Assert.Equal("devui2", devui2.Resource.Name);
    }

    /// <summary>
    /// Verifies that same agent service can be added to multiple DevUI resources.
    /// </summary>
    [Fact]
    public void WithAgentService_SameServiceToMultipleDevUI_Works()
    {
        // Arrange
        var appBuilder = DistributedApplication.CreateBuilder();
        var devui1 = appBuilder.AddDevUI("devui1");
        var devui2 = appBuilder.AddDevUI("devui2");
        var agentService = CreateMockAgentServiceBuilder(appBuilder, "shared-agent");

        // Act
        devui1.WithAgentService(agentService);
        devui2.WithAgentService(agentService);

        // Assert
        var annotation1 = devui1.Resource.Annotations.OfType<AgentServiceAnnotation>().Single();
        var annotation2 = devui2.Resource.Annotations.OfType<AgentServiceAnnotation>().Single();
        Assert.Same(annotation1.AgentService, annotation2.AgentService);
    }

    /// <summary>
    /// Verifies that WithAgentService works with different entity ID prefixes for the same service.
    /// </summary>
    [Fact]
    public void WithAgentService_DifferentPrefixesToDifferentDevUI_Works()
    {
        // Arrange
        var appBuilder = DistributedApplication.CreateBuilder();
        var devui1 = appBuilder.AddDevUI("devui1");
        var devui2 = appBuilder.AddDevUI("devui2");
        var agentService = CreateMockAgentServiceBuilder(appBuilder, "writer-agent");

        // Act
        devui1.WithAgentService(agentService, entityIdPrefix: "prefix1");
        devui2.WithAgentService(agentService, entityIdPrefix: "prefix2");

        // Assert
        var annotation1 = devui1.Resource.Annotations.OfType<AgentServiceAnnotation>().Single();
        var annotation2 = devui2.Resource.Annotations.OfType<AgentServiceAnnotation>().Single();
        Assert.Equal("prefix1", annotation1.EntityIdPrefix);
        Assert.Equal("prefix2", annotation2.EntityIdPrefix);
    }

    #endregion

    #region Helper Methods

    /// <summary>
    /// Creates a mock agent service builder for testing.
    /// Uses a minimal resource implementation that satisfies IResourceWithEndpoints.
    /// </summary>
    private static IResourceBuilder<IResourceWithEndpoints> CreateMockAgentServiceBuilder(
        IDistributedApplicationBuilder appBuilder,
        string name)
    {
        // Create a mock resource that implements IResourceWithEndpoints
        var mockResource = new Mock<IResourceWithEndpoints>();
        mockResource.Setup(r => r.Name).Returns(name);
        mockResource.Setup(r => r.Annotations).Returns(new ResourceAnnotationCollection());

        var mockBuilder = new Mock<IResourceBuilder<IResourceWithEndpoints>>();
        mockBuilder.Setup(b => b.Resource).Returns(mockResource.Object);
        mockBuilder.Setup(b => b.ApplicationBuilder).Returns(appBuilder);

        return mockBuilder.Object;
    }

    #endregion
}
