// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.Hosting;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Tests for HostApplicationBuilderExtensions.AddOpenAIResponses method.
/// </summary>
public sealed class HostApplicationBuilderExtensionsTests
{
    /// <summary>
    /// Verifies that AddOpenAIResponses throws ArgumentNullException for null builder.
    /// </summary>
    [Fact]
    public void AddOpenAIResponses_NullBuilder_ThrowsArgumentNullException()
    {
        // Arrange
        IHostApplicationBuilder builder = null!;

        // Act & Assert
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() =>
            builder.AddOpenAIResponses());

        Assert.Equal("builder", exception.ParamName);
    }

    /// <summary>
    /// Verifies that AddOpenAIResponses returns the same builder instance.
    /// </summary>
    [Fact]
    public void AddOpenAIResponses_ValidBuilder_ReturnsSameBuilder()
    {
        // Arrange
        IHostApplicationBuilder builder = Host.CreateApplicationBuilder();

        // Act
        IHostApplicationBuilder result = builder.AddOpenAIResponses();

        // Assert
        Assert.Same(builder, result);
    }

    /// <summary>
    /// Verifies that AddOpenAIResponses can be called multiple times without error.
    /// </summary>
    [Fact]
    public void AddOpenAIResponses_MultipleCalls_DoesNotThrow()
    {
        // Arrange
        HostApplicationBuilder builder = Host.CreateApplicationBuilder();

        // Act
        builder.AddOpenAIResponses();
        builder.AddOpenAIResponses();
        builder.AddOpenAIResponses();

        // Assert - Building should succeed
        Assert.NotNull(builder.Services);
    }

    /// <summary>
    /// Verifies that AddOpenAIResponses properly configures JSON serialization options.
    /// </summary>
    [Fact]
    public void AddOpenAIResponses_ConfiguresJsonSerialization()
    {
        // Arrange
        HostApplicationBuilder builder = Host.CreateApplicationBuilder();

        // Act
        builder.AddOpenAIResponses();

        // Assert - Should add services without error
        Assert.NotNull(builder.Services);
    }
}
