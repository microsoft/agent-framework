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
                    ("text", typeof(string)),
                    ("numberInt", typeof(int)),
                    ("numberLong", typeof(long)),
                    ("numberDecimal", typeof(decimal)),
                    ("numberDouble", typeof(double)),
                    ("flag", typeof(bool)),
                    ("date", typeof(DateTime)),
                    ("time", typeof(TimeSpan))
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
              "numberDouble": 3.99E99,
              "flag": true,
              "date": "2024-10-01T12:34:56Z",
              "time": "12:34:56"
            }
            """);

        // Act
        Dictionary<string, object?> result = document.ParseRecord(recordType);

        // Assert
        Assert.Equal("hello", result["text"]);
        Assert.Equal(7, result["numberInt"]);
        Assert.Equal(9223372036854775807L, result["numberLong"]);
        Assert.Equal(12.5m, result["numberDecimal"]);
        Assert.Equal(3.99E99, result["numberDouble"]);
        Assert.Equal(true, result["flag"]);
        Assert.Equal(expectedDateTime, result["date"]);
        Assert.Equal(expectedTimeSpan, result["time"]);
    }

    [Fact]
    public void ParseRecord_Object_NoSchema_Succeeds()
    {
        // Arrange
        JsonDocument document = JsonDocument.Parse(
            """
            {
              "text": "hello",
              "numberInt": 7,
              "numberLong": 9223372036854775807,
              "numberDecimal": 12.5,
              "numberDouble": 3.99E99,
              "flag": true,
              "date": "2024-10-01T12:34:56Z",
              "time": "12:34:56"
            }
            """);

        // Act
        Dictionary<string, object?> result = document.ParseRecord(VariableType.RecordType);

        // Assert
        Assert.Equal("hello", result["text"]);
        Assert.Equal(7, result["numberInt"]);
        Assert.Equal(9223372036854775807L, result["numberLong"]);
        Assert.Equal(12.5m, result["numberDecimal"]);
        Assert.Equal(3.99E99, result["numberDouble"]);
        Assert.Equal(true, result["flag"]);
        Assert.Equal("2024-10-01T12:34:56Z", result["date"]);
        Assert.Equal("12:34:56", result["time"]);
    }

    [Fact]
    public void ParseRecord_Object_NestedRecord_Succeeds()
    {
        // Arrange
        VariableType innerRecord =
            VariableType.Record(
                [
                    ("innerText", typeof(string)),
                    ("innerNumber", typeof(int))
                ]);

        VariableType outerRecord =
            VariableType.Record(
                [
                    ("outerText", typeof(string)),
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
        Assert.NotNull(nested);
        Assert.True(nested.ContainsKey("innerText"));
        Assert.Equal("inner", nested["innerText"]);
        Assert.Equal(42, nested["innerNumber"]);
    }

    [Fact]
    public void ParseRecord_NullRoot_ReturnsEmpty()
    {
        // Arrange
        VariableType recordType =
            VariableType.Record(
                [
                    ("text", typeof(string))
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
        VariableType listType =
            VariableType.List(
                [
                    ("name", typeof(string)),
                    ("value", typeof(int))
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
        List<object?> result = document.ParseList(listType);

        // Assert
        Assert.Single(result);
        Dictionary<string, object?> element = Assert.IsType<Dictionary<string, object?>>(result[0]);
        Assert.Equal("item", element["name"]);
        Assert.Equal(5, element["value"]);
    }

    [Fact]
    public void ParseRecord_ArrayWithMultipleRecords_Throws()
    {
        // Arrange
        VariableType recordType =
            VariableType.Record(
                [
                    ("id", typeof(int))
                ]);

        JsonDocument document = JsonDocument.Parse(
            """
            [
              { "id": 1 },
              { "id": 2 }
            ]
            """);

        // Act / Assert
        Assert.Throws<DeclarativeActionException>(() => document.ParseRecord(recordType));
    }

    [Fact]
    public void ParseRecord_InvalidTargetType_Throws()
    {
        // Arrange
        VariableType notARecord = typeof(string);
        JsonDocument document = JsonDocument.Parse(
            """
            { "x": 1 }
            """);

        // Act / Assert
        Assert.Throws<DeclarativeActionException>(() => document.ParseRecord(notARecord));
    }

    [Fact]
    public void ParseRecord_InvalidRootKind_Throws()
    {
        // Arrange
        VariableType recordType =
            VariableType.Record(
                [
                    ("text", typeof(string))
                ]);

        JsonDocument document = JsonDocument.Parse(@"""not-an-object""");

        // Act / Assert
        Assert.Throws<DeclarativeActionException>(() => document.ParseRecord(recordType));
    }

    [Fact]
    public void ParseRecord_UnsupportedPropertyType_Throws()
    {
        // Arrange
        VariableType recordType =
            VariableType.Record(
                [
                    ("unsupported", typeof(Guid))
                ]);

        JsonDocument document = JsonDocument.Parse(
            """
            { "unsupported": "C2556C11-210E-4BB6-BF18-4A8968CB45A8" }
            """);

        // Act / Assert
        Assert.Throws<DeclarativeActionException>(() => document.ParseRecord(recordType));
    }

    [Fact]
    public void ParseRecord_MissingRequiredProperty_Throws()
    {
        // Arrange
        VariableType recordType =
            VariableType.Record(
                [
                    ("required", typeof(bool))
                ]);

        JsonDocument document = JsonDocument.Parse("{}");

        // Act / Assert
        Assert.Throws<DeclarativeActionException>(() => document.ParseRecord(recordType));
    }

    [Fact]
    public void ParseRecord_MissingNullableProperty_Succeeds()
    {
        // Arrange
        VariableType recordType =
            VariableType.Record(
                [
                    ("required", typeof(string))
                ]);

        JsonDocument document = JsonDocument.Parse("{}");

        // Act
        Dictionary<string, object?> result = document.ParseRecord(recordType);

        // Assert
        Assert.Single(result);
        Dictionary<string, object?> element = Assert.IsType<Dictionary<string, object?>>(result);
        Assert.Null(element["required"]);
    }

    [Fact]
    public void ParseList_NullRoot_ReturnsEmpty()
    {
        // Arrange
        JsonDocument document = JsonDocument.Parse("null");

        // Act
        List<object?> result = document.ParseList(typeof(int[]));

        // Assert
        Assert.Empty(result);
    }

    [Fact]
    public void ParseList_Array_Primitives_Succeeds()
    {
        // Arrange
        JsonDocument document = JsonDocument.Parse("[1,2,3]");

        // Act
        List<object?> result = document.ParseList(typeof(int[]));

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
        JsonDocument document = JsonDocument.Parse("7");

        // Act
        List<object?> result = document.ParseList(typeof(int));

        // Assert
        Assert.Single(result);
        Assert.Equal(7, result[0]);
    }

    [Fact]
    public void ParseList_Array_Records_Succeeds()
    {
        // Arrange
        VariableType listType =
            VariableType.List(
                [
                    ("id", typeof(int)),
                    ("name", typeof(string))
                ]);
        JsonDocument document = JsonDocument.Parse(
            """
            [
              { "id": 1, "name": "a" },
              { "id": 2, "name": "b" }
            ]
            """);

        // Act
        List<object?> result = document.ParseList(listType);

        // Assert
        Assert.Equal(2, result.Count);
        Dictionary<string, object?> first = (Dictionary<string, object?>)result[0]!;
        Dictionary<string, object?> second = (Dictionary<string, object?>)result[1]!;
        Assert.NotNull(first);
        Assert.Equal(1, first["id"]);
        Assert.Equal("a", first["name"]);
        Assert.NotNull(second);
        Assert.Equal(2, second["id"]);
        Assert.Equal("b", second["name"]);
    }

    [Fact]
    public void ParseList_InvalidTargetType_Throws()
    {
        // Arrange
        JsonDocument document = JsonDocument.Parse("[1,2]");

        // Act / Assert
        Assert.Throws<DeclarativeActionException>(() => document.ParseList(typeof(int)));
    }

    [Fact]
    public void ParseList_Array_MixedTypes_Throws()
    {
        // Arrange
        JsonDocument document = JsonDocument.Parse("[1,\"two\",3]");

        // Act / Assert
        Assert.Throws<DeclarativeActionException>(() => document.ParseList(typeof(int[])));
    }
}
