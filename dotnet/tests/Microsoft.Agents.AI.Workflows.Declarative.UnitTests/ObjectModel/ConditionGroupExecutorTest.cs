// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;
using Microsoft.Agents.ObjectModel;
using Microsoft.PowerFx.Types;

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

    [Theory]
    [InlineData(VariableScopeNames.Environment, "Env", true)]
    [InlineData(VariableScopeNames.Environment, "Env", false)]
    [InlineData(VariableScopeNames.Local, "Local", true)]
    [InlineData(VariableScopeNames.Local, "Local", false)]
    public async Task ConditionGroupRejectsSensitiveConditionAsync(string scope, string alias, bool matches)
    {
        // Arrange
        this.State.Set("Setting", FormulaValue.New(matches ? "enabled" : "disabled"), scope, SensitivityLevel.Sensitive);
        ConditionGroup.Builder builder = this.CreateModel(
            nameof(ConditionGroupRejectsSensitiveConditionAsync), [true], includeElse: true).ToBuilder();
        builder.Conditions[0].Condition = BoolExpression.Expression($"Left({alias}.Setting, 2) = \"en\"").ToBuilder();
        ConditionGroupExecutor action = new(AssignParent<ConditionGroup>(builder), this.State);

        // Act
        Task ExecuteAsync() => this.ExecuteAsync(action, isDiscrete: false);

        // Assert
        DeclarativeActionException exception = await Assert.ThrowsAsync<DeclarativeActionException>(ExecuteAsync);
        Assert.Contains("condition", exception.Message);
        Assert.DoesNotContain(matches ? "enabled" : "disabled", exception.Message);
    }

    [Theory]
    [InlineData(true, "If(Env.Setting, false)")]
    [InlineData(false, "If(Env.Setting, false)")]
    [InlineData(true, "If(Env.Setting, 1 / 0 = 0, false)")]
    [InlineData(false, "If(Env.Setting, 1 / 0 = 0, false)")]
    public async Task ConditionGroupValidatesConditionalResultsAsync(bool value, string expression)
    {
        // Arrange
        this.State.Set("Setting", FormulaValue.New(value), VariableScopeNames.Environment, SensitivityLevel.Sensitive);
        ConditionGroup.Builder builder = this.CreateModel(
            nameof(ConditionGroupValidatesConditionalResultsAsync), [true], includeElse: true).ToBuilder();
        builder.Conditions[0].Condition = BoolExpression.Expression(expression).ToBuilder();
        ConditionGroupExecutor action = new(AssignParent<ConditionGroup>(builder), this.State);

        // Act
        Task ExecuteAsync() => this.ExecuteAsync(action, isDiscrete: false);

        // Assert
        DeclarativeActionException exception = await Assert.ThrowsAsync<DeclarativeActionException>(ExecuteAsync);
        Assert.Contains("condition", exception.Message);
        Assert.DoesNotContain("ErrDivByZero", exception.Message);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task ConditionGroupAllowsNonSensitiveConditionAsync(bool matches)
    {
        // Arrange
        this.State.Set("Setting", FormulaValue.New(matches ? "enabled" : "disabled"));
        ConditionGroup.Builder builder = this.CreateModel(
            nameof(ConditionGroupAllowsNonSensitiveConditionAsync), [true], includeElse: true).ToBuilder();
        builder.Conditions[0].Condition = BoolExpression.Expression("Left(Local.Setting, 2) = \"en\"").ToBuilder();
        ConditionGroup model = AssignParent<ConditionGroup>(builder);
        ConditionGroupExecutor action = new(model, this.State);
        string? selectedStep = null;

        // Act
        await this.ExecuteAsync(action, "capture_condition", (context, message, cancellationToken) =>
        {
            selectedStep = Assert.IsType<string>(message.Result);
            return default;
        });

        // Assert
        Assert.Equal(
            matches ? ConditionGroupExecutor.Steps.Item(model, model.Conditions[0]) : ConditionGroupExecutor.Steps.Else(model),
            selectedStep);
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
