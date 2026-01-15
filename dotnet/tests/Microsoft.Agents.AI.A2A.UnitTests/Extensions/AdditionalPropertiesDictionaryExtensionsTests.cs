// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.A2A.UnitTests;

/// <summary>
/// Unit tests for the <see cref="AdditionalPropertiesDictionaryExtensions"/> class.
/// </summary>
public sealed class AdditionalPropertiesDictionaryExtensionsTests
{
    [Fact]
    public void ToA2AMetadata_WithNullAdditionalProperties_ReturnsNull()
    {
        // Arrange
        AdditionalPropertiesDictionary? additionalProperties = null;

        // Act
        Dictionary<string, JsonElement>? result = additionalProperties.ToA2AMetadata();

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public void ToA2AMetadata_WithEmptyAdditionalProperties_ReturnsNull()
    {
        // Arrange
        AdditionalPropertiesDictionary additionalProperties = [];

        // Act
        Dictionary<string, JsonElement>? result = additionalProperties.ToA2AMetadata();

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public void ToA2AMetadata_WithStringValue_ReturnsMetadataWithJsonElement()
    {
        // Arrange
        AdditionalPropertiesDictionary additionalProperties = new()
        {
            { "stringKey", "stringValue" }
        };

        // Act
        Dictionary<string, JsonElement>? result = additionalProperties.ToA2AMetadata();

        // Assert
        Assert.NotNull(result);
        Assert.Single(result);
        Assert.True(result.ContainsKey("stringKey"));
        Assert.Equal("stringValue", result["stringKey"].GetString());
    }

    [Fact]
    public void ToA2AMetadata_WithNumericValue_ReturnsMetadataWithJsonElement()
    {
        // Arrange
        AdditionalPropertiesDictionary additionalProperties = new()
        {
            { "numberKey", 42 }
        };

        // Act
        Dictionary<string, JsonElement>? result = additionalProperties.ToA2AMetadata();

        // Assert
        Assert.NotNull(result);
        Assert.Single(result);
        Assert.True(result.ContainsKey("numberKey"));
        Assert.Equal(42, result["numberKey"].GetInt32());
    }

    [Fact]
    public void ToA2AMetadata_WithBooleanValue_ReturnsMetadataWithJsonElement()
    {
        // Arrange
        AdditionalPropertiesDictionary additionalProperties = new()
        {
            { "booleanKey", true }
        };

        // Act
        Dictionary<string, JsonElement>? result = additionalProperties.ToA2AMetadata();

        // Assert
        Assert.NotNull(result);
        Assert.Single(result);
        Assert.True(result.ContainsKey("booleanKey"));
        Assert.True(result["booleanKey"].GetBoolean());
    }

    [Fact]
    public void ToA2AMetadata_WithMultipleProperties_ReturnsMetadataWithAllProperties()
    {
        // Arrange
        AdditionalPropertiesDictionary additionalProperties = new()
        {
            { "stringKey", "stringValue" },
            { "numberKey", 42 },
            { "booleanKey", true }
        };

        // Act
        Dictionary<string, JsonElement>? result = additionalProperties.ToA2AMetadata();

        // Assert
        Assert.NotNull(result);
        Assert.Equal(3, result.Count);

        Assert.True(result.ContainsKey("stringKey"));
        Assert.Equal("stringValue", result["stringKey"].GetString());

        Assert.True(result.ContainsKey("numberKey"));
        Assert.Equal(42, result["numberKey"].GetInt32());

        Assert.True(result.ContainsKey("booleanKey"));
        Assert.True(result["booleanKey"].GetBoolean());
    }

    [Fact]
    public void ToA2AMetadata_WithArrayValue_ReturnsMetadataWithJsonElement()
    {
        // Arrange
        int[] arrayValue = [1, 2, 3];
        AdditionalPropertiesDictionary additionalProperties = new()
        {
            { "arrayKey", arrayValue }
        };

        // Act
        Dictionary<string, JsonElement>? result = additionalProperties.ToA2AMetadata();

        // Assert
        Assert.NotNull(result);
        Assert.Single(result);
        Assert.True(result.ContainsKey("arrayKey"));
        Assert.Equal(JsonValueKind.Array, result["arrayKey"].ValueKind);
        Assert.Equal(3, result["arrayKey"].GetArrayLength());
    }

    [Fact]
    public void ToA2AMetadata_WithNullValue_ReturnsMetadataWithNullJsonElement()
    {
        // Arrange
        AdditionalPropertiesDictionary additionalProperties = new()
        {
            { "nullKey", null! }
        };

        // Act
        Dictionary<string, JsonElement>? result = additionalProperties.ToA2AMetadata();

        // Assert
        Assert.NotNull(result);
        Assert.Single(result);
        Assert.True(result.ContainsKey("nullKey"));
        Assert.Equal(JsonValueKind.Null, result["nullKey"].ValueKind);
    }

    [Fact]
    public void ToA2AMetadata_WithJsonElementValue_ReturnsMetadataWithJsonElement()
    {
        // Arrange
        JsonElement jsonElement = JsonSerializer.SerializeToElement(new { name = "test", value = 123 });
        AdditionalPropertiesDictionary additionalProperties = new()
        {
            { "jsonElementKey", jsonElement }
        };

        // Act
        Dictionary<string, JsonElement>? result = additionalProperties.ToA2AMetadata();

        // Assert
        Assert.NotNull(result);
        Assert.Single(result);
        Assert.True(result.ContainsKey("jsonElementKey"));
        Assert.Equal(JsonValueKind.Object, result["jsonElementKey"].ValueKind);
        Assert.Equal("test", result["jsonElementKey"].GetProperty("name").GetString());
        Assert.Equal(123, result["jsonElementKey"].GetProperty("value").GetInt32());
    }
}
