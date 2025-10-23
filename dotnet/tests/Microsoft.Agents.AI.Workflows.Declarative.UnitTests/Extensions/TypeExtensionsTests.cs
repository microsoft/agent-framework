// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.Extensions;

public sealed class TypeExtensionsTests
{
    [Fact]
    public void ReferenceType() => VerifyIsNullable(typeof(string));

    [Fact]
    public void ClassType() => VerifyIsNullable(typeof(object));

    [Fact]
    public void InterfaceType() => VerifyIsNullable(typeof(IDisposable));

    [Fact]
    public void ArrayType() => VerifyIsNullable(typeof(int[]));

    [Fact]
    public void NonNullableValueType() => VerifyNotNullable(typeof(int));

    [Fact]
    public void NonNullableStructType() => VerifyNotNullable(typeof(DateTime));

    [Fact]
    public void NonNullableEnumType() => VerifyNotNullable(typeof(DayOfWeek));

    [Fact]
    public void NullableInt() => VerifyIsNullable(typeof(int?));

    [Fact]
    public void NullableDateTime() => VerifyIsNullable(typeof(DateTime?));

    [Fact]
    public void NullableEnum() => VerifyIsNullable(typeof(DayOfWeek?));

    [Fact]
    public void NullableCustomStruct() => VerifyIsNullable(typeof(TestStruct?));

    private static void VerifyNotNullable(Type targetType)
    {
        // Act
        bool result = targetType.IsNullable();

        // Assert
        Assert.False(result);
    }

    private static void VerifyIsNullable(Type targetType)
    {
        // Act
        bool result = targetType.IsNullable();

        // Assert
        Assert.True(result);
    }

    private struct TestStruct
    {
        public int Value { get; set; }
    }
}
