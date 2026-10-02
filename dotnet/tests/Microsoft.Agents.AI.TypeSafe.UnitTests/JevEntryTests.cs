// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;

namespace Microsoft.Agents.AI.TypeSafe.UnitTests;

public sealed class JevEntryTests
{
    [Fact]
    public void Conversions_FromTextAndJson_KeepTheValue()
    {
        // Arrange
        using JsonDocument document = JsonDocument.Parse("""{ "question": "Is `order` paid?" }""");

        // Act
        JevEntry text = "Is this urgent?";
        JevEntry nullText = (string?)null;
        var json = (JevEntry)document.RootElement;

        // Assert
        Assert.Equal(JsonValueKind.String, text.Kind);
        Assert.Equal("Is this urgent?", text.Text);
        Assert.Equal("Is this urgent?", text.ToString());
        Assert.True(nullText.IsNull);
        Assert.Equal(JevEntry.Null, nullText);
        Assert.Equal(JsonValueKind.Object, json.Kind);
        Assert.Null(json.Text);
        Assert.Equal("""{ "question": "Is `order` paid?" }""", json.ToString());
    }

    [Fact]
    public void Default_IsTheNullEntry()
    {
        // Act
        JevEntry entry = default;

        // Assert
        Assert.True(entry.IsNull);
        Assert.Equal(JsonValueKind.Null, entry.Kind);
        Assert.Null(entry.Json);
        Assert.Equal(string.Empty, entry.ToString());
    }

    [Fact]
    public void Json_OutlivesTheDocumentItCameFrom()
    {
        // Arrange
        JevEntry entry;
        using (JsonDocument document = JsonDocument.Parse("""["a", "b"]"""))
        {
            entry = JevEntry.FromJsonElement(document.RootElement);
        }

        // Act & Assert
        Assert.Equal(2, entry.Json!.Value.GetArrayLength());
    }

    [Theory]
    [InlineData("42")]
    [InlineData("true")]
    [InlineData("false")]
    public void FromJsonElement_NumberOrBoolean_Throws(string json)
    {
        // Arrange
        using JsonDocument document = JsonDocument.Parse(json);
        JsonElement element = document.RootElement;

        // Act & Assert
        Assert.Throws<ArgumentException>(() => (JevEntry)element);
        Assert.Throws<ArgumentException>(() => JevEntry.FromJsonElement(element));
    }

    [Fact]
    public void Equality_ComparesJsonValuesRegardlessOfPropertyOrder()
    {
        // Arrange
        using JsonDocument first = JsonDocument.Parse("""{ "a": 1, "b": [true] }""");
        using JsonDocument second = JsonDocument.Parse("""{ "b": [true], "a": 1 }""");
        using JsonDocument other = JsonDocument.Parse("""{ "a": 2 }""");
        var left = (JevEntry)first.RootElement;
        var right = (JevEntry)second.RootElement;

        // Act & Assert
        Assert.True(left == right);
        Assert.Equal(left.GetHashCode(), right.GetHashCode());
        Assert.True(left != (JevEntry)other.RootElement);
        Assert.Equal((JevEntry)"same", (JevEntry)"same");
        Assert.NotEqual((JevEntry)"same", JevEntry.Null);
    }

    [Theory]
    [InlineData("\"text\"", JsonValueKind.String)]
    [InlineData("{\"k\":\"v\"}", JsonValueKind.Object)]
    [InlineData("[\"x\"]", JsonValueKind.Array)]
    [InlineData("null", JsonValueKind.Null)]
    public void Serialization_RoundTripsTheJsonValue(string json, JsonValueKind kind)
    {
        // Act
        var entry = (JevEntry)JsonSerializer.Deserialize(json, JevJsonUtilities.Options.GetTypeInfo(typeof(JevEntry)))!;
        string written = JsonSerializer.Serialize(entry, JevJsonUtilities.Options.GetTypeInfo(typeof(JevEntry)));

        // Assert
        Assert.Equal(kind, entry.Kind);
        Assert.Equal(json, written);
    }

    [Theory]
    [InlineData("42")]
    [InlineData("true")]
    public void Deserialization_NumberOrBoolean_Throws(string json)
    {
        // Act & Assert
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize(json, JevJsonUtilities.Options.GetTypeInfo(typeof(JevEntry))));
    }
}
