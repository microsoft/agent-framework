// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
using Microsoft.Agents.ObjectModel.Abstractions;
using Microsoft.PowerFx.Types;
using Moq;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.Kit;

public sealed class IWorkflowContextExtensionsTests
{
    [Fact]
    public async Task FormatTemplateAsync_WithSensitiveValue_ThrowsAsync()
    {
        // Arrange
        WorkflowFormulaState state = new(RecalcEngineFactory.Create());
        state.Set("SOME_SECRET", FormulaValue.New("secret-value"), VariableScopeNames.Environment, SensitivityLevel.Sensitive);
        state.Bind();
        DeclarativeWorkflowContext context = new(new Mock<IWorkflowContext>().Object, state);

        // Act
        ValueTask<string> FormatAsync() => context.FormatTemplateAsync("={Env.SOME_SECRET}");

        // Assert
        DeclarativeActionException exception = await Assert.ThrowsAsync<DeclarativeActionException>(async () => await FormatAsync());
        Assert.Contains("Cannot return sensitive workflow expression value", exception.Message);
    }

    [Fact]
    public async Task QueueStateUpdateAsync_WithSensitivity_RebindsStateAsync()
    {
        // Arrange
        WorkflowFormulaState state = new(RecalcEngineFactory.Create());
        state.Set("TestValue", FormulaValue.New("old-value"));
        state.Bind();
        DeclarativeWorkflowContext context = new(new Mock<IWorkflowContext>().Object, state);

        // Act
        await context.QueueStateUpdateAsync(PropertyPath.Create("Local.TestValue"), FormulaValue.New("new-value"), SensitivityLevel.Sensitive);

        // Assert
        Assert.Equal("new-value", state.Engine.Eval("Local.TestValue").ToObject());
        Assert.Equal(SensitivityLevel.Sensitive, state.GetSensitivity("TestValue", VariableScopeNames.Local));
    }

    [Fact]
    public async Task ReadStateWithSensitivityAsync_QueuesSensitiveAssignmentAsync()
    {
        // Arrange
        WorkflowFormulaState state = new(RecalcEngineFactory.Create());
        state.Set(SystemScope.Names.LastMessageText, FormulaValue.New("secret-value"), VariableScopeNames.System, SensitivityLevel.Sensitive);
        state.Bind();

        Mock<IWorkflowContext> source = new(MockBehavior.Loose);
        source
            .Setup(c => c.ReadStateAsync<object>(SystemScope.Names.LastMessageText, VariableScopeNames.System, default))
            .Returns(new ValueTask<object?>("secret-value"));
        DeclarativeWorkflowContext context = new(source.Object, state);

        // Act
        var evaluatedValue = await context.ReadStateWithSensitivityAsync<object>(SystemScope.Names.LastMessageText, VariableScopeNames.System);
        await context.QueueStateUpdateWithSensitivityAsync("TestValue", evaluatedValue, VariableScopeNames.Local);

        // Assert
        Assert.Equal("secret-value", state.Engine.Eval("Local.TestValue").ToObject());
        Assert.Equal(SensitivityLevel.Sensitive, state.GetSensitivity("TestValue", VariableScopeNames.Local));
    }

    [Fact]
    public async Task ReadStateWithSensitivityAsync_WithPlainContext_ReadsSensitivitySidecarAsync()
    {
        // Arrange
        Mock<IWorkflowContext> context = new(MockBehavior.Loose);
        context
            .Setup(c => c.ReadStateAsync<object>("TestValue", VariableScopeNames.Local, default))
            .Returns(new ValueTask<object?>("secret-value"));
        context
            .Setup(c => c.ReadStateAsync<SensitivityLevel>("TestValue", WorkflowFormulaState.GetSensitivityScopeName(VariableScopeNames.Local), default))
            .Returns(new ValueTask<SensitivityLevel>(SensitivityLevel.Sensitive));

        // Act
        var evaluatedValue = await context.Object.ReadStateWithSensitivityAsync<object>("TestValue", VariableScopeNames.Local);

        // Assert
        Assert.Equal("secret-value", evaluatedValue.Value);
        Assert.Equal(SensitivityLevel.Sensitive, evaluatedValue.Sensitivity);
    }

    [Fact]
    public async Task QueueStateUpdateWithSensitivityAsync_WithPlainContext_QueuesSensitivitySidecarAsync()
    {
        // Arrange
        Mock<IWorkflowContext> context = new(MockBehavior.Strict);
        context
            .Setup(c => c.QueueStateUpdateAsync("TestValue", "secret-value", VariableScopeNames.Local, default))
            .Returns(default(ValueTask));
        context
            .Setup(c => c.QueueStateUpdateAsync("TestValue", SensitivityLevel.Sensitive, WorkflowFormulaState.GetSensitivityScopeName(VariableScopeNames.Local), default))
            .Returns(default(ValueTask));

        // Act
        await context.Object.QueueStateUpdateWithSensitivityAsync("TestValue", new EvaluationResult<string>("secret-value", SensitivityLevel.Sensitive), VariableScopeNames.Local);

        // Assert
        context.VerifyAll();
    }
}
