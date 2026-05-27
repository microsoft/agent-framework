// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Agents.AI.DurableTask.Workflows;

namespace Microsoft.Agents.AI.DurableTask.UnitTests.Workflows;

public sealed class DurableActivityExecutorTests
{
    private static readonly JsonSerializerOptions s_camelCaseOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        PropertyNameCaseInsensitive = true
    };

    #region DeserializeInput

    [Fact]
    public void DeserializeInput_StringType_ReturnsInputAsIs()
    {
        // Arrange
        const string Input = "hello world";

        // Act
        object result = DurableActivityExecutor.DeserializeInput(Input, typeof(string));

        // Assert
        Assert.Equal("hello world", result);
    }

    [Fact]
    public void DeserializeInput_SimpleObject_DeserializesCorrectly()
    {
        // Arrange
        string input = JsonSerializer.Serialize(new TestRecord("EXP-001", 100.50m), s_camelCaseOptions);

        // Act
        object result = DurableActivityExecutor.DeserializeInput(input, typeof(TestRecord));

        // Assert
        TestRecord record = Assert.IsType<TestRecord>(result);
        Assert.Equal("EXP-001", record.Id);
        Assert.Equal(100.50m, record.Amount);
    }

    [Fact]
    public void DeserializeInput_StringArray_DeserializesDirectly()
    {
        // Arrange
        string input = JsonSerializer.Serialize((string[])["a", "b", "c"]);

        // Act
        object result = DurableActivityExecutor.DeserializeInput(input, typeof(string[]));

        // Assert
        string[] array = Assert.IsType<string[]>(result);
        Assert.Equal(["a", "b", "c"], array);
    }

    [Fact]
    public void DeserializeInput_TypedArrayFromFanIn_DeserializesEachElement()
    {
        // Arrange — fan-in produces a JSON array of serialized strings
        TestRecord r1 = new("EXP-001", 100m);
        TestRecord r2 = new("EXP-002", 200m);
        string[] serializedElements =
        [
            JsonSerializer.Serialize(r1, s_camelCaseOptions),
            JsonSerializer.Serialize(r2, s_camelCaseOptions)
        ];
        string input = JsonSerializer.Serialize(serializedElements);

        // Act
        object result = DurableActivityExecutor.DeserializeInput(input, typeof(TestRecord[]));

        // Assert
        TestRecord[] records = Assert.IsType<TestRecord[]>(result);
        Assert.Equal(2, records.Length);
        Assert.Equal("EXP-001", records[0].Id);
        Assert.Equal(100m, records[0].Amount);
        Assert.Equal("EXP-002", records[1].Id);
        Assert.Equal(200m, records[1].Amount);
    }

    [Fact]
    public void DeserializeInput_TypedArrayWithSingleElement_DeserializesCorrectly()
    {
        // Arrange
        TestRecord r1 = new("EXP-001", 50m);
        string[] serializedElements = [JsonSerializer.Serialize(r1, s_camelCaseOptions)];
        string input = JsonSerializer.Serialize(serializedElements);

        // Act
        object result = DurableActivityExecutor.DeserializeInput(input, typeof(TestRecord[]));

        // Assert
        TestRecord[] records = Assert.IsType<TestRecord[]>(result);
        Assert.Single(records);
        Assert.Equal("EXP-001", records[0].Id);
    }

    [Fact]
    public void DeserializeInput_TypedArrayWithNullElement_ThrowsInvalidOperationException()
    {
        // Arrange — one element is "null"
        string input = JsonSerializer.Serialize((string[])["null"]);

        // Act & Assert
        Assert.Throws<InvalidOperationException>(
            () => DurableActivityExecutor.DeserializeInput(input, typeof(TestRecord[])));
    }

    [Fact]
    public void DeserializeInput_InvalidJson_ThrowsJsonException()
    {
        // Arrange
        const string Input = "not valid json";

        // Act & Assert
        Assert.ThrowsAny<JsonException>(
            () => DurableActivityExecutor.DeserializeInput(Input, typeof(TestRecord)));
    }

    #endregion

    #region ResolveInputType

    [Fact]
    public void ResolveInputType_NullTypeName_ReturnsFirstSupportedType()
    {
        // Arrange
        HashSet<Type> supportedTypes = [typeof(TestRecord), typeof(string)];

        // Act
        Type result = DurableActivityExecutor.ResolveInputType(null, supportedTypes);

        // Assert
        Assert.Equal(typeof(TestRecord), result);
    }

    [Fact]
    public void ResolveInputType_EmptyTypeName_ReturnsFirstSupportedType()
    {
        // Arrange
        HashSet<Type> supportedTypes = [typeof(TestRecord)];

        // Act
        Type result = DurableActivityExecutor.ResolveInputType(string.Empty, supportedTypes);

        // Assert
        Assert.Equal(typeof(TestRecord), result);
    }

    [Fact]
    public void ResolveInputType_EmptySupportedTypes_DefaultsToString()
    {
        // Arrange
        HashSet<Type> supportedTypes = [];

        // Act
        Type result = DurableActivityExecutor.ResolveInputType(null, supportedTypes);

        // Assert
        Assert.Equal(typeof(string), result);
    }

    [Fact]
    public void ResolveInputType_MatchesByFullName()
    {
        // Arrange
        HashSet<Type> supportedTypes = [typeof(TestRecord)];

        // Act
        Type result = DurableActivityExecutor.ResolveInputType(typeof(TestRecord).FullName, supportedTypes);

        // Assert
        Assert.Equal(typeof(TestRecord), result);
    }

    [Fact]
    public void ResolveInputType_MatchesByName()
    {
        // Arrange
        HashSet<Type> supportedTypes = [typeof(TestRecord)];

        // Act
        Type result = DurableActivityExecutor.ResolveInputType("TestRecord", supportedTypes);

        // Assert
        Assert.Equal(typeof(TestRecord), result);
    }

    [Fact]
    public void ResolveInputType_StringArrayFallsBackToSupportedType()
    {
        // Arrange — fan-in sends string[] but executor expects TestRecord[]
        HashSet<Type> supportedTypes = [typeof(TestRecord[])];

        // Act
        Type result = DurableActivityExecutor.ResolveInputType(typeof(string[]).FullName, supportedTypes);

        // Assert
        Assert.Equal(typeof(TestRecord[]), result);
    }

    [Fact]
    public void ResolveInputType_StringFallsBackToSupportedType()
    {
        // Arrange — executor doesn't support string
        HashSet<Type> supportedTypes = [typeof(TestRecord)];

        // Act
        Type result = DurableActivityExecutor.ResolveInputType(typeof(string).FullName, supportedTypes);

        // Assert
        Assert.Equal(typeof(TestRecord), result);
    }

    [Fact]
    public void ResolveInputType_StringArrayRetainedWhenSupported()
    {
        // Arrange — executor explicitly supports string[]
        HashSet<Type> supportedTypes = [typeof(string[])];

        // Act
        Type result = DurableActivityExecutor.ResolveInputType(typeof(string[]).FullName, supportedTypes);

        // Assert
        Assert.Equal(typeof(string[]), result);
    }

    #endregion

    private sealed record TestRecord(string Id, decimal Amount);
}
