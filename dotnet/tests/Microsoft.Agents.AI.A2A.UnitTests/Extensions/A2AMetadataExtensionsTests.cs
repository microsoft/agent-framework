// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using A2A;

namespace Microsoft.Agents.AI.A2A.UnitTests;

/// <summary>
/// Unit tests for the <see cref="A2AMetadataExtensions"/> class.
/// </summary>
public sealed class A2AMetadataExtensionsTests
{
    [Fact]
    public void ToAdditionalProperties_WithNullMetadata_ReturnsNull()
    {
        // Arrange
        Dictionary<string, JsonElement>? metadata = null;

        // Act
        var result = metadata.ToAdditionalProperties();

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public void ToAdditionalProperties_WithEmptyMetadata_ReturnsNull()
    {
        // Arrange
        var metadata = new Dictionary<string, JsonElement>();

        // Act
        var result = metadata.ToAdditionalProperties();

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public void ToAdditionalProperties_WithMultipleProperties_ReturnsAdditionalPropertiesDictionaryWithAllProperties()
    {
        // Arrange
        var metadata = new Dictionary<string, JsonElement>
        {
            { "stringKey", JsonSerializer.SerializeToElement("stringValue") },
            { "numberKey", JsonSerializer.SerializeToElement(42) },
            { "booleanKey", JsonSerializer.SerializeToElement(true) }
        };

        // Act
        var result = metadata.ToAdditionalProperties();

        // Assert
        Assert.NotNull(result);
        Assert.Equal(3, result.Count);

        Assert.True(result.ContainsKey("stringKey"));
        Assert.Equal("stringValue", ((JsonElement)result["stringKey"]!).GetString());

        Assert.True(result.ContainsKey("numberKey"));
        Assert.Equal(42, ((JsonElement)result["numberKey"]!).GetInt32());

        Assert.True(result.ContainsKey("booleanKey"));
        Assert.True(((JsonElement)result["booleanKey"]!).GetBoolean());
    }
}
