// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;

namespace Microsoft.Agents.AI.Skills.Mcp.UnitTests;

public sealed class JsonElementComparerTests
{
    [Theory]
    [InlineData("null", "null")]
    [InlineData("true", "true")]
    [InlineData("1", "1.0e0")]
    [InlineData("[1,true,null]", "[1.0e0,true,null]")]
    [InlineData("""{"first":1,"second":2}""", """{"second":2,"first":1}""")]
    [InlineData("""{"value":1}""", """{"value":1.0e0}""")]
    [InlineData("""{"value":0}""", """{"value":-0.0}""")]
    [InlineData("""{"value":1e9999}""", """{"value":10e9998}""")]
    [InlineData("""{"value":0.123456789012345678901234567890}""", """{"value":0.1234567890123456789012345678900}""")]
    [InlineData("""{"value":"\u0061"}""", """{"value":"a"}""")]
    [InlineData("""{"nested":[{"a":null,"b":true},[],{}]}""", """{"nested":[{"b":true,"a":null},[],{}]}""")]
    [InlineData("""{"value":1,"value":1}""", """{"value":1,"value":1}""")]
    [InlineData("""{"value":1,"value":2}""", """{"value":1,"value":2}""")]
    [InlineData("""{"value":1,"\u0076alue":1}""", """{"value":1,"value":1}""")]
    [InlineData("""{"items":[{"value":1,"value":1}]}""", """{"items":[{"value":1,"value":1}]}""")]
    public void DeepEquals_EquivalentValues_ReturnsTrueAndNull(string advertised, string fetched)
    {
        // Arrange
        using JsonDocument expected = JsonDocument.Parse(advertised);
        using JsonDocument actual = JsonDocument.Parse(fetched);

        // Act
        bool areEqual = JsonElementComparer.DeepEquals(expected.RootElement, actual.RootElement, out string? differencePath);

        // Assert
        Assert.True(areEqual);
        Assert.Null(differencePath);
    }

    [Theory]
    [InlineData("""{"value":1}""", """{"value":"1"}""", "/value")]
    [InlineData("""{"value":true}""", """{"value":false}""", "/value")]
    [InlineData("""{"value":null}""", "{}", "/value")]
    [InlineData("{}", """{"value":null}""", "/value")]
    [InlineData("""{"Value":1}""", """{"value":1}""", "/value")]
    [InlineData("""{"value":"text"}""", """{"value":" text "}""", "/value")]
    [InlineData("""{"value":9007199254740992}""", """{"value":9007199254740993}""", "/value")]
    [InlineData("""{"value":0.123456789012345678901234567890}""", """{"value":0.123456789012345678901234567891}""", "/value")]
    [InlineData("""{"items":[1,2]}""", """{"items":[2,1]}""", "/items/0")]
    [InlineData("""{"items":[1,2]}""", """{"items":[1]}""", "/items/1")]
    [InlineData("""{"items":[1]}""", """{"items":[1,2]}""", "/items/1")]
    [InlineData("""{"items":[{"value":true}]}""", """{"items":[{"value":null}]}""", "/items/0/value")]
    [InlineData("""{"a/b~c":{"":1}}""", """{"a/b~c":{"":2}}""", "/a~1b~0c/")]
    [InlineData("""{"value":1,"value":1}""", """{"value":1}""", "/value")]
    [InlineData("""{"value":1}""", """{"value":1,"value":1}""", "/value")]
    [InlineData("""{"nested":{"value":1,"value":2}}""", """{"nested":{"value":2}}""", "/nested/value")]
    [InlineData("{}", "[]", "")]
    public void DeepEquals_DifferentOrAmbiguousValues_ReturnsFalseAndJsonPointer(string advertised, string fetched, string expectedPath)
    {
        // Arrange
        using JsonDocument expected = JsonDocument.Parse(advertised);
        using JsonDocument actual = JsonDocument.Parse(fetched);

        // Act
        bool areEqual = JsonElementComparer.DeepEquals(expected.RootElement, actual.RootElement, out string? differencePath);

        // Assert
        Assert.False(areEqual);
        Assert.Equal(expectedPath, differencePath);
    }
}
