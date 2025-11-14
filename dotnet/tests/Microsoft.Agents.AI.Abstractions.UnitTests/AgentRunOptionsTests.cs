// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Unit tests for the <see cref="AgentRunOptions"/> class.
/// </summary>
public class AgentRunOptionsTests
{
    [Fact]
    public void CloningConstructorCopiesProperties()
    {
        // Arrange
        var options = new AgentRunOptions
        {
            ContinuationToken = new object(),
            AllowBackgroundResponses = true,
            AdditionalProperties = new AdditionalPropertiesDictionary
            {
                ["key1"] = "value1",
                ["key2"] = 42
            }
        };

        // Act
        var clone = new AgentRunOptions(options);

        // Assert
        Assert.NotNull(clone);
        Assert.Same(options.ContinuationToken, clone.ContinuationToken);
        Assert.Equal(options.AllowBackgroundResponses, clone.AllowBackgroundResponses);
        Assert.NotNull(clone.AdditionalProperties);
        Assert.NotSame(options.AdditionalProperties, clone.AdditionalProperties);
        Assert.Equal("value1", clone.AdditionalProperties["key1"]);
        Assert.Equal(42, clone.AdditionalProperties["key2"]);
    }

    [Fact]
    public void CloningConstructorThrowsIfNull() =>
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new AgentRunOptions(null!));

    [Fact]
    public void JsonSerializationRoundtrips()
    {
        // Arrange
        var options = new AgentRunOptions
        {
            ContinuationToken = ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 }),
            AllowBackgroundResponses = true,
            AdditionalProperties = new AdditionalPropertiesDictionary
            {
                ["key1"] = "value1",
                ["key2"] = 42
            }
        };

        // Act
        string json = JsonSerializer.Serialize(options, AgentAbstractionsJsonUtilities.DefaultOptions);

        var deserialized = JsonSerializer.Deserialize<AgentRunOptions>(json, AgentAbstractionsJsonUtilities.DefaultOptions);

        // Assert
        Assert.NotNull(deserialized);
        Assert.Equivalent(ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 }), deserialized!.ContinuationToken);
        Assert.Equal(options.AllowBackgroundResponses, deserialized.AllowBackgroundResponses);
        Assert.NotNull(deserialized.AdditionalProperties);
        Assert.Equal(2, deserialized.AdditionalProperties.Count);
        Assert.True(deserialized.AdditionalProperties.TryGetValue("key1", out object? value1));
        Assert.IsType<JsonElement>(value1);
        Assert.Equal("value1", ((JsonElement)value1!).GetString());
        Assert.True(deserialized.AdditionalProperties.TryGetValue("key2", out object? value2));
        Assert.IsType<JsonElement>(value2);
        Assert.Equal(42, ((JsonElement)value2!).GetInt32());
    }
}
