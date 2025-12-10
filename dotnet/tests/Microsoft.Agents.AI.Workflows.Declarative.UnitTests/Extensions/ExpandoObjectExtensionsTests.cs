// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Dynamic;
using System.Linq;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.Extensions;

public sealed class ExpandoObjectExtensionsTests
{
    [Fact]
    public void ToRecordTypeWithEmptyExpandoObject()
    {
        // Arrange
        ExpandoObject expando = new();

        // Act
        RecordType recordType = expando.ToRecordType();

        // Assert
        Assert.NotNull(recordType);
        Assert.Empty(recordType.GetFieldTypes());
    }

    [Fact]
    public void ToRecordTypeWithStringProperty()
    {
        // Arrange
        dynamic expando = new ExpandoObject();
        expando.Name = "John Doe";

        // Act
        RecordType recordType = ((ExpandoObject)expando).ToRecordType();

        // Assert
        Assert.NotNull(recordType);
        IEnumerable<NamedFormulaType> fieldTypes = recordType.GetFieldTypes();
        Assert.Single(fieldTypes);
        NamedFormulaType field = fieldTypes.First();
        Assert.Equal("Name", field.Name.Value);
        Assert.Equal(FormulaType.String, field.Type);
    }

    [Fact]
    public void ToRecordTypeWithMultipleProperties()
    {
        // Arrange
        dynamic expando = new ExpandoObject();
        expando.Name = "Alice";
        expando.Age = 30;
        expando.IsActive = true;

        // Act
        RecordType recordType = ((ExpandoObject)expando).ToRecordType();

        // Assert
        Assert.NotNull(recordType);
        IEnumerable<NamedFormulaType> fieldTypes = recordType.GetFieldTypes();
        Assert.Equal(3, fieldTypes.Count());
        IEnumerable<string> fieldNames = fieldTypes.Select(f => f.Name.Value);
        Assert.Contains("Name", fieldNames);
        Assert.Contains("Age", fieldNames);
        Assert.Contains("IsActive", fieldNames);
    }

    [Fact]
    public void ToRecordTypeWithNullProperty()
    {
        // Arrange
        dynamic expando = new ExpandoObject();
        expando.Name = "Test";
        expando.NullValue = null;

        // Act
        RecordType recordType = ((ExpandoObject)expando).ToRecordType();

        // Assert
        Assert.NotNull(recordType);
        IEnumerable<NamedFormulaType> fieldTypes = recordType.GetFieldTypes();
        Assert.Equal(2, fieldTypes.Count());
        IEnumerable<string> fieldNames = fieldTypes.Select(f => f.Name.Value);
        Assert.Contains("Name", fieldNames);
        Assert.Contains("NullValue", fieldNames);
    }

    [Fact]
    public void ToRecordWithEmptyExpandoObject()
    {
        // Arrange
        ExpandoObject expando = new();

        // Act
        RecordValue recordValue = expando.ToRecord();

        // Assert
        Assert.NotNull(recordValue);
        Assert.Empty(recordValue.Fields);
    }

    [Fact]
    public void ToRecordWithStringProperty()
    {
        // Arrange
        dynamic expando = new ExpandoObject();
        expando.Message = "Hello World";

        // Act
        RecordValue recordValue = ((ExpandoObject)expando).ToRecord();

        // Assert
        Assert.NotNull(recordValue);
        Assert.Single(recordValue.Fields);
        NamedValue field = recordValue.Fields.First();
        Assert.Equal("Message", field.Name);
        StringValue stringValue = Assert.IsType<StringValue>(field.Value);
        Assert.Equal("Hello World", stringValue.Value);
    }

    [Fact]
    public void ToRecordWithMultiplePropertiesOfDifferentTypes()
    {
        // Arrange
        dynamic expando = new ExpandoObject();
        expando.Name = "Bob";
        expando.Count = 42;
        expando.Active = true;

        // Act
        RecordValue recordValue = ((ExpandoObject)expando).ToRecord();

        // Assert
        Assert.NotNull(recordValue);
        Assert.Equal(3, recordValue.Fields.Count());

        FormulaValue nameField = recordValue.GetField("Name");
        StringValue nameValue = Assert.IsType<StringValue>(nameField);
        Assert.Equal("Bob", nameValue.Value);

        FormulaValue countField = recordValue.GetField("Count");
        DecimalValue countValue = Assert.IsType<DecimalValue>(countField);
        Assert.Equal(42, countValue.Value);

        FormulaValue activeField = recordValue.GetField("Active");
        BooleanValue activeValue = Assert.IsType<BooleanValue>(activeField);
        Assert.True(activeValue.Value);
    }

    [Fact]
    public void ToRecordWithNestedExpandoObject()
    {
        // Arrange
        dynamic nested = new ExpandoObject();
        nested.InnerValue = "Inner";

        dynamic expando = new ExpandoObject();
        expando.Outer = "Outer";
        expando.Nested = nested;

        // Act
        RecordValue recordValue = ((ExpandoObject)expando).ToRecord();

        // Assert
        Assert.NotNull(recordValue);
        Assert.Equal(2, recordValue.Fields.Count());

        Assert.NotNull(recordValue.GetField("Outer"));
        FormulaValue nestedField = recordValue.GetField("Nested");
        Assert.NotNull(nestedField);

        RecordValue nestedRecord = Assert.IsType<RecordValue>(nestedField, exactMatch: false);
        Assert.Single(nestedRecord.Fields);
    }

    [Fact]
    public void ToRecordWithNullProperty()
    {
        // Arrange
        dynamic expando = new ExpandoObject();
        expando.Name = "Test";
        expando.NullValue = null;

        // Act
        RecordValue recordValue = ((ExpandoObject)expando).ToRecord();

        // Assert
        Assert.NotNull(recordValue);
        Assert.Equal(2, recordValue.Fields.Count());

        FormulaValue nullField = recordValue.GetField("NullValue");
        Assert.IsType<BlankValue>(nullField);
    }

    [Fact]
    public void ToRecordTypeAndToRecordAreConsistent()
    {
        // Arrange
        dynamic expando = new ExpandoObject();
        expando.StringField = "Value";
        expando.IntField = 123;
        expando.BoolField = false;

        // Act
        RecordType recordType = ((ExpandoObject)expando).ToRecordType();
        RecordValue recordValue = ((ExpandoObject)expando).ToRecord();

        // Assert
        List<NamedFormulaType> fieldTypesList = recordType.GetFieldTypes().ToList();
        Assert.Equal(fieldTypesList.Count, recordValue.Fields.Count());

        foreach (NamedFormulaType fieldType in fieldTypesList)
        {
            Assert.Contains(recordValue.Fields, f => f.Name == fieldType.Name.Value);
        }
    }
}
