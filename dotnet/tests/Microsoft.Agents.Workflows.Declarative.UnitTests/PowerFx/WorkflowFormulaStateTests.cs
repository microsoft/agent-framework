// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.PowerFx;

public class WorkflowFormulaStateTests
{
    internal WorkflowFormulaState State { get; } = new(RecalcEngineFactory.Create());

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
}
