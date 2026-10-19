// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
using Microsoft.Agents.ObjectModel.Abstractions;
using Microsoft.PowerFx.Types;
using Moq;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.PowerFx;

public class WorkflowFormulaStateTests
{
    internal WorkflowFormulaState State { get; } = new(RecalcEngineFactory.Create());

    [Fact]
    public void GetWithImplicitScope()
    {
        // Arrange
        FormulaValue testValue = FormulaValue.New("test");
        this.State.Set("key1", testValue);

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
        FormulaValue result = this.State.Get("key1");
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
        this.State.Set("key1", initialValue);
        this.State.Set("key1", newValue);

        // Assert
        FormulaValue result = this.State.Get("key1");
        Assert.Equal(newValue, result);
    }

    [Theory]
    [InlineData("item", "ITEM", false)]
    [InlineData("ITEM", "item", false)]
    [InlineData("item", "ITEM", true)]
    [InlineData("ITEM", "item", true)]
    public void SetKeepsCaseVariantVariablesIndependent(string firstName, string secondName, bool useBlank)
    {
        // Arrange
        FormulaValue firstValue = FormulaValue.New("first");
        FormulaValue secondValue = useBlank ? FormulaValue.NewBlank() : FormulaValue.New("second");
        this.State.Set(firstName, firstValue, sensitivity: SensitivityLevel.Sensitive);

        // Act
        this.State.Set(secondName, secondValue);
        this.State.Bind();
        EvaluationResult<string> firstResult = this.State.Evaluator.GetValue(StringExpression.Expression($"Local.{firstName}"));
        EvaluationResult<string> secondResult = this.State.Evaluator.GetValue(StringExpression.Expression($"Local.{secondName}"));

        // Assert
        Assert.Equal(firstValue, this.State.Get(firstName));
        Assert.Equal(secondValue, this.State.Get(secondName));
        Assert.Equal("first", firstResult.Value);
        Assert.Equal(useBlank ? string.Empty : "second", secondResult.Value);
        Assert.Equal(SensitivityLevel.Sensitive, firstResult.Sensitivity);
        Assert.Equal(SensitivityLevel.None, secondResult.Sensitivity);
    }

    [Theory]
    [InlineData("item", "ITEM")]
    [InlineData("ITEM", "item")]
    public void SetSensitivityKeepsCaseVariantVariablesIndependent(string firstName, string secondName)
    {
        // Arrange
        this.State.Set(firstName, FormulaValue.New("first"), sensitivity: SensitivityLevel.Sensitive);
        this.State.Set(secondName, FormulaValue.New("second"), sensitivity: SensitivityLevel.Sensitive);

        // Act
        this.State.SetSensitivity(secondName, VariableScopeNames.Local, SensitivityLevel.None);

        // Assert
        Assert.Equal("first", Assert.IsType<StringValue>(this.State.Get(firstName)).Value);
        Assert.Equal("second", Assert.IsType<StringValue>(this.State.Get(secondName)).Value);
        Assert.Equal(SensitivityLevel.Sensitive, this.State.GetSensitivity(firstName));
        Assert.Equal(SensitivityLevel.None, this.State.GetSensitivity(secondName));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task RestoreAsync_KeepsCaseVariantVariablesIndependentAsync(bool reverseOrder)
    {
        // Arrange
        Mock<IWorkflowContext> context = new(MockBehavior.Strict);
        HashSet<string> keys = reverseOrder ? ["ITEM", "item"] : ["item", "ITEM"];
        context.Setup(c => c.ReadStateKeysAsync(It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((string? scopeName, CancellationToken _) => string.Equals(scopeName, VariableScopeNames.Local, StringComparison.Ordinal) ? keys : []);
        context.Setup(c => c.ReadStateAsync<PortableValue>("item", VariableScopeNames.Local, It.IsAny<CancellationToken>()))
            .ReturnsAsync(new PortableValue("first"));
        context.Setup(c => c.ReadStateAsync<PortableValue>("ITEM", VariableScopeNames.Local, It.IsAny<CancellationToken>()))
            .ReturnsAsync(new PortableValue("second"));
        string sensitivityScope = WorkflowFormulaState.GetSensitivityScopeName(VariableScopeNames.Local);
        context.Setup(c => c.ReadStateAsync<SensitivityLevel>("item", sensitivityScope, It.IsAny<CancellationToken>()))
            .ReturnsAsync(SensitivityLevel.Sensitive);
        context.Setup(c => c.ReadStateAsync<SensitivityLevel>("ITEM", sensitivityScope, It.IsAny<CancellationToken>()))
            .ReturnsAsync(SensitivityLevel.None);

        // Act
        await this.State.RestoreAsync(context.Object, CancellationToken.None);

        // Assert
        Assert.Equal("first", Assert.IsType<StringValue>(this.State.Get("item")).Value);
        Assert.Equal("second", Assert.IsType<StringValue>(this.State.Get("ITEM")).Value);
        Assert.Equal(SensitivityLevel.Sensitive, this.State.GetSensitivity("item"));
        Assert.Equal(SensitivityLevel.None, this.State.GetSensitivity("ITEM"));
    }

    [Fact]
    public async Task RestoreAsync_RestoresPersistedSensitivityAsync()
    {
        // Arrange
        Mock<IWorkflowContext> context = new(MockBehavior.Strict);
        context.Setup(c => c.ReadStateKeysAsync(It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((string? scopeName, CancellationToken _) => scopeName == VariableScopeNames.Local ? new HashSet<string> { "secret" } : []);
        context.Setup(c => c.ReadStateAsync<PortableValue>("secret", VariableScopeNames.Local, It.IsAny<CancellationToken>()))
            .ReturnsAsync(new PortableValue("secret-value"));
        context.Setup(c => c.ReadStateAsync<SensitivityLevel>("secret", WorkflowFormulaState.GetSensitivityScopeName(VariableScopeNames.Local), It.IsAny<CancellationToken>()))
            .ReturnsAsync(SensitivityLevel.Sensitive);

        // Act
        await this.State.RestoreAsync(context.Object, CancellationToken.None);

        // Assert
        Assert.Equal(SensitivityLevel.Sensitive, this.State.GetSensitivity("secret"));
    }
}
