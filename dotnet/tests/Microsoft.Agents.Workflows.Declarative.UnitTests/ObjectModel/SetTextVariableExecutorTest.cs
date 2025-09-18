// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.ObjectModel;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx.Types;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.ObjectModel;

/// <summary>
/// Tests for <see cref="SetTextVariableExecutor"/>.
/// </summary>
public sealed class SetTextVariableExecutorTest(ITestOutputHelper output) : WorkflowActionExecutorTest(output)
{
    [Fact]
    public async Task SetLiteralValueAsync()
    {
        // Arrange
        SetTextVariable model =
            this.CreateModel(
                this.FormatDisplayName(nameof(SetLiteralValueAsync)),
                FormatVariablePath("TextVar"),
                "Text variable value");

        // Act
        SetTextVariableExecutor action = new(model, this.State);
        await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);
        this.VerifyState("TextVar", FormulaValue.New("Text variable value"));
    }

    [Fact]
    public async Task UpdateExistingValueAsync()
    {
        // Arrange
        this.State.Set("TextVar", FormulaValue.New("Old value"));

        SetTextVariable model =
            this.CreateModel(
                this.FormatDisplayName(nameof(UpdateExistingValueAsync)),
                FormatVariablePath("TextVar"),
                "New value");

        // Act
        SetTextVariableExecutor action = new(model, this.State);
        await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);
        this.VerifyState("TextVar", FormulaValue.New("New value"));
    }

    private SetTextVariable CreateModel(string displayName, string variablePath, string textValue)
    {
        SetTextVariable.Builder actionBuilder =
            new()
            {
                Id = this.CreateActionId(),
                DisplayName = this.FormatDisplayName(displayName),
                Variable = InitializablePropertyPath.Create(variablePath),
                Value = TemplateLine.Parse(textValue),
            };

        return AssignParent<SetTextVariable>(actionBuilder);
    }
}
