// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;
using Microsoft.Agents.ObjectModel;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.ObjectModel;

/// <summary>
/// Tests for <see cref="ConditionGroupExecutor"/>.
/// </summary>
public sealed class ConditionGroupExecutorTest(ITestOutputHelper output) : WorkflowActionExecutorTest(output)
{
    [Fact]
    public void ConditionGroupThrowsWhenModelInvalid() =>
        // Arrange, Act & Assert
        Assert.Throws<DeclarativeModelException>(() => new ConditionGroupExecutor(new ConditionGroup(), this.State));

    [Fact]
    public void ConditionGroupDefaultNaming()
    {
        // Arrange
        ConditionGroup model = this.CreateModel(nameof(ConditionGroupDefaultNaming), [false], includeElse: true, defineActionIds: false);
        ConditionItem condition = model.Conditions[0];

        // Act
        string conditionStepId = ConditionGroupExecutor.Steps.Item(model, condition);
        string elseStepId = ConditionGroupExecutor.Steps.Else(model);

        // Assert
        Assert.Equal($"{model.Id}_Items0", conditionStepId);
        Assert.Equal(model.ElseActions.Id.Value, elseStepId);
    }

    [Fact]
    public void ConditionGroupExplicitNaming()
    {
        // Arrange
        ConditionGroup model = this.CreateModel(nameof(ConditionGroupExplicitNaming), [false], includeElse: true);
        ConditionItem condition = model.Conditions[0];

        // Act
        string conditionStepId = ConditionGroupExecutor.Steps.Item(model, condition);
        string elseStepId = ConditionGroupExecutor.Steps.Else(model);

        // Assert
        Assert.Equal(condition.Id, conditionStepId);
        Assert.Equal(model.ElseActions.Id.Value, elseStepId);
    }

    [Fact]
    public async Task ConditionGroupFirstConditionTrueAsync()
    {
        // Arrange, Act & Assert
        await this.ExecuteTestAsync(
            displayName: nameof(ConditionGroupFirstConditionTrueAsync),
            conditions: [true, false]);
    }

    [Fact]
    public async Task ConditionGroupSecondConditionTrueAsync()
    {
        // Arrange, Act & Assert
        await this.ExecuteTestAsync(
            displayName: nameof(ConditionGroupSecondConditionTrueAsync),
            conditions: [false, true]);
    }

    [Fact]
    public async Task ConditionGroupFirstConditionNullAsync()
    {
        // Arrange, Act & Assert
        await this.ExecuteTestAsync(
            displayName: nameof(ConditionGroupFirstConditionNullAsync),
            conditions: [null, true]);
    }

    [Fact]
    public async Task ConditionGroupElseBranchAsync()
    {
        // Arrange, Act & Assert
        await this.ExecuteTestAsync(
            displayName: nameof(ConditionGroupElseBranchAsync),
            conditions: [false, false],
            includeElse: true);
    }

    [Fact]
    public async Task ConditionGroupDoneAsync()
    {
        ConditionGroup model = this.CreateModel(nameof(ConditionGroupDoneAsync), [true]);
        ConditionGroupExecutor action = new(model, this.State);

        // Act
        WorkflowEvent[] events = await this.ExecuteAsync("condition_done_id", action.DoneAsync);

        // Assert
        VerifyModel(model, action);

        Assert.NotEmpty(events);
        VerifyCompletionEvent(events);
    }

    [Fact]
    public void ConditionGroupIsMatchTrue()
    {
        // Arrange
        ConditionGroup model = this.CreateModel(nameof(ConditionGroupIsMatchTrue), [true]);
        ConditionItem firstCondition = model.Conditions[0];
        ConditionGroupExecutor executor = new(model, this.State);
        ActionExecutorResult result = new(executor.Id, ConditionGroupExecutor.Steps.Item(model, firstCondition));

        // Act
        bool isMatch = executor.IsMatch(firstCondition, result);

        // Assert
        Assert.True(isMatch);
    }

    [Fact]
    public void ConditionGroupIsMatchFalse()
    {
        // Arrange
        ConditionGroup model = this.CreateModel(nameof(ConditionGroupIsMatchFalse), [true, false]);
        ConditionItem firstCondition = model.Conditions[0];
        ConditionItem secondCondition = model.Conditions[1];
        ConditionGroupExecutor executor = new(model, this.State);
        ActionExecutorResult result = new(executor.Id, ConditionGroupExecutor.Steps.Item(model, secondCondition));

        // Act
        bool isMatch = executor.IsMatch(firstCondition, result);

        // Assert
        Assert.False(isMatch);
    }

    [Fact]
    public void ConditionGroupIsElseTrue()
    {
        // Arrange
        ConditionGroup model = this.CreateModel(nameof(ConditionGroupIsElseTrue), [false]);
        ConditionGroupExecutor executor = new(model, this.State);
        ActionExecutorResult result = new(executor.Id, ConditionGroupExecutor.Steps.Else(model));

        // Act
        bool isElse = executor.IsElse(result);

        // Assert
        Assert.True(isElse);
    }

    [Fact]
    public void ConditionGroupIsElseFalse()
    {
        // Arrange
        ConditionGroup model = this.CreateModel(nameof(ConditionGroupIsElseFalse), [false]);
        ConditionGroupExecutor executor = new(model, this.State);
        ActionExecutorResult result = new(executor.Id, "different_step");

        // Act
        bool isElse = executor.IsElse(result);

        // Assert
        Assert.False(isElse);
    }

    private async Task ExecuteTestAsync(
        string displayName,
        bool?[] conditions,
        bool includeElse = false)
    {
        // Arrange
        ConditionGroup model = this.CreateModel(displayName, conditions, includeElse);
        ConditionGroupExecutor action = new(model, this.State);

        // Act
        WorkflowEvent[] events = await this.ExecuteAsync(action, isDiscrete: false);

        // Assert
        VerifyModel(model, action);

        Assert.NotEmpty(events);
        VerifyInvocationEvent(events);

        VerifyIsDiscrete(action, isDiscrete: false);
    }

    private ConditionGroup CreateModel(
        string displayName,
        bool?[] conditions,
        bool includeElse = false,
        bool defineActionIds = true)
    {
        ConditionGroup.Builder actionBuilder = new()
        {
            Id = this.CreateActionId(),
            DisplayName = this.FormatDisplayName(displayName),
        };

        for (int index = 0; index < conditions.Length; ++index)
        {
            bool? condition = conditions[index];

            ConditionItem.Builder conditionBuilder = new()
            {
                Id = defineActionIds ? $"condition_{index}" : null,
                Actions = this.CreateActions(defineActionIds ? $"condition_actions_{index}" : null),
                Condition = condition is null ? null : BoolExpression.Literal(condition.Value).ToBuilder(),
            };

            actionBuilder.Conditions.Add(conditionBuilder);
        }

        if (includeElse)
        {
            actionBuilder.ElseActions = this.CreateActions(defineActionIds ? "else_actions" : null);
        }

        return AssignParent<ConditionGroup>(actionBuilder);
    }

    private ActionScope.Builder CreateActions(string? actionScopeId)
    {
        ActionScope.Builder actions = [];

        if (actionScopeId is not null)
        {
            actions.Id = new ActionId(actionScopeId);
        }

        actions.Actions.Add(
            new SendActivity.Builder
            {
                Id = $"{actionScopeId ?? "action"}_send_activity",
                Activity = new MessageActivityTemplate(),
            });

        return actions;
    }
}
