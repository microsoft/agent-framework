// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.PowerFx;

public class WorkflowScopesTests
{
    internal WorkflowFormulaState State { get; } = new(RecalcEngineFactory.Create());

    [Fact]
    public void ConstructorInitializesAllScopes()
    {
        // Act & Assert
        RecordValue envRecord = this.State.BuildRecord(VariableScopeNames.Environment);
        RecordValue topicRecord = this.State.BuildRecord(VariableScopeNames.Topic);
        RecordValue globalRecord = this.State.BuildRecord(VariableScopeNames.Global);
        RecordValue systemRecord = this.State.BuildRecord(VariableScopeNames.System);

        Assert.NotNull(envRecord);
        Assert.NotNull(topicRecord);
        Assert.NotNull(globalRecord);
        Assert.NotNull(systemRecord);
    }

    [Fact]
    public void BuildRecordWhenEmpty()
    {
        // Act
        RecordValue record = this.State.BuildRecord(VariableScopeNames.Topic);

        // Assert
        Assert.NotNull(record);
        Assert.Empty(record.Fields);
    }

    [Fact]
    public void BuildRecordContainsSetValues()
    {
        // Arrange
        FormulaValue testValue = FormulaValue.New("test");
        this.State.Set("key1", testValue, VariableScopeNames.Topic);

        // Act
        RecordValue record = this.State.BuildRecord(VariableScopeNames.Topic);

        // Assert
        Assert.NotNull(record);
        Assert.Single(record.Fields);
        Assert.Equal("key1", record.Fields.First().Name);
        Assert.Equal(testValue, record.Fields.First().Value);
    }

    [Fact]
    public void BuildRecordForAllScopeTypes()
    {
        // Arrange
        FormulaValue testValue = FormulaValue.New("test");

        // Act & Assert
        this.State.Set("envKey", testValue, VariableScopeNames.Environment);
        RecordValue envRecord = this.State.BuildRecord(VariableScopeNames.Environment);
        Assert.Single(envRecord.Fields);

        this.State.Set("topicKey", testValue, VariableScopeNames.Topic);
        RecordValue topicRecord = this.State.BuildRecord(VariableScopeNames.Topic);
        Assert.Single(topicRecord.Fields);

        this.State.Set("globalKey", testValue, VariableScopeNames.Global);
        RecordValue globalRecord = this.State.BuildRecord(VariableScopeNames.Global);
        Assert.Single(globalRecord.Fields);

        this.State.Set("systemKey", testValue, VariableScopeNames.System);
        RecordValue systemRecord = this.State.BuildRecord(VariableScopeNames.System);
        Assert.Single(systemRecord.Fields);
    }

    [Fact]
    public void GetWithImplicitScope()
    {
        // Arrange
        FormulaValue testValue = FormulaValue.New("test");
        this.State.Set("key1", testValue, VariableScopeNames.Topic);

        // Act
        FormulaValue result = this.State.Get("key1");

        // Assert
        Assert.Equal(testValue, result);
    }

    [Fact]
    public void GetWithSpecifiedScope()
    {
        // Arrange
        FormulaValue testValue = FormulaValue.New("test");
        this.State.Set("key1", testValue, VariableScopeNames.Global);

        // Act
        FormulaValue result = this.State.Get("key1", VariableScopeNames.Global);

        // Assert
        Assert.Equal(testValue, result);
    }

    [Fact]
    public void SetDefaultScope()
    {
        // Arrange
        FormulaValue testValue = FormulaValue.New("test");

        // Act
        this.State.Set("key1", testValue);

        // Assert
        FormulaValue result = this.State.Get("key1", VariableScopeNames.Topic);
        Assert.Equal(testValue, result);
    }

    [Fact]
    public void SetSpecifiedScope()
    {
        // Arrange
        FormulaValue testValue = FormulaValue.New("test");

        // Act
        this.State.Set("key1", testValue, VariableScopeNames.System);

        // Assert
        FormulaValue result = this.State.Get("key1", VariableScopeNames.System);
        Assert.Equal(testValue, result);
    }

    [Fact]
    public void SetOverwritesExistingValue()
    {
        // Arrange
        FormulaValue initialValue = FormulaValue.New("initial");
        FormulaValue newValue = FormulaValue.New("new");

        // Act
        this.State.Set("key1", initialValue, VariableScopeNames.Topic);
        this.State.Set("key1", newValue, VariableScopeNames.Topic);

        // Assert
        FormulaValue result = this.State.Get("key1", VariableScopeNames.Topic);
        Assert.Equal(newValue, result);
    }

    [Fact]
    public void RemoveSpecifiedScope()
    {
        // Arrange
        FormulaValue testValue = FormulaValue.New("test");

        // Act
        this.State.Set("key1", testValue);

        // Assert
        FormulaValue result = this.State.Get("key1");
        Assert.Equal(testValue, result);

        // Act
        this.State.Reset("key1");

        // Assert
        FormulaValue resultBlank = this.State.Get("key1");
        Assert.IsType<BlankValue>(resultBlank);
    }
}
