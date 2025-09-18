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
        DataValue dataValue = formulaValue.ToDataValue();
        BooleanDataValue typedValue = Assert.IsType<BooleanDataValue>(dataValue);
        Assert.Equal(formulaValue.Value, typedValue.Value);

        BooleanValue formulaCopy = Assert.IsType<BooleanValue>(dataValue.ToFormula());
        Assert.Equal(typedValue.Value, formulaCopy.Value);

        Assert.Equal(bool.TrueString, formulaValue.Format());
    }

    [Fact]
    public void StringValues()
    {
        StringValue formulaValue = FormulaValue.New("test value");
        Assert.Equal(StringDataType.Instance, formulaValue.GetDataType());

        DataValue dataValue = formulaValue.ToDataValue();
        StringDataValue typedValue = Assert.IsType<StringDataValue>(dataValue);
        Assert.Equal(formulaValue.Value, typedValue.Value);

        StringValue formulaCopy = Assert.IsType<StringValue>(typedValue.ToFormula());
        Assert.Equal(typedValue.Value, formulaCopy.Value);

        Assert.Equal(formulaValue.Value, formulaValue.Format());
    }

    [Fact]
    public void DecimalValues()
    {
        DecimalValue formulaValue = FormulaValue.New(45.3m);
        Assert.Equal(NumberDataType.Instance, formulaValue.GetDataType());

        DataValue dataValue = formulaValue.ToDataValue();
        NumberDataValue typedValue = Assert.IsType<NumberDataValue>(dataValue);
        Assert.Equal(formulaValue.Value, typedValue.Value);

        DecimalValue formulaCopy = Assert.IsType<DecimalValue>(typedValue.ToFormula());
        Assert.Equal(typedValue.Value, formulaCopy.Value);

        Assert.Equal("45.3", formulaValue.Format());
    }

    [Fact]
    public void NumberValues()
    {
        NumberValue formulaValue = FormulaValue.New(3.1415926535897);
        Assert.Equal(FloatDataType.Instance, formulaValue.GetDataType());

        DataValue dataValue = formulaValue.ToDataValue();
        FloatDataValue typedValue = Assert.IsType<FloatDataValue>(dataValue);
        Assert.Equal(formulaValue.Value, typedValue.Value);

        NumberValue formulaCopy = Assert.IsType<NumberValue>(typedValue.ToFormula());
        Assert.Equal(typedValue.Value, formulaCopy.Value);

        Assert.Equal("3.1415926535897", formulaValue.Format());
    }

    [Fact]
    public void BlankValues()
    {
        BlankValue formulaValue = FormulaValue.NewBlank();
        Assert.Equal(DataType.Blank, formulaValue.GetDataType());
        Assert.IsType<BlankDataValue>(formulaValue.ToDataValue());

        Assert.Equal(string.Empty, formulaValue.Format());
    }

    [Fact]
    public void VoidValues()
    {
        VoidValue formulaValue = FormulaValue.NewVoid();
        Assert.Equal(DataType.Unspecified, formulaValue.GetDataType());
        Assert.IsType<BlankDataValue>(formulaValue.ToDataValue());
    }

    [Fact]
    public void DateValues()
    {
        DateTime timestamp = DateTime.UtcNow.Date;
        DateValue formulaValue = FormulaValue.NewDateOnly(timestamp);
        Assert.Equal(DataType.Date, formulaValue.GetDataType());

        DataValue dataValue = formulaValue.ToDataValue();
        DateDataValue typedValue = Assert.IsType<DateDataValue>(dataValue);
        Assert.Equal(formulaValue.GetConvertedValue(TimeZoneInfo.Utc), typedValue.Value);

        DateValue formulaCopy = Assert.IsType<DateValue>(dataValue.ToFormula());
        Assert.Equal(typedValue.Value, formulaCopy.GetConvertedValue(TimeZoneInfo.Utc));

        Assert.Equal($"{timestamp}", formulaValue.Format());
    }

    [Fact]
    public void DateTimeValues()
    {
        DateTime timestamp = DateTime.UtcNow;
        DateTimeValue formulaValue = FormulaValue.New(timestamp);
        Assert.Equal(DataType.DateTime, formulaValue.GetDataType());

        DataValue dataValue = formulaValue.ToDataValue();
        DateTimeDataValue typedValue = Assert.IsType<DateTimeDataValue>(dataValue);
        Assert.Equal(formulaValue.GetConvertedValue(TimeZoneInfo.Utc), typedValue.Value);

        DateTimeValue formulaCopy = Assert.IsType<DateTimeValue>(typedValue.ToFormula());
        Assert.Equal(typedValue.Value, formulaCopy.GetConvertedValue(TimeZoneInfo.Utc));

        Assert.Equal($"{timestamp}", formulaValue.Format());
    }

    [Fact]
    public void TimeValues()
    {
        TimeValue formulaValue = FormulaValue.New(TimeSpan.Parse("10:35"));
        Assert.Equal(DataType.Time, formulaValue.GetDataType());

        DataValue dataValue = formulaValue.ToDataValue();
        TimeDataValue typedValue = Assert.IsType<TimeDataValue>(dataValue);
        Assert.Equal(formulaValue.Value, typedValue.Value);

        TimeValue formulaCopy = Assert.IsType<TimeValue>(typedValue.ToFormula());
        Assert.Equal(typedValue.Value, formulaCopy.Value);

        Assert.Equal("10:35:00", formulaValue.Format());
    }

    [Fact]
    public void RecordValues()
    {
        RecordValue formulaValue = FormulaValue.NewRecordFromFields(
            new NamedValue("FieldA", FormulaValue.New("Value1")),
            new NamedValue("FieldB", FormulaValue.New("Value2")),
            new NamedValue("FieldC", FormulaValue.New("Value3")));
        Assert.Equal(DataType.EmptyRecord, formulaValue.GetDataType());

        RecordDataValue dataValue = formulaValue.ToRecord();
        Assert.Equal(formulaValue.Fields.Count(), dataValue.Properties.Count);
        foreach (KeyValuePair<string, DataValue> property in dataValue.Properties)
        {
            Assert.Contains(property.Key, formulaValue.Fields.Select(field => field.Name));
        }

        RecordValue formulaCopy = Assert.IsType<RecordValue>(dataValue.ToFormula(), exactMatch: false);
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

        Dictionary<string, int> source =
            new()
            {
                ["FieldA"] = 1,
                ["FieldB"] = 2,
                ["FieldC"] = 3
            };
        FormulaValue formula = source.ToFormula();
        Assert.IsType<RecordValue>(formula, exactMatch: false);
    }

    [Fact]
    public void TableValues()
    {
        RecordValue recordValue = FormulaValue.NewRecordFromFields(
            new NamedValue("FieldA", FormulaValue.New("Value1")),
            new NamedValue("FieldB", FormulaValue.New("Value2")),
            new NamedValue("FieldC", FormulaValue.New("Value3")));
        TableValue formulaValue = FormulaValue.NewTable(recordValue.Type, [recordValue]);

        TableDataValue dataValue = formulaValue.ToTable();
        Assert.Equal(formulaValue.Rows.Count(), dataValue.Values.Length);

        TableValue formulaCopy = Assert.IsType<TableValue>(dataValue.ToFormula(), exactMatch: false);
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
