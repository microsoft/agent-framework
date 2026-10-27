// Copyright (c) Microsoft. All rights reserved.

using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
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
    [Theory]
    [InlineData(VariableScopeNames.Topic, VariableScopeNames.Local)]
    [InlineData(VariableScopeNames.Local, VariableScopeNames.Local)]
    [InlineData(VariableScopeNames.Global, VariableScopeNames.Global)]
    [InlineData("custom", "custom")]
    [InlineData(null, null)]
    public async Task StateAccess_UsesCanonicalScopeAsync(string? scope, string? expectedScope)
    {
        // Arrange
        Mock<IWorkflowContext> source = new(MockBehavior.Strict);
        source.Setup(c => c.ReadStateAsync<string>("TestValue", expectedScope, It.IsAny<CancellationToken>()))
            .ReturnsAsync("stored");
        source.Setup(c => c.ReadOrInitStateAsync("TestValue", It.IsAny<System.Func<string>>(), expectedScope, It.IsAny<CancellationToken>()))
            .ReturnsAsync("stored");
        source.Setup(c => c.ReadStateKeysAsync(expectedScope, It.IsAny<CancellationToken>()))
            .ReturnsAsync(["TestValue"]);
        DeclarativeWorkflowContext context = new(source.Object, new(RecalcEngineFactory.Create()));

        // Act
        string? value = await context.ReadStateAsync<string>("TestValue", scope);
        string initialized = await context.ReadOrInitStateAsync("TestValue", () => "initial", scope);
        HashSet<string> keys = await context.ReadStateKeysAsync(scope);

        // Assert
        Assert.Equal("stored", value);
        Assert.Equal("stored", initialized);
        Assert.Equal("TestValue", Assert.Single(keys));
        source.VerifyAll();
    }

    [Fact]
    public async Task ReadOrInitStateAsync_FormulaAliasUsesCanonicalScopeAsync()
    {
        // Arrange
        Mock<IWorkflowContext> source = new(MockBehavior.Strict);
        source.Setup(c => c.QueueStateUpdateAsync("TestValue", It.IsAny<object>(), VariableScopeNames.Local, It.IsAny<CancellationToken>()))
            .Returns(default(ValueTask));
        WorkflowFormulaState state = new(RecalcEngineFactory.Create());
        DeclarativeWorkflowContext context = new(source.Object, state);

        // Act
        FormulaValue result = await context.ReadOrInitStateAsync<FormulaValue>("TestValue", () => FormulaValue.New("initial"), VariableScopeNames.Topic);

        // Assert
        Assert.Equal("initial", result.ToObject());
        Assert.Equal("initial", state.Get("TestValue", VariableScopeNames.Local).ToObject());
        source.VerifyAll();
    }

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
    public async Task FormatTemplateWithSensitivityAsync_WithSensitiveValue_ReturnsSensitivityAsync()
    {
        // Arrange
        WorkflowFormulaState state = new(RecalcEngineFactory.Create());
        state.Set("SOME_SECRET", FormulaValue.New("secret-value"), VariableScopeNames.Environment, SensitivityLevel.Sensitive);
        state.Bind();
        DeclarativeWorkflowContext context = new(new Mock<IWorkflowContext>().Object, state);

        // Act
        EvaluationResult<string> result = await context.FormatTemplateWithSensitivityAsync("={Env.SOME_SECRET}");

        // Assert
        Assert.Equal("=secret-value" + System.Environment.NewLine, result.Value);
        Assert.Equal(SensitivityLevel.Sensitive, result.Sensitivity);
    }

    [Fact]
    public async Task EvaluateValueAsync_WithSensitiveValue_ThrowsAsync()
    {
        // Arrange
        WorkflowFormulaState state = new(RecalcEngineFactory.Create());
        state.Set(SystemScope.Names.LastMessageText, FormulaValue.New("secret-value"), VariableScopeNames.System, SensitivityLevel.Sensitive);
        state.Bind();
        DeclarativeWorkflowContext context = new(new Mock<IWorkflowContext>().Object, state);

        // Act
        ValueTask<object?> EvaluateAsync() => context.EvaluateValueAsync<object>("System.LastMessageText");

        // Assert
        DeclarativeActionException exception = await Assert.ThrowsAsync<DeclarativeActionException>(async () => await EvaluateAsync());
        Assert.Contains("Cannot return sensitive workflow expression value", exception.Message);
    }

    [Fact]
    public async Task EvaluateValueWithSensitivityAsync_WithSensitiveValue_ReturnsSensitivityAsync()
    {
        // Arrange
        WorkflowFormulaState state = new(RecalcEngineFactory.Create());
        state.Set(SystemScope.Names.LastMessageText, FormulaValue.New("secret-value"), VariableScopeNames.System, SensitivityLevel.Sensitive);
        state.Bind();
        DeclarativeWorkflowContext context = new(new Mock<IWorkflowContext>().Object, state);

        // Act
        EvaluationResult<object?> result = await context.EvaluateValueWithSensitivityAsync<object>("System.LastMessageText");

        // Assert
        Assert.Equal("secret-value", result.Value);
        Assert.Equal(SensitivityLevel.Sensitive, result.Sensitivity);
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
        context.Setup(c => c.ReadStateKeysAsync(VariableScopeNames.Topic, default)).ReturnsAsync([]);
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
        context.Setup(c => c.ReadStateKeysAsync(VariableScopeNames.Topic, default)).ReturnsAsync([]);
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

    [Fact]
    public async Task GeneratedForeachPattern_WithSensitiveCollection_PreservesItemSensitivityAsync()
    {
        // Arrange
        WorkflowFormulaState state = new(RecalcEngineFactory.Create());
        state.Set(
            "SensitiveItems",
            FormulaValue.NewTable(
                RecordType.Empty(),
                FormulaValue.NewRecordFromFields(new NamedValue("Value", FormulaValue.New("first"))),
                FormulaValue.NewRecordFromFields(new NamedValue("Value", FormulaValue.New("second")))),
            VariableScopeNames.Environment,
            SensitivityLevel.Sensitive);
        state.Bind();
        DeclarativeWorkflowContext context = new(new Mock<IWorkflowContext>().Object, state);

        // Act
        EvaluationResult<object?> evaluatedValue = await context.EvaluateValueWithSensitivityAsync<object>("Env.SensitiveItems");
        IEnumerable values = Assert.IsAssignableFrom<IEnumerable>(evaluatedValue.Value);
        object? firstValue = values.Cast<object?>().First();
        await context.QueueStateUpdateWithSensitivityAsync(
            key: "LoopValue",
            value: new EvaluationResult<object?>(firstValue, evaluatedValue.Sensitivity),
            scopeName: VariableScopeNames.Local);

        // Assert
        Assert.Equal(SensitivityLevel.Sensitive, evaluatedValue.Sensitivity);
        Assert.NotNull(state.Get("LoopValue").ToObject());
        Assert.Equal(SensitivityLevel.Sensitive, state.GetSensitivity("LoopValue"));
    }

    [Fact]
    public async Task ConvertValueWithSensitivityAsync_WithPlainContext_PreservesSensitivitySidecarAsync()
    {
        // Arrange
        Mock<IWorkflowContext> context = new(MockBehavior.Loose);
        context.Setup(c => c.ReadStateKeysAsync(VariableScopeNames.Topic, default)).ReturnsAsync([]);
        context
            .Setup(c => c.ReadStateAsync<PortableValue>("TestValue", VariableScopeNames.Local, default))
            .Returns(new ValueTask<PortableValue?>(new PortableValue("42")));
        context
            .Setup(c => c.ReadStateAsync<SensitivityLevel>("TestValue", WorkflowFormulaState.GetSensitivityScopeName(VariableScopeNames.Local), default))
            .Returns(new ValueTask<SensitivityLevel>(SensitivityLevel.Sensitive));

        // Act
        EvaluationResult<object?> result = await context.Object.ConvertValueWithSensitivityAsync(typeof(decimal), "TestValue", VariableScopeNames.Local);

        // Assert
        Assert.Equal(42M, result.Value);
        Assert.Equal(SensitivityLevel.Sensitive, result.Sensitivity);
    }
}
