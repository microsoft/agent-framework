// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.Extensions;

public sealed class JsonDocumentExtensionsTests
{
    [Fact]
    public void ParseRecord_Object_PrimitiveFields_Succeeds()
    {
        // Arrange
        VariableType recordType =
            VariableType.Record(
                [
                    ("text", new VariableType(typeof(string))),
                    ("numberInt", new VariableType(typeof(int))),
                    ("numberLong", new VariableType(typeof(long))),
                    ("numberDecimal", new VariableType(typeof(decimal))),
                    ("numberDouble", new VariableType(typeof(double))),
                    ("flag", new VariableType(typeof(bool))),
                    ("date", new VariableType(typeof(DateTime))),
                    ("time", new VariableType(typeof(TimeSpan)))
                ]);

        DateTime expectedDateTime = new(2024, 10, 01, 12, 34, 56, DateTimeKind.Utc);
        TimeSpan expectedTimeSpan = new(12, 34, 56);

        JsonDocument document = JsonDocument.Parse(
            """
            {
              "text": "hello",
              "numberInt": 7,
              "numberLong": 9223372036854775807,
              "numberDecimal": 12.5,
              "numberDouble": 9.75,
              "flag": true,
              "date": "2024-10-01T12:34:56Z",
              "time": "2024-10-01T12:34:56+00:00"
            }
            """);

        // Act
        Dictionary<string, object?> result = document.ParseRecord(recordType);

        // Assert
        Assert.Equal("hello", result["text"]);
        Assert.Equal(7d, result["numberInt"]);
        Assert.Equal(9223372036854775807L, result["numberLong"]);
        Assert.Equal(12.5m, result["numberDecimal"]);
        Assert.Equal(9.75d, result["numberDouble"]);
        Assert.Equal(true, result["flag"]);
        Assert.Equal(expectedDateTime, result["date"]);
        Assert.Equal(expectedTimeSpan, result["time"]);
    }

    [Fact]
    public void ParseRecord_Object_NestedRecord_Succeeds()
    {
        // Arrange
        VariableType innerRecord =
            VariableType.Record(
                [
                    ("innerText", new VariableType(typeof(string))),
                    ("innerNumber", new VariableType(typeof(int)))
                ]);

        VariableType outerRecord =
            VariableType.Record(
                [
                    ("outerText", new VariableType(typeof(string))),
                    ("nested", innerRecord)
                ]);

        JsonDocument document = JsonDocument.Parse(
            """
            {
              "outerText": "outer",
              "nested": {
                "innerText": "inner",
                "innerNumber": 42
              }
            }
            """);

        // Act
        Dictionary<string, object?> result = document.ParseRecord(outerRecord);

        // Assert
        Assert.Equal("outer", result["outerText"]);
        Dictionary<string, object?> nested = (Dictionary<string, object?>)result["nested"]!;
        Assert.Equal("inner", nested["innerText"]);
        Assert.Equal(42, nested["innerNumber"]);
    }

    [Fact]
    public void ParseRecord_NullRoot_ReturnsEmptyDictionary()
    {
        // Arrange
        VariableType recordType =
            VariableType.Record(
                [
                    ("text", new VariableType(typeof(string)))
                ]);

        JsonDocument document = JsonDocument.Parse("null");

        // Act
        Dictionary<string, object?> result = document.ParseRecord(recordType);

        // Assert
        Assert.Empty(result);
    }

    [Fact]
    public void ParseRecord_ArrayWithSingleRecord_Succeeds()
    {
        // Arrange
        VariableType recordType =
            VariableType.Record(
                [
                    ("name", new VariableType(typeof(string))),
                    ("value", new VariableType(typeof(int)))
                ]);

        JsonDocument document = JsonDocument.Parse(
            """
            [
              {
                "name": "item",
                "value": 5
              }
            ]
            """);

        // Act
        Dictionary<string, object?> result = document.ParseRecord(recordType);

        // Assert
        Assert.Equal("item", result["name"]);
        Assert.Equal(5, result["value"]);
    }

    [Fact]
    public void ParseRecord_ArrayWithMultipleRecords_Throws()
    {
        // Arrange
        VariableType recordType =
            VariableType.Record(
                [
                    ("id", new VariableType(typeof(int)))
                ]);

        JsonDocument document = JsonDocument.Parse(
            """
            [
              { "id": 1 },
              { "id": 2 }
            ]
            """);

        // Act / Assert
        Assert.Throws<InvalidOperationException>(() => document.ParseRecord(recordType));
    }

    [Fact]
    public void ParseRecord_InvalidTargetType_ThrowsDeclarativeActionException()
    {
        // Arrange
        VariableType notARecord = new(typeof(string));
        JsonDocument document = JsonDocument.Parse(
            """
            { "x": 1 }
            """);

        // Act / Assert
        Assert.Throws<DeclarativeActionException>(() => document.ParseRecord(notARecord));
    }

    [Fact]
    public void ParseRecord_InvalidRootKind_ThrowsDeclarativeActionException()
    {
        // Arrange
        VariableType recordType =
            VariableType.Record(
                [
                    ("text", new VariableType(typeof(string)))
                ]);

        JsonDocument document = JsonDocument.Parse(@"""not-an-object""");

        // Act / Assert
        Assert.Throws<DeclarativeActionException>(() => document.ParseRecord(recordType));
    }

    [Fact]
    public void ParseRecord_UnsupportedPropertyType_ThrowsInvalidOperationException()
    {
        // Arrange
        VariableType recordType =
            VariableType.Record(
                [
                    ("unsupported", new VariableType(typeof(float)))
                ]);

        JsonDocument document = JsonDocument.Parse(
            """
            { "unsupported": 3.14 }
            """);

        // Act / Assert
        InvalidOperationException exception = Assert.Throws<InvalidOperationException>(() => document.ParseRecord(recordType));
        Assert.Contains("Unsupported data type", exception.Message);
    }

    [Fact]
    public void ParseRecord_MissingProperty_ThrowsKeyNotFoundException()
    {
        // Arrange
        VariableType recordType =
            VariableType.Record(
                [
                    ("required", new VariableType(typeof(string)))
                ]);

        JsonDocument document = JsonDocument.Parse("{}");

        // Act / Assert
        Assert.Throws<KeyNotFoundException>(() => document.ParseRecord(recordType));
    }
    [Fact]
    public void ParseList_NullRoot_ReturnsEmptyList()
    {
        // Arrange
        VariableType listType = new(typeof(int[])); // IsList == true
        JsonDocument document = JsonDocument.Parse("null");

        // Act
        List<object?> result = document.ParseList(listType);

        // Assert
        Assert.Empty(result);
    }

    [Fact]
    public void ParseList_Array_Primitives_Succeeds()
    {
        // Arrange
        VariableType listType = new(typeof(int[]));
        JsonDocument document = JsonDocument.Parse("[1,2,3]");

        // Act
        List<object?> result = document.ParseList(listType);

        // Assert
        Assert.Equal(3, result.Count);
        Assert.Equal(1, result[0]);
        Assert.Equal(2, result[1]);
        Assert.Equal(3, result[2]);
    }

    [Fact]
    public void ParseList_PrimitiveRoot_WrappedAsSingleElement_Succeeds()
    {
        // Arrange
        VariableType listType = new(typeof(int[]));
        JsonDocument document = JsonDocument.Parse("7");

        // Act
        List<object?> result = document.ParseList(listType);

        // Assert
        Assert.Single(result);
        Assert.Equal(7, result[0]);
    }

    [Fact]
    public void ParseList_Array_Records_Succeeds()
    {
        // Arrange
        VariableType recordType =
            VariableType.Record(
                [
                    ("id", new VariableType(typeof(int))),
                    ("name", new VariableType(typeof(string)))
                ]);
        JsonDocument document = JsonDocument.Parse(
            """
            [
              { "id": 1, "name": "a" },
              { "id": 2, "name": "b" }
            ]
            """);

        // Act
        List<object?> result = document.ParseList(recordType);

        // Assert
        Assert.Equal(2, result.Count);
        Dictionary<string, object?> first = (Dictionary<string, object?>)result[0]!;
        Dictionary<string, object?> second = (Dictionary<string, object?>)result[1]!;
        Assert.Equal(1, first["id"]);
        Assert.Equal("a", first["name"]);
        Assert.Equal(2, second["id"]);
        Assert.Equal("b", second["name"]);
    }

    [Fact]
    public void ParseList_InvalidTargetType_ThrowsDeclarativeActionException()
    {
        // Arrange
        VariableType notAList = new(typeof(int));
        JsonDocument document = JsonDocument.Parse("[1,2]");

        // Act / Assert
        Assert.Throws<DeclarativeActionException>(() => document.ParseList(notAList));
    }

    [Fact]
    public void ParseList_Array_MixedTypes_Throws()
    {
        // Arrange
        VariableType listType = new(typeof(int[]));
        JsonDocument document = JsonDocument.Parse("[1,\"two\",3]");

        // Act / Assert
        Assert.ThrowsAny<Exception>(() => document.ParseList(listType));
    }
}
