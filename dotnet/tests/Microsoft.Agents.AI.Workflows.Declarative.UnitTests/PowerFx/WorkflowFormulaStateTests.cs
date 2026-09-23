// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
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

    [Fact]
    public async Task DeclarativeContextFallbackSessionId_IsScopedToPersistedRunStateAsync()
    {
        // Arrange
        Dictionary<string, string> firstRunState = [];
        Dictionary<string, string> secondRunState = [];
        IWorkflowContext firstContext = CreateContext(firstRunState);
        IWorkflowContext restoredContext = CreateContext(firstRunState);
        IWorkflowContext secondContext = CreateContext(secondRunState);

        // Act
        DeclarativeWorkflowContext first =
            await DeclarativeWorkflowContext.CreateAsync(firstContext, this.State);
        DeclarativeWorkflowContext continued =
            await DeclarativeWorkflowContext.CreateAsync(firstContext, this.State);
        DeclarativeWorkflowContext restored =
            await DeclarativeWorkflowContext.CreateAsync(restoredContext, this.State);
        DeclarativeWorkflowContext second =
            await DeclarativeWorkflowContext.CreateAsync(secondContext, this.State);

        // Assert
        Assert.Equal(first.SessionId, continued.SessionId);
        Assert.Equal(first.SessionId, restored.SessionId);
        Assert.NotEqual(first.SessionId, second.SessionId);
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

    private static IWorkflowContext CreateContext(Dictionary<string, string> state)
    {
        Mock<IWorkflowContext> context = new();
        context
            .Setup(current => current.ReadOrInitStateAsync(
                It.IsAny<string>(),
                It.IsAny<Func<string>>(),
                It.IsAny<string?>(),
                It.IsAny<CancellationToken>()))
            .Returns((string key, Func<string> factory, string? scopeName, CancellationToken cancellationToken) =>
            {
                if (!state.TryGetValue(key, out string? value))
                {
                    value = factory();
                    state[key] = value;
                }

                return new ValueTask<string>(value);
            });
        return context.Object;
    }
}
