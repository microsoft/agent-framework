// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Net.Sockets;
using Aspire.Hosting.ApplicationModel;

namespace Aspire.Hosting.AgentFramework.DevUI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="DevUIResource"/> class.
/// </summary>
public class DevUIResourceTests
{
    #region Constructor Tests

    /// <summary>
    /// Verifies that the resource name is correctly set.
    /// </summary>
    [Fact]
    public void Constructor_WithName_SetsName()
    {
        // Arrange & Act
        var resource = new DevUIResource("test-devui");

        // Assert
        Assert.Equal("test-devui", resource.Name);
    }

    /// <summary>
    /// Verifies that the resource implements IResourceWithEndpoints.
    /// </summary>
    [Fact]
    public void Resource_ImplementsIResourceWithEndpoints()
    {
        // Arrange & Act
        var resource = new DevUIResource("test-devui");

        // Assert
        Assert.IsAssignableFrom<IResourceWithEndpoints>(resource);
    }

    /// <summary>
    /// Verifies that the resource implements IResourceWithWaitSupport.
    /// </summary>
    [Fact]
    public void Resource_ImplementsIResourceWithWaitSupport()
    {
        // Arrange & Act
        var resource = new DevUIResource("test-devui");

        // Assert
        Assert.IsAssignableFrom<IResourceWithWaitSupport>(resource);
    }

    #endregion

    #region Endpoint Annotation Tests

    /// <summary>
    /// Verifies that the resource has an HTTP endpoint annotation when port is specified.
    /// </summary>
    [Fact]
    public void Constructor_WithPort_AddsEndpointAnnotation()
    {
        // Arrange & Act
        var resource = CreateResourceWithPort(8090);

        // Assert
        var endpoint = resource.Annotations.OfType<EndpointAnnotation>().FirstOrDefault();
        Assert.NotNull(endpoint);
        Assert.Equal("http", endpoint.Name);
        Assert.Equal(8090, endpoint.Port);
    }

    /// <summary>
    /// Verifies that the endpoint annotation has correct protocol type.
    /// </summary>
    [Fact]
    public void EndpointAnnotation_HasTcpProtocol()
    {
        // Arrange
        var resource = CreateResourceWithPort(8080);

        // Act
        var endpoint = resource.Annotations.OfType<EndpointAnnotation>().First();

        // Assert
        Assert.Equal(ProtocolType.Tcp, endpoint.Protocol);
    }

    /// <summary>
    /// Verifies that the endpoint annotation has HTTP URI scheme.
    /// </summary>
    [Fact]
    public void EndpointAnnotation_HasHttpUriScheme()
    {
        // Arrange
        var resource = CreateResourceWithPort(8080);

        // Act
        var endpoint = resource.Annotations.OfType<EndpointAnnotation>().First();

        // Assert
        Assert.Equal("http", endpoint.UriScheme);
    }

    /// <summary>
    /// Verifies that the endpoint is not proxied.
    /// </summary>
    [Fact]
    public void EndpointAnnotation_IsNotProxied()
    {
        // Arrange
        var resource = CreateResourceWithPort(8080);

        // Act
        var endpoint = resource.Annotations.OfType<EndpointAnnotation>().First();

        // Assert
        Assert.False(endpoint.IsProxied);
    }

    /// <summary>
    /// Verifies that the endpoint target host is localhost.
    /// </summary>
    [Fact]
    public void EndpointAnnotation_TargetHostIsLocalhost()
    {
        // Arrange
        var resource = CreateResourceWithPort(8080);

        // Act
        var endpoint = resource.Annotations.OfType<EndpointAnnotation>().First();

        // Assert
        Assert.Equal("localhost", endpoint.TargetHost);
    }

    /// <summary>
    /// Verifies that the endpoint has no fixed port when null is passed.
    /// </summary>
    [Fact]
    public void Constructor_WithNullPort_EndpointHasNullPort()
    {
        // Arrange & Act
        var resource = CreateResourceWithPort(null);

        // Assert
        var endpoint = resource.Annotations.OfType<EndpointAnnotation>().FirstOrDefault();
        Assert.NotNull(endpoint);
        Assert.Null(endpoint.Port);
    }

    #endregion

    #region PrimaryEndpoint Tests

    /// <summary>
    /// Verifies that PrimaryEndpoint returns an endpoint reference.
    /// </summary>
    [Fact]
    public void PrimaryEndpoint_ReturnsEndpointReference()
    {
        // Arrange
        var resource = CreateResourceWithPort(8080);

        // Act
        var endpoint = resource.PrimaryEndpoint;

        // Assert
        Assert.NotNull(endpoint);
        Assert.Same(resource, endpoint.Resource);
    }

    /// <summary>
    /// Verifies that PrimaryEndpoint returns the same instance on multiple calls.
    /// </summary>
    [Fact]
    public void PrimaryEndpoint_MultipleCalls_ReturnsSameInstance()
    {
        // Arrange
        var resource = CreateResourceWithPort(8080);

        // Act
        var endpoint1 = resource.PrimaryEndpoint;
        var endpoint2 = resource.PrimaryEndpoint;

        // Assert
        Assert.Same(endpoint1, endpoint2);
    }

    #endregion

    /// <summary>
    /// Creates a DevUIResource using reflection to access the internal constructor.
    /// This is necessary because the (name, port) constructor is internal.
    /// </summary>
    private static DevUIResource CreateResourceWithPort(int? port)
    {
        // Use reflection to call the internal constructor
        var constructorInfo = typeof(DevUIResource).GetConstructor(
            System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic,
            null,
            [typeof(string), typeof(int?)],
            null);

        if (constructorInfo is null)
        {
            throw new InvalidOperationException("Could not find internal DevUIResource constructor");
        }

        return (DevUIResource)constructorInfo.Invoke(["test-devui", port]);
    }
}
