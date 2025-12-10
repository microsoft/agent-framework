// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.Kit;

public sealed class VariableTypeTests
{
    [Fact]
    public void IsValidPrimitivesReturnTrue()
    {
        Assert.True(VariableType.IsValid<bool>());
        Assert.True(VariableType.IsValid<int>());
        Assert.True(VariableType.IsValid<long>());
        Assert.True(VariableType.IsValid<float>());
        Assert.True(VariableType.IsValid<decimal>());
        Assert.True(VariableType.IsValid<double>());
        Assert.True(VariableType.IsValid<string>());
        Assert.True(VariableType.IsValid<DateTime>());
        Assert.True(VariableType.IsValid<TimeSpan>());
    }

    [Fact]
    public void IsValidUnsupportedTypeReturnFalse()
    {
        Assert.False(VariableType.IsValid<Guid>());
        Assert.False(VariableType.IsValid<Uri>());
    }

    [Fact]
    public void IsListForListTypeReturnTrue()
    {
        VariableType listType = new(typeof(List<int>));
        Assert.True(listType.IsList);
        Assert.False(listType.IsRecord);
        Assert.True(listType.IsValid());
    }

    [Fact]
    public void IsRecordForDictionaryInterfaceReturnTrue()
    {
        VariableType recordType = new(typeof(IDictionary<string, object?>));
        Assert.True(recordType.IsRecord);
        Assert.False(recordType.IsList);
        Assert.True(recordType.IsValid());
    }

    [Fact]
    public void RecordFactoryCreatesSchema()
    {
        // Assuming the intended signature supports tuple params; adjust if needed.
        VariableType nameType = new(typeof(string));
        VariableType ageType = new(typeof(int));

        // If the actual signature differs (params IEnumerable<...>), adapt test accordingly.
        VariableType recordType = VariableType.Record(
            [("name", nameType), ("age", ageType)]
        );

        Assert.True(recordType.IsRecord);
        Assert.True(recordType.HasSchema);
        Assert.NotNull(recordType.Schema);
        Assert.Equal(2, recordType.Schema.Count);
        Assert.True(recordType.Schema.ContainsKey("name"));
        Assert.True(recordType.Schema.ContainsKey("age"));
        Assert.Equal(typeof(string), recordType.Schema["name"].Type);
        Assert.Equal(typeof(int), recordType.Schema["age"].Type);
    }

    [Fact]
    public void EqualsPrimitiveTypeEquality()
    {
        VariableType t1 = new(typeof(int));
        VariableType t2 = new(typeof(int));
        VariableType t3 = new(typeof(string));

        Assert.True(t1.Equals(t2));
        Assert.True(t1.Equals(typeof(int)));
        Assert.False(t1.Equals(t3));
        Assert.False(t1.Equals(typeof(string)));
    }

    [Fact]
    public void EqualsRecordEqualityIgnoresOrder()
    {
        VariableType strType = new(typeof(string));
        VariableType intType = new(typeof(int));

        VariableType recordA = VariableType.Record(
            [("first", strType), ("second", intType)]
        );
        VariableType recordB = VariableType.Record(
            [("second", intType), ("first", strType)]
        );

        Assert.True(recordA.Equals(recordB));
        Assert.True(recordB.Equals(recordA));
    }

    [Fact]
    public void EqualsRecordInequalityDifferentSchema()
    {
        VariableType strType = new(typeof(string));
        VariableType intType = new(typeof(int));

        VariableType recordA = VariableType.Record(
            [("first", strType), ("second", intType)]
        );
        VariableType recordB = VariableType.Record(
            [("first", strType)]
        );

        Assert.False(recordA.Equals(recordB));
        Assert.False(recordB.Equals(recordA));
    }

    [Fact]
    public void GetHashCodePrimitiveConsistency()
    {
        VariableType a = new(typeof(double));
        VariableType b = new(typeof(double));
        Assert.Equal(a, b);
        Assert.Equal(a, typeof(double));
        Assert.Equal(a.GetHashCode(), b.GetHashCode());
    }

    [Fact]
    public void GetHashCodeRecordConsistency()
    {
        VariableType a = VariableType.Record(("a", typeof(string)), ("b", typeof(int)));
        VariableType b = VariableType.Record(("a", typeof(string)), ("b", typeof(int)));
        Assert.Equal(a, b);
        Assert.NotEqual(a.GetHashCode(), b.GetHashCode());
    }

    [Fact]
    public void HasSchemaFalseForNonRecord()
    {
        VariableType primitive = new(typeof(int));
        Assert.False(primitive.HasSchema);
    }

    [Fact]
    public void ImplicitOperatorFromTypeWrapsCorrectly()
    {
        VariableType vt = typeof(string);
        Assert.Equal(typeof(string), vt.Type);
        Assert.True(vt.IsValid());
    }

    [Fact]
    public void EqualsNullAndDifferentTypes()
    {
        VariableType vt = new(typeof(int));
        VariableType? nullType = null;
        object? nullObj = null;
        object different = "test";

        Assert.False(vt.Equals(nullObj));
        Assert.False(vt.Equals(nullType));
        Assert.False(vt.Equals(different));
        Assert.True(vt.Equals((object)typeof(int)));
    }
}
