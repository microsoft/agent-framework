// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
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
}
