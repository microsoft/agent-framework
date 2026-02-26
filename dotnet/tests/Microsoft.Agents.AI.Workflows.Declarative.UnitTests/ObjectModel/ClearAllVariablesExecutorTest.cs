// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;
using Microsoft.Agents.ObjectModel;
using Microsoft.PowerFx.Types;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.ObjectModel;

/// <summary>
/// Tests for <see cref="ClearAllVariablesExecutor"/>.
/// </summary>
public sealed class ClearAllVariablesExecutorTest(ITestOutputHelper output) : WorkflowActionExecutorTest(output)
{
    [Fact]
    public async Task ClearGlobalScopeAsync()
    {
        // Arrange
        this.State.Set("GlobalVar", FormulaValue.New("Old value"), VariableScopeNames.Global);

        // Act & Assert
        await this.ExecuteTestAsync(
                this.FormatDisplayName(nameof(ClearGlobalScopeAsync)),
                VariablesToClear.AllGlobalVariables,
                "GlobalVar",
                VariableScopeNames.Global);
    }

    [Fact]
    public async Task ClearWorkflowScopeAsync()
    {
        // Arrange
        this.State.Set("LocalVar", FormulaValue.New("Old value"));

        // Act & Assert
        await this.ExecuteTestAsync(
                this.FormatDisplayName(nameof(ClearWorkflowScopeAsync)),
                VariablesToClear.ConversationScopedVariables,
                "LocalVar");
    }

    [Fact]
    public async Task ClearUserScopeAsync()
    {
        // Arrange
        this.State.Set("LocalVar", FormulaValue.New("Old value"));

        // Act & Assert
        await this.ExecuteTestAsync(
                this.FormatDisplayName(nameof(ClearUserScopeAsync)),
                VariablesToClear.UserScopedVariables,
                "LocalVar",
                expectedValue: FormulaValue.New("Old value"));
    }

    [Fact]
    public async Task ClearWorkflowHistoryAsync()
    {
        // Arrange
        this.State.Set("LocalVar", FormulaValue.New("Old value"));

        // Act & Assert
        await this.ExecuteTestAsync(
                this.FormatDisplayName(nameof(ClearWorkflowHistoryAsync)),
                VariablesToClear.ConversationHistory,
                "LocalVar",
                expectedValue: FormulaValue.New("Old value"));
    }

    private async Task ExecuteTestAsync(
        string displayName,
        VariablesToClear scope,
        string variableName,
        string variableScope = VariableScopeNames.Local,
        FormulaValue? expectedValue = null)
    {
        // Arrange
        ClearAllVariables model = this.CreateModel(
            this.FormatDisplayName(displayName),
            scope);

        ClearAllVariablesExecutor action = new(model, this.State);

        this.State.Bind();

        // Act
        await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);
        this.VerifyUndefined("NoVar");
        if (expectedValue is null)
        {
            this.VerifyUndefined(variableName, variableScope);
        }
        else
        {
            this.VerifyState(variableName, variableScope, expectedValue);
        }
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
