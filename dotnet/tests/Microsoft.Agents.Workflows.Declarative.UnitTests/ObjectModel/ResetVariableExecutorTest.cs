// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.ObjectModel;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx.Types;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.ObjectModel;

/// <summary>
/// Tests for <see cref="ResetVariableExecutor"/>.
/// </summary>
public sealed class ResetVariableExecutorTest(ITestOutputHelper output) : WorkflowActionExecutorTest(output)
{
    [Fact]
    public async Task ResetDefinedValueAsync()
    {
        // Arrange
        this.State.Set("MyVar1", FormulaValue.New("Value #1"));
        this.State.Set("MyVar2", FormulaValue.New("Value #2"));

        ResetVariable model =
            this.CreateModel(
                this.FormatDisplayName(nameof(ResetDefinedValueAsync)),
                FormatVariablePath("MyVar1"));

        // Act
        ResetVariableExecutor action = new(model, this.State);
        await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);
        this.VerifyUndefined("MyVar1");
        this.VerifyState("MyVar2", FormulaValue.New("Value #2"));
    }

    [Fact]
    public async Task ResetUndefinedValueAsync()
    {
        // Arrange
        this.State.Set("MyVar1", FormulaValue.New("Value #1"));

        ResetVariable model =
            this.CreateModel(
                this.FormatDisplayName(nameof(ResetUndefinedValueAsync)),
                FormatVariablePath("NoVar"));

        // Act
        ResetVariableExecutor action = new(model, this.State);
        await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);
        this.VerifyUndefined("NoVar");
        this.VerifyState("MyVar1", FormulaValue.New("Value #1"));
    }

    private ResetVariable CreateModel(string displayName, string variablePath)
    {
        ResetVariable.Builder actionBuilder =
            new()
            {
                Id = this.CreateActionId(),
                DisplayName = this.FormatDisplayName(displayName),
                Variable = InitializablePropertyPath.Create(variablePath),
            };

        return AssignParent<ResetVariable>(actionBuilder);
    }
}
