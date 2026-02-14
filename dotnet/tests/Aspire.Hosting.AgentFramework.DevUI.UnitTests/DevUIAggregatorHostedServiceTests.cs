// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using Aspire.Hosting.ApplicationModel;
using Microsoft.AspNetCore.Http;

namespace Aspire.Hosting.AgentFramework.DevUI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="DevUIAggregatorHostedService"/> class.
/// </summary>
public class DevUIAggregatorHostedServiceTests
{
    #region RewriteAgentIdInQueryString Tests

    /// <summary>
    /// Verifies that RewriteAgentIdInQueryString returns empty string when query string has no value.
    /// </summary>
    [Fact]
    public void RewriteAgentIdInQueryString_EmptyQueryString_ReturnsEmptyString()
    {
        // Arrange
        var queryString = QueryString.Empty;

        // Act
        var result = DevUIAggregatorHostedService.RewriteAgentIdInQueryString(queryString, "writer");

        // Assert
        Assert.Equal(string.Empty, result);
    }

    /// <summary>
    /// Verifies that RewriteAgentIdInQueryString rewrites agent_id to the un-prefixed value.
    /// </summary>
    [Fact]
    public void RewriteAgentIdInQueryString_WithPrefixedAgentId_RewritesToUnprefixed()
    {
        // Arrange
        var queryString = new QueryString("?agent_id=writer-agent%2Fwriter");

        // Act
        var result = DevUIAggregatorHostedService.RewriteAgentIdInQueryString(queryString, "writer");

        // Assert
        Assert.Contains("agent_id=writer", result);
        Assert.DoesNotContain("writer-agent", result);
    }

    /// <summary>
    /// Verifies that RewriteAgentIdInQueryString preserves other query parameters.
    /// </summary>
    [Fact]
    public void RewriteAgentIdInQueryString_WithOtherParams_PreservesOtherParams()
    {
        // Arrange
        var queryString = new QueryString("?agent_id=writer-agent%2Fwriter&conversation_id=123&page=5");

        // Act
        var result = DevUIAggregatorHostedService.RewriteAgentIdInQueryString(queryString, "writer");

        // Assert
        Assert.Contains("agent_id=writer", result);
        Assert.Contains("conversation_id=123", result);
        Assert.Contains("page=5", result);
    }

    /// <summary>
    /// Verifies that RewriteAgentIdInQueryString works when agent_id is not the first parameter.
    /// </summary>
    [Fact]
    public void RewriteAgentIdInQueryString_AgentIdNotFirst_StillRewrites()
    {
        // Arrange
        var queryString = new QueryString("?page=1&agent_id=editor-agent%2Feditor&limit=10");

        // Act
        var result = DevUIAggregatorHostedService.RewriteAgentIdInQueryString(queryString, "editor");

        // Assert
        Assert.Contains("agent_id=editor", result);
        Assert.DoesNotContain("editor-agent", result);
    }

    /// <summary>
    /// Verifies that RewriteAgentIdInQueryString handles special characters in actual agent ID.
    /// </summary>
    [Fact]
    public void RewriteAgentIdInQueryString_SpecialCharsInAgentId_UrlEncodesCorrectly()
    {
        // Arrange
        var queryString = new QueryString("?agent_id=prefix%2Fmy-agent");

        // Act
        var result = DevUIAggregatorHostedService.RewriteAgentIdInQueryString(queryString, "my-agent");

        // Assert
        // The result should contain the agent_id with the value properly encoded if needed
        Assert.Contains("agent_id=my-agent", result);
    }

    /// <summary>
    /// Verifies that RewriteAgentIdInQueryString handles an agent_id with no prefix.
    /// </summary>
    [Fact]
    public void RewriteAgentIdInQueryString_NoPrefix_SetsDirectly()
    {
        // Arrange
        var queryString = new QueryString("?agent_id=simple");

        // Act
        var result = DevUIAggregatorHostedService.RewriteAgentIdInQueryString(queryString, "new-value");

        // Assert
        Assert.Contains("agent_id=new-value", result);
        Assert.DoesNotContain("simple", result);
    }

    /// <summary>
    /// Verifies that RewriteAgentIdInQueryString adds agent_id even if not originally present.
    /// </summary>
    [Fact]
    public void RewriteAgentIdInQueryString_NoAgentId_AddsAgentId()
    {
        // Arrange
        var queryString = new QueryString("?page=1&limit=10");

        // Act
        var result = DevUIAggregatorHostedService.RewriteAgentIdInQueryString(queryString, "writer");

        // Assert
        Assert.Contains("agent_id=writer", result);
        Assert.Contains("page=1", result);
        Assert.Contains("limit=10", result);
    }

    /// <summary>
    /// Verifies that RewriteAgentIdInQueryString returns proper format starting with ?.
    /// </summary>
    [Fact]
    public void RewriteAgentIdInQueryString_ValidQuery_ReturnsQueryStringFormat()
    {
        // Arrange
        var queryString = new QueryString("?agent_id=test");

        // Act
        var result = DevUIAggregatorHostedService.RewriteAgentIdInQueryString(queryString, "writer");

        // Assert
        Assert.StartsWith("?", result);
    }

    #endregion

    #region Backend Resolution Behavior Tests

    /// <summary>
    /// Verifies that ResolveBackends returns empty dictionary when no annotations are present.
    /// These tests verify the expected behavior of the aggregator via the DevUI resource annotations.
    /// </summary>
    [Fact]
    public void DevUIResource_NoAnnotations_ResolveBackendsReturnsEmpty()
    {
        // Arrange
        var builder = DistributedApplication.CreateBuilder();
        var devui = builder.AddDevUI("devui");

        // Assert - no AgentServiceAnnotation means no backends
        var annotations = devui.Resource.Annotations
            .OfType<AgentServiceAnnotation>()
            .ToList();

        Assert.Empty(annotations);
    }

    /// <summary>
    /// Verifies that WithAgentService adds proper annotations for backend resolution.
    /// </summary>
    [Fact]
    public void WithAgentService_AddsAnnotation_ForBackendResolution()
    {
        // Arrange
        var builder = DistributedApplication.CreateBuilder();
        var devui = builder.AddDevUI("devui");
        var agentService = CreateMockAgentServiceBuilder(builder, "writer-agent");

        // Act
        devui.WithAgentService(agentService);

        // Assert
        var annotation = devui.Resource.Annotations
            .OfType<AgentServiceAnnotation>()
            .FirstOrDefault();

        Assert.NotNull(annotation);
        Assert.Equal("writer-agent", annotation.AgentService.Name);
    }

    /// <summary>
    /// Verifies that custom EntityIdPrefix is properly stored in the annotation.
    /// </summary>
    [Fact]
    public void WithAgentService_CustomPrefix_StoresInAnnotation()
    {
        // Arrange
        var builder = DistributedApplication.CreateBuilder();
        var devui = builder.AddDevUI("devui");
        var agentService = CreateMockAgentServiceBuilder(builder, "writer-agent");

        // Act
        devui.WithAgentService(agentService, entityIdPrefix: "custom-writer");

        // Assert
        var annotation = devui.Resource.Annotations
            .OfType<AgentServiceAnnotation>()
            .First();

        Assert.Equal("custom-writer", annotation.EntityIdPrefix);
    }

    /// <summary>
    /// Verifies that multiple agent services create multiple annotations for backend resolution.
    /// </summary>
    [Fact]
    public void WithAgentService_MultipleServices_CreatesMultipleAnnotations()
    {
        // Arrange
        var builder = DistributedApplication.CreateBuilder();
        var devui = builder.AddDevUI("devui");
        var writerService = CreateMockAgentServiceBuilder(builder, "writer-agent");
        var editorService = CreateMockAgentServiceBuilder(builder, "editor-agent");

        // Act
        devui.WithAgentService(writerService);
        devui.WithAgentService(editorService);

        // Assert
        var annotations = devui.Resource.Annotations
            .OfType<AgentServiceAnnotation>()
            .ToList();

        Assert.Equal(2, annotations.Count);
        Assert.Contains(annotations, a => a.AgentService.Name == "writer-agent");
        Assert.Contains(annotations, a => a.AgentService.Name == "editor-agent");
    }

    #endregion

    #region Entity ID Parsing Tests

    /// <summary>
    /// Verifies the expected format for prefixed entity IDs in the aggregator.
    /// </summary>
    [Theory]
    [InlineData("writer-agent/writer", "writer-agent", "writer")]
    [InlineData("editor-agent/editor", "editor-agent", "editor")]
    [InlineData("custom/my-agent", "custom", "my-agent")]
    [InlineData("prefix/sub/path", "prefix", "sub/path")]
    public void PrefixedEntityId_Format_ExtractsCorrectly(string prefixedId, string expectedPrefix, string expectedRest)
    {
        // This test documents the expected format for prefixed entity IDs
        // The aggregator uses "prefix/entityId" format where:
        // - prefix is typically the resource name or custom prefix
        // - entityId is the original entity identifier from the backend

        var slashIndex = prefixedId.IndexOf('/');
        var prefix = prefixedId[..slashIndex];
        var rest = prefixedId[(slashIndex + 1)..];

        Assert.Equal(expectedPrefix, prefix);
        Assert.Equal(expectedRest, rest);
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
        var mockResource = new Moq.Mock<IResourceWithEndpoints>();
        mockResource.Setup(r => r.Name).Returns(name);
        mockResource.Setup(r => r.Annotations).Returns(new ResourceAnnotationCollection());

        var mockBuilder = new Moq.Mock<IResourceBuilder<IResourceWithEndpoints>>();
        mockBuilder.Setup(b => b.Resource).Returns(mockResource.Object);
        mockBuilder.Setup(b => b.ApplicationBuilder).Returns(appBuilder);

        return mockBuilder.Object;
    }

    #endregion
}
