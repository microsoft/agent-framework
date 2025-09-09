// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.PowerFx;

public class WorkflowScopesTests
{
    [Fact]
    public void ConstructorInitializesAllScopes()
    {
        // Arrange & Act
        WorkflowScopes scopes = new();

        // Assert
        RecordValue envRecord = scopes.BuildRecord(VariableScopeNames.Environment);
        RecordValue topicRecord = scopes.BuildRecord(VariableScopeNames.Topic);
        RecordValue globalRecord = scopes.BuildRecord(VariableScopeNames.Global);
        RecordValue systemRecord = scopes.BuildRecord(VariableScopeNames.System);

        Assert.NotNull(envRecord);
        Assert.NotNull(topicRecord);
        Assert.NotNull(globalRecord);
        Assert.NotNull(systemRecord);
    }

    [Fact]
    public void BuildRecordWhenEmpty()
    {
        // Arrange
        WorkflowScopes scopes = new();

        // Act
        RecordValue record = scopes.BuildRecord(VariableScopeNames.Topic);

        // Assert
        Assert.NotNull(record);
        Assert.Empty(record.Fields);
    }

    [Fact]
    public void BuildRecordContainsSetValues()
    {
        // Arrange
        WorkflowScopes scopes = new();
        FormulaValue testValue = FormulaValue.New("test");
        scopes.Set("key1", testValue, VariableScopeNames.Topic);

        // Act
        RecordValue record = scopes.BuildRecord(VariableScopeNames.Topic);

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
        WorkflowScopes scopes = new();
        FormulaValue testValue = FormulaValue.New("test");

        // Act & Assert
        scopes.Set("envKey", testValue, VariableScopeNames.Environment);
        RecordValue envRecord = scopes.BuildRecord(VariableScopeNames.Environment);
        Assert.Single(envRecord.Fields);

        scopes.Set("topicKey", testValue, VariableScopeNames.Topic);
        RecordValue topicRecord = scopes.BuildRecord(VariableScopeNames.Topic);
        Assert.Single(topicRecord.Fields);

        scopes.Set("globalKey", testValue, VariableScopeNames.Global);
        RecordValue globalRecord = scopes.BuildRecord(VariableScopeNames.Global);
        Assert.Single(globalRecord.Fields);

        scopes.Set("systemKey", testValue, VariableScopeNames.System);
        RecordValue systemRecord = scopes.BuildRecord(VariableScopeNames.System);
        Assert.Single(systemRecord.Fields);
    }

    [Fact]
    public void GetWithImplicitScope()
    {
        // Arrange
        WorkflowScopes scopes = new();
        FormulaValue testValue = FormulaValue.New("test");
        scopes.Set("key1", testValue, VariableScopeNames.Topic);

        // Act
        FormulaValue result = scopes.Get("key1");

        // Assert
        Assert.Equal(testValue, result);
    }

    [Fact]
    public void GetWithSpecifiedScope()
    {
        // Arrange
        WorkflowScopes scopes = new();
        FormulaValue testValue = FormulaValue.New("test");
        scopes.Set("key1", testValue, VariableScopeNames.Global);

        // Act
        FormulaValue result = scopes.Get("key1", VariableScopeNames.Global);

        // Assert
        Assert.Equal(testValue, result);
    }

    [Fact]
    public void SetDefaultScope()
    {
        // Arrange
        WorkflowScopes scopes = new();
        FormulaValue testValue = FormulaValue.New("test");

        // Act
        scopes.Set("key1", testValue);

        // Assert
        FormulaValue result = scopes.Get("key1", VariableScopeNames.Topic);
        Assert.Equal(testValue, result);
    }

    [Fact]
    public void SetSpecifiedScope()
    {
        // Arrange
        WorkflowScopes scopes = new();
        FormulaValue testValue = FormulaValue.New("test");

        // Act
        scopes.Set("key1", testValue, VariableScopeNames.System);

        // Assert
        FormulaValue result = scopes.Get("key1", VariableScopeNames.System);
        Assert.Equal(testValue, result);
    }

    [Fact]
    public void SetOverwritesExistingValue()
    {
        // Arrange
        WorkflowScopes scopes = new();
        FormulaValue initialValue = FormulaValue.New("initial");
        FormulaValue newValue = FormulaValue.New("new");

        // Act
        scopes.Set("key1", initialValue, VariableScopeNames.Topic);
        scopes.Set("key1", newValue, VariableScopeNames.Topic);

        // Assert
        FormulaValue result = scopes.Get("key1", VariableScopeNames.Topic);
        Assert.Equal(newValue, result);
    }

    [Fact]
    public void RemoveSpecifiedScope()
    {
        // Arrange
        WorkflowScopes scopes = new();
        FormulaValue testValue = FormulaValue.New("test");

        // Act
        scopes.Set("key1", testValue);

        // Assert
        FormulaValue result = scopes.Get("key1");
        Assert.Equal(testValue, result);

        // Act
        scopes.Reset("key1");

        // Assert
        FormulaValue resultBlank = scopes.Get("key1");
        Assert.IsType<BlankValue>(resultBlank);
    }
}
