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
    public async Task ClearWorkflowScopeAsync()
    {
        // Arrange
        this.State.Set("NoVar", FormulaValue.New("Old value"));
        this.State.Bind();

        ClearAllVariables model =
            this.CreateModel(
                this.FormatDisplayName(nameof(ClearWorkflowScopeAsync)),
                VariablesToClear.ConversationScopedVariables);

        // Act
        ClearAllVariablesExecutor action = new(model, this.State);
        await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);
        this.VerifyUndefined("NoVar");
    }

    [Fact]
    public async Task ClearUndefinedScopeAsync()
    {
        // Arrange
        this.State.Set("NoVar", FormulaValue.New("Old value"));
        this.State.Bind();

        // Arrange
        ClearAllVariables model =
            this.CreateModel(
                this.FormatDisplayName(nameof(ClearUndefinedScopeAsync)),
                VariablesToClear.UserScopedVariables);

        // Act
        ClearAllVariablesExecutor action = new(model, this.State);
        await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);
        this.VerifyState("NoVar", FormulaValue.New("Old value"));
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

        return AssignParent<ClearAllVariables>(actionBuilder);
    }
}
