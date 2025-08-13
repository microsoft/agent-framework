// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests;

public class WorkflowScopesTests
{
    [Fact]
    public void ConstructorInitializesAllScopes()
    {
        // Arrange & Act
        WorkflowScopes scopes = new();

        // Assert
        RecordValue envRecord = scopes.BuildRecord(WorkflowScopeType.Env);
        RecordValue topicRecord = scopes.BuildRecord(WorkflowScopeType.Topic);
        RecordValue globalRecord = scopes.BuildRecord(WorkflowScopeType.Global);
        RecordValue systemRecord = scopes.BuildRecord(WorkflowScopeType.System);

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
        RecordValue record = scopes.BuildRecord(WorkflowScopeType.Topic);

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
        scopes.Set("key1", WorkflowScopeType.Topic, testValue);

        // Act
        RecordValue record = scopes.BuildRecord(WorkflowScopeType.Topic);

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
        scopes.Set("envKey", WorkflowScopeType.Env, testValue);
        RecordValue envRecord = scopes.BuildRecord(WorkflowScopeType.Env);
        Assert.Single(envRecord.Fields);

        scopes.Set("topicKey", WorkflowScopeType.Topic, testValue);
        RecordValue topicRecord = scopes.BuildRecord(WorkflowScopeType.Topic);
        Assert.Single(topicRecord.Fields);

        scopes.Set("globalKey", WorkflowScopeType.Global, testValue);
        RecordValue globalRecord = scopes.BuildRecord(WorkflowScopeType.Global);
        Assert.Single(globalRecord.Fields);

        scopes.Set("systemKey", WorkflowScopeType.System, testValue);
        RecordValue systemRecord = scopes.BuildRecord(WorkflowScopeType.System);
        Assert.Single(systemRecord.Fields);
    }

    [Fact]
    public void GetWithImplicitScope()
    {
        // Arrange
        WorkflowScopes scopes = new();
        FormulaValue testValue = FormulaValue.New("test");
        scopes.Set("key1", WorkflowScopeType.Topic, testValue);

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
        scopes.Set("key1", WorkflowScopeType.Global, testValue);

        // Act
        FormulaValue result = scopes.Get("key1", WorkflowScopeType.Global);

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
        FormulaValue result = scopes.Get("key1", WorkflowScopeType.Topic);
        Assert.Equal(testValue, result);
    }

    [Fact]
    public void SetSpecifiedScope()
    {
        // Arrange
        WorkflowScopes scopes = new();
        FormulaValue testValue = FormulaValue.New("test");

        // Act
        scopes.Set("key1", WorkflowScopeType.System, testValue);

        // Assert
        FormulaValue result = scopes.Get("key1", WorkflowScopeType.System);
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
        scopes.Set("key1", WorkflowScopeType.Topic, initialValue);
        scopes.Set("key1", WorkflowScopeType.Topic, newValue);

        // Assert
        FormulaValue result = scopes.Get("key1", WorkflowScopeType.Topic);
        Assert.Equal(newValue, result);
    }
}
