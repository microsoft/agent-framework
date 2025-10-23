// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections;
using System.Collections.Generic;
using System.Collections.Immutable;
using System.Linq;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.Extensions;

public sealed class DataValueExtensionsTests
{
    [Fact]
    public void ToDataValueWithNull()
    {
        // Arrange
        object? value = null;

        // Act
        DataValue result = value.ToDataValue();

        // Assert
        Assert.IsType<BlankDataValue>(result);
    }

    [Fact]
    public void ToDataValueWithUnassignedValue()
    {
        // Arrange
        object value = UnassignedValue.Instance;

        // Act
        DataValue result = value.ToDataValue();

        // Assert
        Assert.IsType<BlankDataValue>(result);
    }

    [Fact]
    public void ToDataValueWithBooleanTrue()
    {
        // Arrange
        const bool Value = true;

        // Act
        DataValue result = Value.ToDataValue();

        // Assert
        BooleanDataValue boolValue = Assert.IsType<BooleanDataValue>(result);
        Assert.True(boolValue.Value);
    }

    [Fact]
    public void ToDataValueWithBooleanFalse()
    {
        // Arrange
        const bool Value = false;

        // Act
        DataValue result = Value.ToDataValue();

        // Assert
        BooleanDataValue boolValue = Assert.IsType<BooleanDataValue>(result);
        Assert.False(boolValue.Value);
    }

    [Fact]
    public void ToDataValueWithInt()
    {
        // Arrange
        const int Value = 42;

        // Act
        DataValue result = Value.ToDataValue();

        // Assert
        NumberDataValue numberValue = Assert.IsType<NumberDataValue>(result);
        Assert.Equal(42, numberValue.Value);
    }

    [Fact]
    public void ToDataValueWithLong()
    {
        // Arrange
        const long Value = 9876543210L;

        // Act
        DataValue result = Value.ToDataValue();

        // Assert
        NumberDataValue numberValue = Assert.IsType<NumberDataValue>(result);
        Assert.Equal(9876543210L, numberValue.Value);
    }

    [Fact]
    public void ToDataValueWithFloat()
    {
        // Arrange
        const float Value = 3.14f;

        // Act
        DataValue result = Value.ToDataValue();

        // Assert
        FloatDataValue floatValue = Assert.IsType<FloatDataValue>(result);
        Assert.Equal(3.14f, floatValue.Value, precision: 2);
    }

    [Fact]
    public void ToDataValueWithDecimal()
    {
        // Arrange
        const decimal Value = 123.456m;

        // Act
        DataValue result = Value.ToDataValue();

        // Assert
        NumberDataValue numberValue = Assert.IsType<NumberDataValue>(result);
        Assert.Equal(123.456m, numberValue.Value);
    }

    [Fact]
    public void ToDataValueWithDouble()
    {
        // Arrange
        const double Value = 2.71828;

        // Act
        DataValue result = Value.ToDataValue();

        // Assert
        FloatDataValue floatValue = Assert.IsType<FloatDataValue>(result);
        Assert.Equal(2.71828, floatValue.Value, precision: 5);
    }

    [Fact]
    public void ToDataValueWithString()
    {
        // Arrange
        const string Value = "Test String";

        // Act
        DataValue result = Value.ToDataValue();

        // Assert
        StringDataValue stringValue = Assert.IsType<StringDataValue>(result);
        Assert.Equal("Test String", stringValue.Value);
    }

    [Fact]
    public void ToDataValueWithDateTimeZeroTime()
    {
        // Arrange
        DateTime value = new(2025, 10, 17, 0, 0, 0);

        // Act
        DataValue result = value.ToDataValue();

        // Assert
        DateDataValue dateValue = Assert.IsType<DateDataValue>(result);
        Assert.Equal(new DateTime(2025, 10, 17), dateValue.Value);
    }

    [Fact]
    public void ToDataValueWithDateTimeNonZeroTime()
    {
        // Arrange
        DateTime value = new(2025, 10, 17, 14, 30, 45);

        // Act
        DataValue result = value.ToDataValue();

        // Assert
        DateTimeDataValue dateTimeValue = Assert.IsType<DateTimeDataValue>(result);
        Assert.Equal(new DateTime(2025, 10, 17, 14, 30, 45), dateTimeValue.Value.DateTime);
    }

    [Fact]
    public void ToDataValueWithTimeSpan()
    {
        // Arrange
        TimeSpan value = TimeSpan.FromHours(2.5);

        // Act
        DataValue result = value.ToDataValue();

        // Assert
        TimeDataValue timeValue = Assert.IsType<TimeDataValue>(result);
        Assert.Equal(TimeSpan.FromHours(2.5), timeValue.Value);
    }

    [Fact]
    public void ToDataValueWithDataValue()
    {
        // Arrange
        DataValue value = StringDataValue.Create("Already a DataValue");

        // Act
        DataValue result = value.ToDataValue();

        // Assert
        Assert.Same(value, result);
    }

    [Fact]
    public void ToDataValueWithFormulaValue()
    {
        // Arrange
        FormulaValue value = FormulaValue.New(123);

        // Act
        DataValue result = value.ToDataValue();

        // Assert
        NumberDataValue numberValue = Assert.IsType<NumberDataValue>(result);
        Assert.Equal(123, numberValue.Value);
    }

    [Fact]
    public void ToFormulaWithNull()
    {
        // Arrange
        DataValue? value = null;

        // Act
        FormulaValue result = value.ToFormula();

        // Assert
        Assert.IsType<BlankValue>(result);
    }

    [Fact]
    public void ToFormulaWithBlankDataValue()
    {
        // Arrange
        DataValue value = DataValue.Blank();

        // Act
        FormulaValue result = value.ToFormula();

        // Assert
        Assert.IsType<BlankValue>(result);
    }

    [Fact]
    public void ToFormulaWithBooleanDataValue()
    {
        // Arrange
        DataValue value = BooleanDataValue.Create(true);

        // Act
        FormulaValue result = value.ToFormula();

        // Assert
        BooleanValue boolValue = Assert.IsType<BooleanValue>(result);
        Assert.True(boolValue.Value);
    }

    [Fact]
    public void ToFormulaWithNumberDataValue()
    {
        // Arrange
        DataValue value = NumberDataValue.Create(99.5m);

        // Act
        FormulaValue result = value.ToFormula();

        // Assert
        DecimalValue decimalValue = Assert.IsType<DecimalValue>(result);
        Assert.Equal(99.5m, decimalValue.Value);
    }

    [Fact]
    public void ToFormulaWithFloatDataValue()
    {
        // Arrange
        DataValue value = FloatDataValue.Create(1.23);

        // Act
        FormulaValue result = value.ToFormula();

        // Assert
        NumberValue numberValue = Assert.IsType<NumberValue>(result);
        Assert.Equal(1.23, numberValue.Value, precision: 2);
    }

    [Fact]
    public void ToFormulaWithStringDataValue()
    {
        // Arrange
        DataValue value = StringDataValue.Create("Test");

        // Act
        FormulaValue result = value.ToFormula();

        // Assert
        StringValue stringValue = Assert.IsType<StringValue>(result);
        Assert.Equal("Test", stringValue.Value);
    }

    [Fact]
    public void ToFormulaWithDateTimeDataValue()
    {
        // Arrange
        DateTime dateTime = new(2025, 10, 17, 12, 0, 0);
        DataValue value = DateTimeDataValue.Create(dateTime);

        // Act
        FormulaValue result = value.ToFormula();

        // Assert
        DateTimeValue dateTimeValue = Assert.IsType<DateTimeValue>(result);
        Assert.Equal(dateTime, dateTimeValue.GetConvertedValue(TimeZoneInfo.Utc));
    }

    [Fact]
    public void ToFormulaWithDateDataValue()
    {
        // Arrange
        DateTime date = new(2025, 10, 17);
        DataValue value = DateDataValue.Create(date);

        // Act
        FormulaValue result = value.ToFormula();

        // Assert
        DateValue dateValue = Assert.IsType<DateValue>(result);
        Assert.Equal(date, dateValue.GetConvertedValue(TimeZoneInfo.Utc));
    }

    [Fact]
    public void ToFormulaWithTimeDataValue()
    {
        // Arrange
        TimeSpan time = TimeSpan.FromHours(3);
        DataValue value = TimeDataValue.Create(time);

        // Act
        FormulaValue result = value.ToFormula();

        // Assert
        TimeValue timeValue = Assert.IsType<TimeValue>(result);
        Assert.Equal(time, timeValue.Value);
    }

    [Fact]
    public void ToFormulaWithRecordDataValue()
    {
        // Arrange
        DataValue value = DataValue.RecordFromFields(
            new KeyValuePair<string, DataValue>("Name", StringDataValue.Create("John")),
            new KeyValuePair<string, DataValue>("Age", NumberDataValue.Create(30)));

        // Act
        FormulaValue result = value.ToFormula();

        // Assert
        RecordValue recordValue = Assert.IsType<RecordValue>(result, exactMatch: false);
        Assert.Equal(2, recordValue.Fields.Count());
    }

    [Fact]
    public void ToFormulaWithTableDataValue()
    {
        // Arrange
        RecordDataValue record = DataValue.RecordFromFields(
            new KeyValuePair<string, DataValue>("Field", StringDataValue.Create("Value")));
        DataValue value = DataValue.TableFromRecords(ImmutableArray.Create(record));

        // Act
        FormulaValue result = value.ToFormula();

        // Assert
        TableValue tableValue = Assert.IsType<TableValue>(result, exactMatch: false);
        Assert.Single(tableValue.Rows);
    }

    [Fact]
    public void ToFormulaTypeWithNull()
    {
        // Arrange
        DataValue? value = null;

        // Act
        FormulaType result = value.ToFormulaType();

        // Assert
        Assert.Equal(FormulaType.Blank, result);
    }

    [Fact]
    public void ToFormulaTypeWithBooleanDataValue()
    {
        // Arrange
        DataValue value = BooleanDataValue.Create(true);

        // Act
        FormulaType result = value.ToFormulaType();

        // Assert
        Assert.Equal(FormulaType.Boolean, result);
    }

    [Fact]
    public void ToFormulaTypeWithStringDataValue()
    {
        // Arrange
        DataValue value = StringDataValue.Create("Test");

        // Act
        FormulaType result = value.ToFormulaType();

        // Assert
        Assert.Equal(FormulaType.String, result);
    }

    [Fact]
    public void DataTypeToFormulaTypeWithNull()
    {
        // Arrange
        DataType? type = null;

        // Act
        FormulaType result = type.ToFormulaType();

        // Assert
        Assert.Equal(FormulaType.Blank, result);
    }

    [Fact]
    public void DataTypeToFormulaTypeWithBooleanDataType()
    {
        // Arrange
        DataType type = BooleanDataType.Instance;

        // Act
        FormulaType result = type.ToFormulaType();

        // Assert
        Assert.Equal(FormulaType.Boolean, result);
    }

    [Fact]
    public void DataTypeToFormulaTypeWithNumberDataType()
    {
        // Arrange
        DataType type = NumberDataType.Instance;

        // Act
        FormulaType result = type.ToFormulaType();

        // Assert
        Assert.Equal(FormulaType.Decimal, result);
    }

    [Fact]
    public void DataTypeToFormulaTypeWithFloatDataType()
    {
        // Arrange
        DataType type = FloatDataType.Instance;

        // Act
        FormulaType result = type.ToFormulaType();

        // Assert
        Assert.Equal(FormulaType.Number, result);
    }

    [Fact]
    public void DataTypeToFormulaTypeWithStringDataType()
    {
        // Arrange
        DataType type = StringDataType.Instance;

        // Act
        FormulaType result = type.ToFormulaType();

        // Assert
        Assert.Equal(FormulaType.String, result);
    }

    [Fact]
    public void DataTypeToFormulaTypeWithDateTimeDataType()
    {
        // Arrange
        DataType type = DateTimeDataType.Instance;

        // Act
        FormulaType result = type.ToFormulaType();

        // Assert
        Assert.Equal(FormulaType.DateTime, result);
    }

    [Fact]
    public void DataTypeToFormulaTypeWithDateDataType()
    {
        // Arrange
        DataType type = DateDataType.Instance;

        // Act
        FormulaType result = type.ToFormulaType();

        // Assert
        Assert.Equal(FormulaType.Date, result);
    }

    [Fact]
    public void DataTypeToFormulaTypeWithTimeDataType()
    {
        // Arrange
        DataType type = TimeDataType.Instance;

        // Act
        FormulaType result = type.ToFormulaType();

        // Assert
        Assert.Equal(FormulaType.Time, result);
    }

    [Fact]
    public void ToObjectWithNull()
    {
        // Arrange
        DataValue? value = null;

        // Act
        object? result = value.ToObject();

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public void ToObjectWithBlankDataValue()
    {
        // Arrange
        DataValue value = DataValue.Blank();

        // Act
        object? result = value.ToObject();

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public void ToObjectWithBooleanDataValue()
    {
        // Arrange
        DataValue value = BooleanDataValue.Create(true);

        // Act
        object? result = value.ToObject();

        // Assert
        Assert.IsType<bool>(result);
        Assert.True((bool)result);
    }

    [Fact]
    public void ToObjectWithNumberDataValue()
    {
        // Arrange
        DataValue value = NumberDataValue.Create(42.5m);

        // Act
        object? result = value.ToObject();

        // Assert
        Assert.IsType<decimal>(result);
        Assert.Equal(42.5m, (decimal)result);
    }

    [Fact]
    public void ToObjectWithStringDataValue()
    {
        // Arrange
        DataValue value = StringDataValue.Create("Hello");

        // Act
        object? result = value.ToObject();

        // Assert
        Assert.IsType<string>(result);
        Assert.Equal("Hello", (string)result);
    }

    [Fact]
    public void ToClrTypeWithBooleanDataType()
    {
        // Arrange
        DataType type = BooleanDataType.Instance;

        // Act
        Type result = type.ToClrType();

        // Assert
        Assert.Equal(typeof(bool), result);
    }

    [Fact]
    public void ToClrTypeWithNumberDataType()
    {
        // Arrange
        DataType type = NumberDataType.Instance;

        // Act
        Type result = type.ToClrType();

        // Assert
        Assert.Equal(typeof(decimal), result);
    }

    [Fact]
    public void ToClrTypeWithFloatDataType()
    {
        // Arrange
        DataType type = FloatDataType.Instance;

        // Act
        Type result = type.ToClrType();

        // Assert
        Assert.Equal(typeof(double), result);
    }

    [Fact]
    public void ToClrTypeWithStringDataType()
    {
        // Arrange
        DataType type = StringDataType.Instance;

        // Act
        Type result = type.ToClrType();

        // Assert
        Assert.Equal(typeof(string), result);
    }

    [Fact]
    public void ToClrTypeWithDateTimeDataType()
    {
        // Arrange
        DataType type = DateTimeDataType.Instance;

        // Act
        Type result = type.ToClrType();

        // Assert
        Assert.Equal(typeof(DateTime), result);
    }

    [Fact]
    public void ToClrTypeWithTimeDataType()
    {
        // Arrange
        DataType type = TimeDataType.Instance;

        // Act
        Type result = type.ToClrType();

        // Assert
        Assert.Equal(typeof(TimeSpan), result);
    }

    [Fact]
    public void AsListWithNull()
    {
        // Arrange
        DataValue? value = null;

        // Act
        IList<string>? result = value.AsList<string>();

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public void AsListWithBlankDataValue()
    {
        // Arrange
        DataValue value = DataValue.Blank();

        // Act
        IList<string>? result = value.AsList<string>();

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public void NewBlankWithNullDataType()
    {
        // Arrange
        DataType? type = null;

        // Act
        FormulaValue result = type.NewBlank();

        // Assert
        Assert.IsType<BlankValue>(result);
    }

    [Fact]
    public void NewBlankWithBooleanDataType()
    {
        // Arrange
        DataType type = BooleanDataType.Instance;

        // Act
        FormulaValue result = type.NewBlank();

        // Assert
        Assert.IsType<BlankValue>(result);
    }

    [Fact]
    public void ToRecordValueWithRecordDataValue()
    {
        // Arrange
        RecordDataValue recordDataValue = DataValue.RecordFromFields(
            new KeyValuePair<string, DataValue>("Field1", StringDataValue.Create("Value1")),
            new KeyValuePair<string, DataValue>("Field2", NumberDataValue.Create(123)));

        // Act
        RecordValue result = recordDataValue.ToRecordValue();

        // Assert
        Assert.NotNull(result);
        Assert.Equal(2, result.Fields.Count());

        Assert.NotNull(result.GetField("Field1"));
        Assert.NotNull(result.GetField("Field2"));
    }

    [Fact]
    public void ToRecordTypeWithRecordDataType()
    {
        // Arrange
        RecordDataType recordDataType = new RecordDataType.Builder
        {
            Properties =
            {
                ["Name"] = new PropertyInfo.Builder
                {
                    Type = StringDataType.Instance
                }.Build(),
                ["Count"] = new PropertyInfo.Builder
                {
                    Type = NumberDataType.Instance
                }.Build()
            }
        }.Build();

        // Act
        RecordType result = recordDataType.ToRecordType();

        // Assert
        Assert.NotNull(result);
        IEnumerable<NamedFormulaType> fieldTypes = result.GetFieldTypes();
        List<NamedFormulaType> fieldTypesList = fieldTypes.ToList();
        Assert.Equal(2, fieldTypesList.Count);

        IEnumerable<string> fieldNames = fieldTypesList.Select(f => f.Name.Value);
        Assert.Contains("Name", fieldNames);
        Assert.Contains("Count", fieldNames);

        NamedFormulaType nameField = fieldTypesList.First(f => f.Name.Value == "Name");
        NamedFormulaType countField = fieldTypesList.First(f => f.Name.Value == "Count");
        Assert.Equal(FormulaType.String, nameField.Type);
        Assert.Equal(FormulaType.Decimal, countField.Type);
    }

    [Fact]
    public void ToRecordValueWithDictionary()
    {
        // Arrange
        IDictionary dictionary = new Dictionary<string, object>
        {
            ["Key1"] = "Value1",
            ["Key2"] = 42
        };

        // Act
        RecordDataValue result = dictionary.ToRecordValue();

        // Assert
        Assert.NotNull(result);
        Assert.Equal(2, result.Properties.Count);
        Assert.True(result.Properties.ContainsKey("Key1"));
        Assert.True(result.Properties.ContainsKey("Key2"));
    }

    [Fact]
    public void ToTableValueWithEmptyEnumerable()
    {
        // Arrange
        IEnumerable enumerable = Array.Empty<object>();

        // Act
        TableDataValue result = enumerable.ToTableValue();

        // Assert
        Assert.NotNull(result);
        Assert.Empty(result.Values);
    }

    [Fact]
    public void ToTableValueWithDictionaryEnumerable()
    {
        // Arrange
        IEnumerable enumerable = new List<IDictionary>
        {
            new Dictionary<string, object> { ["Name"] = "Alice", ["Age"] = 30 },
            new Dictionary<string, object> { ["Name"] = "Bob", ["Age"] = 25 }
        };

        // Act
        TableDataValue result = enumerable.ToTableValue();

        // Assert
        Assert.NotNull(result);
    }

    [Fact]
    public void ToTableValueWithPrimitiveEnumerable()
    {
        // Arrange
        IEnumerable enumerable = new List<int> { 1, 2, 3 };

        // Act
        TableDataValue result = enumerable.ToTableValue();

        // Assert
        Assert.NotNull(result);
        Assert.Equal(3, result.Values.Length);
    }
}
