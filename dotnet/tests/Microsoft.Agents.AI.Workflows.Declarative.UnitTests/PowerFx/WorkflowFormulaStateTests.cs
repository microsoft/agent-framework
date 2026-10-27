// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
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

    [Theory]
    [InlineData(VariableScopeNames.Local, VariableScopeNames.Topic, false, false)]
    [InlineData(VariableScopeNames.Topic, VariableScopeNames.Local, false, false)]
    [InlineData(VariableScopeNames.Local, VariableScopeNames.Topic, true, false)]
    [InlineData(VariableScopeNames.Topic, VariableScopeNames.Local, true, false)]
    [InlineData(VariableScopeNames.Local, VariableScopeNames.Topic, false, true)]
    [InlineData(VariableScopeNames.Topic, VariableScopeNames.Local, false, true)]
    public async Task RestoreAsync_PreservesLatestAliasAssignmentAsync(string firstScope, string secondScope, bool sensitive, bool clear)
    {
        // Arrange
        Dictionary<(string? Scope, string Key), PortableValue> values = [];
        Dictionary<(string? Scope, string Key), SensitivityLevel> sensitivities = [];
        Mock<IWorkflowContext> source = CreateStateContext(values, sensitivities);
        DeclarativeWorkflowContext context = new(source.Object, this.State);
        await context.QueueStateUpdateAsync("TestValue", FormulaValue.New("first"), firstScope, SensitivityLevel.Sensitive);
        if (clear)
        {
            await context.QueueClearScopeAsync(secondScope);
        }
        else
        {
            await context.QueueStateUpdateAsync("TestValue", "second", secondScope, sensitive ? SensitivityLevel.Sensitive : SensitivityLevel.None);
        }
        object? expectedValue = this.State.Get("TestValue").ToObject();
        SensitivityLevel expectedSensitivity = this.State.GetSensitivity("TestValue");

        // Act
        WorkflowFormulaState restored = new(RecalcEngineFactory.Create());
        await restored.RestoreAsync(source.Object, CancellationToken.None);

        // Assert
        Assert.Equal(clear ? null : "second", expectedValue);
        Assert.Equal(sensitive ? SensitivityLevel.Sensitive : SensitivityLevel.None, expectedSensitivity);
        Assert.Equal(expectedValue, restored.Get("TestValue", VariableScopeNames.Local).ToObject());
        Assert.Equal(expectedValue, restored.Get("TestValue", VariableScopeNames.Topic).ToObject());
        Assert.Equal(expectedSensitivity, restored.GetSensitivity("TestValue", VariableScopeNames.Local));
        Assert.Equal(expectedSensitivity, restored.GetSensitivity("TestValue", VariableScopeNames.Topic));
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(true, false)]
    [InlineData(false, true)]
    public async Task RestoreAsync_MigratesLegacyTopicStateAsync(bool sensitive, bool clear)
    {
        // Arrange
        string sensitivityScope = WorkflowFormulaState.GetSensitivityScopeName(VariableScopeNames.Local);
        SensitivityLevel sensitivity = sensitive ? SensitivityLevel.Sensitive : SensitivityLevel.None;
        Dictionary<(string? Scope, string Key), PortableValue> values = new()
        {
            [(VariableScopeNames.Local, "OtherValue")] = new("other"),
            [(VariableScopeNames.Topic, "TestValue")] = new(clear ? UnassignedValue.Instance : "legacy"),
        };
        Dictionary<(string? Scope, string Key), SensitivityLevel> sensitivities = new()
        {
            [(sensitivityScope, "TestValue")] = sensitivity,
        };
        Mock<IWorkflowContext> source = CreateStateContext(values, sensitivities);
        DeclarativeWorkflowContext context = new(source.Object, this.State);

        // Act
        await this.State.RestoreAsync(source.Object, CancellationToken.None);

        // Assert
        Assert.Equal(clear ? null : "legacy", this.State.Get("TestValue").ToObject());
        Assert.Equal(sensitivity, this.State.GetSensitivity("TestValue"));
        Assert.Equal("other", this.State.Get("OtherValue").ToObject());
        Assert.DoesNotContain(values.Keys, key => string.Equals(key.Scope, VariableScopeNames.Topic, StringComparison.Ordinal));
        Assert.Contains((VariableScopeNames.Local, "TestValue"), values.Keys);
        Assert.Equal(sensitivity, sensitivities[(sensitivityScope, "TestValue")]);
        if (!clear)
        {
            Assert.Equal("legacy", await context.ReadStateAsync<string>("TestValue", VariableScopeNames.Topic));
            Assert.Equal("legacy", await context.ReadOrInitStateAsync("TestValue", () => "replacement", VariableScopeNames.Topic));
        }

        await context.QueueClearScopeAsync(VariableScopeNames.Topic);
        await this.State.RestoreCheckpointAsync(source.Object, CancellationToken.None);
        Assert.IsType<BlankValue>(this.State.Get("TestValue"));
        Assert.Equal(SensitivityLevel.None, this.State.GetSensitivity("TestValue"));
    }

    [Fact]
    public async Task RestoreAsync_RejectsConflictingAliasEntriesOnEveryAttemptAsync()
    {
        // Arrange
        Dictionary<(string? Scope, string Key), PortableValue> values = new()
        {
            [(VariableScopeNames.Topic, "OtherValue")] = new("other"),
            [(VariableScopeNames.Local, "TestValue")] = new("first"),
            [(VariableScopeNames.Topic, "TestValue")] = new("second"),
        };
        Dictionary<(string? Scope, string Key), SensitivityLevel> sensitivities = [];
        Mock<IWorkflowContext> source = CreateStateContext(values, sensitivities);

        // Act
        DeclarativeActionException first = await Assert.ThrowsAsync<DeclarativeActionException>(
            async () => await this.State.RestoreAsync(source.Object, CancellationToken.None));
        DeclarativeActionException retry = await Assert.ThrowsAsync<DeclarativeActionException>(
            async () => await this.State.RestoreAsync(source.Object, CancellationToken.None));

        // Assert
        Assert.Contains("conflicting", first.Message);
        Assert.Equal(first.Message, retry.Message);
        Assert.Equal(3, values.Count);
        Assert.Empty(sensitivities);
        source.Verify(c => c.QueueStateUpdateAsync(It.IsAny<string>(), It.IsAny<object>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()), Times.Never);
        source.Verify(c => c.QueueClearScopeAsync(It.IsAny<string?>(), It.IsAny<CancellationToken>()), Times.Never);
    }

    [Theory]
    [InlineData(42)]
    [InlineData(42L)]
    [InlineData(1.5f)]
    [InlineData(1.5d)]
    public async Task RestoreAsync_LegacyMigrationPreservesNativeTypesAsync(object value)
    {
        // Arrange
        Dictionary<(string? Scope, string Key), PortableValue> values = new()
        {
            [(VariableScopeNames.Topic, "TestValue")] = new(value),
        };
        Mock<IWorkflowContext> source = CreateStateContext(values, []);

        // Act
        await this.State.RestoreAsync(source.Object, CancellationToken.None);

        // Assert
        PortableValue migrated = values[(VariableScopeNames.Local, "TestValue")];
        Assert.True(migrated.TypeId.IsMatch(value.GetType()));
        Assert.Equal(value, migrated.AsType(value.GetType()));
    }

    private static Mock<IWorkflowContext> CreateStateContext(
        Dictionary<(string? Scope, string Key), PortableValue> values,
        Dictionary<(string? Scope, string Key), SensitivityLevel> sensitivities)
    {
        Mock<IWorkflowContext> source = new(MockBehavior.Strict);
        source.Setup(c => c.QueueStateUpdateAsync(It.IsAny<string>(), It.IsAny<object>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .Callback((string key, object value, string? scope, CancellationToken _) => values[(scope, key)] = new PortableValue(value))
            .Returns(default(ValueTask));
        source.Setup(c => c.QueueStateUpdateAsync(It.IsAny<string>(), It.IsAny<UnassignedValue>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .Callback((string key, UnassignedValue _, string? scope, CancellationToken _) => values.Remove((scope, key)))
            .Returns(default(ValueTask));
        source.Setup(c => c.QueueStateUpdateAsync(It.IsAny<string>(), It.IsAny<SensitivityLevel>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .Callback((string key, SensitivityLevel value, string? scope, CancellationToken _) => sensitivities[(scope, key)] = value)
            .Returns(default(ValueTask));
        source.Setup(c => c.QueueClearScopeAsync(It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .Callback((string? scope, CancellationToken _) =>
            {
                foreach (var key in values.Keys.Where(key => string.Equals(key.Scope, scope, StringComparison.Ordinal)).ToArray())
                {
                    values.Remove(key);
                }
            })
            .Returns(default(ValueTask));
        source.Setup(c => c.ReadStateKeysAsync(It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((string? scope, CancellationToken _) => values.Keys.Where(k => string.Equals(k.Scope, scope, StringComparison.Ordinal)).Select(k => k.Key).ToHashSet());
        source.Setup(c => c.ReadStateAsync<PortableValue>(It.IsAny<string>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((string key, string? scope, CancellationToken _) => values.TryGetValue((scope, key), out PortableValue? value) ? value : null);
        source.Setup(c => c.ReadStateAsync<SensitivityLevel>(It.IsAny<string>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((string key, string? scope, CancellationToken _) => sensitivities.TryGetValue((scope, key), out SensitivityLevel sensitivity) ? sensitivity : SensitivityLevel.None);
        source.Setup(c => c.ReadStateAsync<string>(It.IsAny<string>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((string key, string? scope, CancellationToken _) => values.TryGetValue((scope, key), out PortableValue? value) ? value.As<string>() : null);
        source.Setup(c => c.ReadOrInitStateAsync(It.IsAny<string>(), It.IsAny<Func<string>>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((string key, Func<string> factory, string? scope, CancellationToken _) => values.TryGetValue((scope, key), out PortableValue? value) ? Assert.IsType<string>(value.As<string>()) : factory());
        return source;
    }
}
