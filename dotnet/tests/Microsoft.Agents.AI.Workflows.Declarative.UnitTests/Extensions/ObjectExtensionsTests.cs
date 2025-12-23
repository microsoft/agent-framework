// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.Extensions;

public sealed class ObjectExtensionsTests
{
    [Fact]
    public void AsListWithNullInput()
    {
        object[]? nullList = null;
        IList<string>? result = nullList.AsList<string>();
        Assert.Null(result);
    }

    [Fact]
    public void AsListWithEmptyInput()
    {
        IList<string>? result = Array.Empty<int>().AsList<string>();
        Assert.NotNull(result);
        Assert.Empty(result);
    }

    [Fact]
    public void AsListWithSingleElement()
    {
        const string Value = "Test";
        IList<string>? result = Value.AsList<string>();
        Assert.NotNull(result);
        Assert.Single(result);
        Assert.Equal(Value, result[0]);
    }

    [Fact]
    public void AsListWithMultipleInput()
    {
        object[] inputs = ["33.3", "test"];
        IList<string>? result = inputs.AsList<string>();
        Assert.NotNull(result);
        Assert.Equal(2, result.Count);
    }

    [Fact]
    public void ConvertSame()
    {
        VerifyConversion(true, typeof(bool), true);
        VerifyConversion(32, typeof(int), 32);
        VerifyConversion("Test", typeof(string), "Test");
        DateTime now = DateTime.Now;
        VerifyConversion(now, typeof(DateTime), now);
        VerifyConversion(now.TimeOfDay, typeof(TimeSpan), now.TimeOfDay);
    }

    [Fact]
    public void ConvertFailure()
    {
        VerifyInvalid(32, VariableType.RecordType);
        VerifyInvalid(true, VariableType.RecordType);
        VerifyInvalid(Guid.NewGuid(), typeof(Guid));
    }

    [Fact]
    public void ConvertToString()
    {
        VerifyConversion(true, typeof(string), bool.TrueString);
        VerifyConversion(32, typeof(string), "32");
        VerifyConversion(3.14d, typeof(string), "3.14");
        DateTime now = DateTime.Now;
        VerifyConversion(now, typeof(string), $"{now:o}");
        VerifyConversion(now.TimeOfDay, typeof(string), $"{now.TimeOfDay:c}");
    }

    [Fact]
    public void ConvertFromString()
    {
        VerifyConversion("true", typeof(bool), true);
        VerifyConversion("32", typeof(int), 32);
        VerifyConversion("3.14", typeof(double), 3.14D);
        DateTime now = DateTime.Now;
        VerifyConversion($"{now:o}", typeof(DateTime), now);
        VerifyConversion($"{now.TimeOfDay:c}", typeof(TimeSpan), now.TimeOfDay);
    }

    [Fact]
    public void ConvertJson()
    {
        const string Json =
            """
            {
                "id": "item1",
                "count": 5
            }
            """;
        Dictionary<string, object?> expected =
            new()
            {
                { "id", "item1"},
                { "count", 5},
            };
        VerifyConversion(Json, VariableType.Record(("id", typeof(string)), ("count", typeof(int))), expected);
    }

    private static void VerifyConversion(object? sourceValue, VariableType targetType, object? expectedValue)
    {
        object? actualValue = sourceValue.ConvertType(targetType);
        if (expectedValue is IDictionary<string, object?> or DateTime)
        {
            Assert.Equivalent(expectedValue, actualValue);
        }
        else
        {
            Assert.Equal(expectedValue, actualValue);
        }
    }

    private static void VerifyInvalid(object? sourceValue, VariableType targetType)
    {
        Assert.Throws<DeclarativeActionException>(() => sourceValue.ConvertType(targetType));
    }
}
