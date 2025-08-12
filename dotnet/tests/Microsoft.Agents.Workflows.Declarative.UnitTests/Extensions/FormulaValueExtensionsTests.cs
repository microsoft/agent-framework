// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.Extensions;

public class FormulaValueExtensionsTests
{
    [Fact]
    public void BooleanValue()
    {
        BooleanValue formulaValue = FormulaValue.New(true);
        BooleanDataValue dataValue = formulaValue.ToDataValue();
        Assert.Equal(formulaValue.Value, dataValue.Value);

        BooleanValue formulaCopy = Assert.IsType<BooleanValue>(dataValue.ToFormulaValue());
        Assert.Equal(dataValue.Value, formulaCopy.Value);

        Assert.Equal(bool.TrueString, formulaValue.Format());
    }

    [Fact]
    public void StringValues()
    {
        StringValue formulaValue = FormulaValue.New("test value");
        StringDataValue dataValue = formulaValue.ToDataValue();
        Assert.Equal(formulaValue.Value, dataValue.Value);

        StringValue formulaCopy = Assert.IsType<StringValue>(dataValue.ToFormulaValue());
        Assert.Equal(dataValue.Value, formulaCopy.Value);

        Assert.Equal(formulaValue.Value, formulaValue.Format());
    }

    [Fact]
    public void DecimalValues()
    {
        DecimalValue formulaValue = FormulaValue.New(45.3m);
        NumberDataValue dataValue = formulaValue.ToDataValue();
        Assert.Equal(formulaValue.Value, dataValue.Value);

        DecimalValue formulaCopy = Assert.IsType<DecimalValue>(dataValue.ToFormulaValue());
        Assert.Equal(dataValue.Value, formulaCopy.Value);

        Assert.Equal("45.3", formulaValue.Format());
    }

    [Fact]
    public void NumberValues()
    {
        NumberValue formulaValue = FormulaValue.New(3.1415926535897);
        FloatDataValue dataValue = formulaValue.ToDataValue();
        Assert.Equal(formulaValue.Value, dataValue.Value);

        NumberValue formulaCopy = Assert.IsType<NumberValue>(dataValue.ToFormulaValue());
        Assert.Equal(dataValue.Value, formulaCopy.Value);

        Assert.Equal("3.1415926535897", formulaValue.Format());
    }

    [Fact]
    public void BlankValues()
    {
        BlankValue formulaValue = FormulaValue.NewBlank();

        BlankDataValue dataCopy = Assert.IsType<BlankDataValue>(formulaValue.GetDataValue());

        Assert.Equal(string.Empty, formulaValue.Format());
    }

    [Fact]
    public void VoidValues()
    {
        VoidValue formulaValue = FormulaValue.NewVoid();
        BlankDataValue dataCopy = Assert.IsType<BlankDataValue>(formulaValue.GetDataValue());
    }

    [Fact]
    public void DateValues()
    {
        DateTime timestamp = DateTime.UtcNow.Date;
        DateValue formulaValue = FormulaValue.NewDateOnly(timestamp);
        DateDataValue dataValue = formulaValue.ToDataValue();
        Assert.Equal(formulaValue.GetConvertedValue(TimeZoneInfo.Utc), dataValue.Value);

        DateValue formulaCopy = Assert.IsType<DateValue>(dataValue.ToFormulaValue());
        Assert.Equal(dataValue.Value, formulaCopy.GetConvertedValue(TimeZoneInfo.Utc));

        Assert.Equal($"{timestamp}", formulaValue.Format());
    }

    [Fact]
    public void DateTimeValues()
    {
        DateTime timestamp = DateTime.UtcNow;
        DateTimeValue formulaValue = FormulaValue.New(timestamp);
        DateTimeDataValue dataValue = formulaValue.ToDataValue();
        Assert.Equal(formulaValue.GetConvertedValue(TimeZoneInfo.Utc), dataValue.Value);

        DateTimeValue formulaCopy = Assert.IsType<DateTimeValue>(dataValue.ToFormulaValue());
        Assert.Equal(dataValue.Value, formulaCopy.GetConvertedValue(TimeZoneInfo.Utc));

        Assert.Equal($"{timestamp}", formulaValue.Format());
    }

    [Fact]
    public void TimeValues()
    {
        TimeValue formulaValue = FormulaValue.New(TimeSpan.Parse("10:35"));
        TimeDataValue dataValue = formulaValue.ToDataValue();
        Assert.Equal(formulaValue.Value, dataValue.Value);

        TimeValue formulaCopy = Assert.IsType<TimeValue>(dataValue.ToFormulaValue());
        Assert.Equal(dataValue.Value, formulaCopy.Value);

        Assert.Equal("10:35:00", formulaValue.Format());
    }

    [Fact]
    public void RecordValues()
    {
        RecordValue formulaValue = FormulaValue.NewRecordFromFields(
            new NamedValue("FieldA", FormulaValue.New("Value1")),
            new NamedValue("FieldB", FormulaValue.New("Value2")),
            new NamedValue("FieldC", FormulaValue.New("Value3")));
        RecordDataValue dataValue = formulaValue.ToDataValue();
        Assert.Equal(formulaValue.Fields.Count(), dataValue.Properties.Count);
        foreach (KeyValuePair<string, DataValue> property in dataValue.Properties)
        {
            Assert.Contains(property.Key, formulaValue.Fields.Select(field => field.Name));
        }

        RecordValue formulaCopy = Assert.IsType<RecordValue>(dataValue.ToFormulaValue(), exactMatch: false);
        Assert.Equal(formulaCopy.Fields.Count(), dataValue.Properties.Count);
        foreach (NamedValue field in formulaCopy.Fields)
        {
            Assert.Contains(field.Name, dataValue.Properties.Keys);
        }

        Assert.Equal(
            """
            {
              "FieldA": "Value1",
              "FieldB": "Value2",
              "FieldC": "Value3"
            }
            """,
            formulaValue.Format().Replace(Environment.NewLine, "\n"));
    }

    [Fact]
    public void TableValues()
    {
        RecordValue recordValue = FormulaValue.NewRecordFromFields(
            new NamedValue("FieldA", FormulaValue.New("Value1")),
            new NamedValue("FieldB", FormulaValue.New("Value2")),
            new NamedValue("FieldC", FormulaValue.New("Value3")));
        TableValue formulaValue = TableValue.NewTable(recordValue.Type, [recordValue]);
        TableDataValue dataValue = formulaValue.ToDataValue();
        Assert.Equal(formulaValue.Rows.Count(), dataValue.Values.Length);

        TableValue formulaCopy = Assert.IsType<TableValue>(dataValue.ToFormulaValue(), exactMatch: false);
        Assert.Equal(formulaCopy.Rows.Count(), dataValue.Values.Length);

        Assert.Equal(
            """
            [
              {
                "FieldA": "Value1",
                "FieldB": "Value2",
                "FieldC": "Value3"
              }
            ]
            """,
            formulaValue.Format().Replace(Environment.NewLine, "\n"));
    }
}
