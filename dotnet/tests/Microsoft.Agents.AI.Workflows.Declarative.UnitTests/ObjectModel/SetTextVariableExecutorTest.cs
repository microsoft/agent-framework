// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;
using Microsoft.Agents.ObjectModel;
using Microsoft.PowerFx.Types;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.ObjectModel;

/// <summary>
/// Tests for <see cref="SetTextVariableExecutor"/>.
/// </summary>
public sealed class SetTextVariableExecutorTest(ITestOutputHelper output) : WorkflowActionExecutorTest(output)
{
    [Fact]
    public async Task SetLiteralValueAsync()
    {
        // Arrange, Act & Assert
        await this.ExecuteTestAsync(
                this.FormatDisplayName(nameof(SetLiteralValueAsync)),
                "TextVar",
                "New value");
    }

    [Fact]
    public async Task UpdateExistingValueAsync()
    {
        // Arrange
        this.State.Set("TextVar", FormulaValue.New("Old value"));

        // Act & Assert
        await this.ExecuteTestAsync(
                this.FormatDisplayName(nameof(UpdateExistingValueAsync)),
                "TextVar",
                "New value");
    }

    private async Task ExecuteTestAsync(
        string displayName,
        string variableName,
        string textValue)
    {
        // Arrange
        SetTextVariable model =
            this.CreateModel(
                displayName,
                variableName,
                textValue);

        // Act
        SetTextVariableExecutor action = new(model, this.State);
        await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);
        this.VerifyState(variableName, FormulaValue.New(textValue));
    }

    private SetTextVariable CreateModel(string displayName, string variablePath, string textValue)
    {
        SetTextVariable.Builder actionBuilder =
            new()
            {
                Id = this.CreateActionId(),
                DisplayName = this.FormatDisplayName(displayName),
                Variable = PropertyPath.Create(FormatVariablePath(variablePath)),
                Value = TemplateLine.Parse(textValue),
            };

        return AssignParent<SetTextVariable>(actionBuilder);
    }
}
