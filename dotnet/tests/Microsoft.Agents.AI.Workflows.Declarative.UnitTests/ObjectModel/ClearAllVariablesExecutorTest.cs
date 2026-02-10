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
    public async Task ClearWorkflowScopeAsync()
    {
        // Arrange
        this.State.Set("NoVar", FormulaValue.New("Old value"));
        this.State.Bind();

        // Act & Assert
        await this.ExecuteTestAsync(
                this.FormatDisplayName(nameof(ClearUndefinedScopeAsync)),
                VariablesToClear.ConversationScopedVariables,
                "NoVar");
    }

    [Fact]
    public async Task ClearUndefinedScopeAsync()
    {
        // Arrange
        this.State.Set("NoVar", FormulaValue.New("Old value"));
        this.State.Bind();

        // Act & Assert
        await this.ExecuteTestAsync(
                this.FormatDisplayName(nameof(ClearUndefinedScopeAsync)),
                VariablesToClear.UserScopedVariables,
                "NoVar",
                FormulaValue.New("Old value"));
    }

    private async Task ExecuteTestAsync(
        string displayName,
        VariablesToClear scope,
        string variableName,
        FormulaValue? expectedValue = null)
    {
        // Arrange
        ClearAllVariables model = this.CreateModel(
            this.FormatDisplayName(displayName),
            scope);

        ClearAllVariablesExecutor action = new(model, this.State);

        // Act
        await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);

        if (expectedValue is null)
        {
            this.VerifyUndefined(variableName);
        }
        else
        {
            this.VerifyState(variableName, expectedValue);
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
