// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.ObjectModel;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx.Types;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.ObjectModel;

/// <summary>
/// Tests for <see cref="ClearAllVariablesExecutor"/>.
/// </summary>
public sealed class ClearAllVariablesExecutorTest(ITestOutputHelper output) : WorkflowActionExecutorTest(output)
{
    [Fact]
    public async Task ClearWorkflowScope()
    {
        // Arrange
        this.State.Set("NoVar", FormulaValue.New("Old value"));

        ClearAllVariables model =
            this.CreateModel(
                this.FormatDisplayName(nameof(ClearWorkflowScope)),
                VariablesToClear.ConversationScopedVariables);

        // Act
        ClearAllVariablesExecutor action = new(model, this.State);
        await this.Execute(action);

        // Assert
        this.VerifyModel(model, action);
        this.VerifyUndefined("NoVar");
    }

    [Fact]
    public async Task ClearUndefinedScope()
    {
        // Arrange
        ClearAllVariables model =
            this.CreateModel(
                this.FormatDisplayName(nameof(ClearUndefinedScope)),
                VariablesToClear.UserScopedVariables);

        // Act
        ClearAllVariablesExecutor action = new(model, this.State);
        await this.Execute(action);

        // Assert
        this.VerifyModel(model, action);
        this.VerifyUndefined("NoVar");
    }

    private ClearAllVariables CreateModel(string displayName, VariablesToClear variableTarget)
    {
        ClearAllVariables.Builder actionBuilder =
            new()
            {
                Id = this.CreateActionId(),
                DisplayName = this.FormatDisplayName(displayName),
                Variables = EnumExpression<VariablesToClearWrapper>.Literal(VariablesToClearWrapper.Get(variableTarget)),
            };

        ClearAllVariables model = this.AssignParent<ClearAllVariables>(actionBuilder);

        return model;
    }
}
