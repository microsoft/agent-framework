// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.Extensions;

public sealed class PortableValueExtensionsTests
{
    [Fact]
    public void InvalidType() => TestInvalidType(IPAddress.Loopback);

    [Fact]
    public void NullType() => TestValidType<object>(null, FormulaType.Blank);

    [Fact]
    public void BooleanType() => TestValidType(true, FormulaType.Boolean);

    [Fact]
    public void StringType() => TestValidType("Hello, World!", FormulaType.String);

    [Fact]
    public void IntType() => TestValidType(int.MinValue, FormulaType.Decimal);

    [Fact]
    public void LongType() => TestValidType(long.MaxValue, FormulaType.Decimal);

    [Fact]
    public void DecimalType() => TestValidType(decimal.MaxValue, FormulaType.Decimal);

    [Fact]
    public void FloatType() => TestValidType(float.MaxValue, FormulaType.Number);

    [Fact]
    public void DoubleType() => TestValidType(double.MinValue, FormulaType.Number);

    [Fact]
    public void DateType() => TestValidType(DateTime.UtcNow.Date, FormulaType.Date);

    [Fact]
    public void DateTimeType() => TestValidType(DateTime.UtcNow, FormulaType.DateTime);

    [Fact]
    public void TimeSpanType() => TestValidType(DateTime.UtcNow.TimeOfDay, FormulaType.Time);

    [Fact(Skip = "WIP")]
    public void CollectionType()
    {
        TableValue convertedValue = (TableValue)TestValidType(new List<int> { 1, 2, 3 }, TableType.Empty());
        Assert.Equal(3, convertedValue.Count());
        DecimalValue firstElement = Assert.IsType<DecimalValue>(convertedValue.Rows.First());
        Assert.Equal(1, firstElement.Value);
    }

    [Fact]
    public void DictionaryType()
    {
        RecordValue convertedValue = (RecordValue)TestValidType(new Dictionary<string, int> { { "A", 1 }, { "B", 2 } }, RecordType.Empty());
        Assert.Equal(2, convertedValue.Fields.Count());
        NamedValue firstElement = convertedValue.Fields.First();
        Assert.Equal("A", firstElement.Name);
        DecimalValue firstElementValue = Assert.IsType<DecimalValue>(firstElement.Value);
        Assert.Equal(1, firstElementValue.Value);
    }

    [Fact]
    public void ObjectType()
    {
        RecordValue convertedValue = (RecordValue)TestValidType(FormulaValue.NewRecordFromFields(new NamedValue("key", FormulaValue.New(3))).ToDataValue().ToObject(), RecordType.Empty());
        Assert.Single(convertedValue.Fields);
        NamedValue firstElement = convertedValue.Fields.First();
        Assert.Equal("key", firstElement.Name);
        DecimalValue firstElementValue = Assert.IsType<DecimalValue>(firstElement.Value);
        Assert.Equal(3, firstElementValue.Value);
    }

    private static void TestInvalidType(object? sourceValue)
    {
        Assert.Throws<DeclarativeModelException>(() => sourceValue.AsPortable());

        PortableValue portableValue = new(sourceValue ?? UnassignedValue.Instance);
        Assert.Throws<DeclarativeModelException>(() => portableValue.ToFormula());
    }

    private static FormulaValue TestValidType<TValue>(TValue? sourceValue, FormulaType expectedType) where TValue : notnull
    {
        object portableObject = sourceValue.AsPortable();
        Assert.IsNotType<PortableValue>(portableObject);
        PortableValue portableValue = new(portableObject);
        FormulaValue formulaValue = portableValue.ToFormula();
        Assert.NotNull(formulaValue);
        Assert.Equal(expectedType.GetType(), formulaValue.Type.GetType());
        return formulaValue;
    }
}
