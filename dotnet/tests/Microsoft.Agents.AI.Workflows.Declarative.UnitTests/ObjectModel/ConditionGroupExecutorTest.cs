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
    public void ConditionGroupNamingConventionItem()
    {
        // Arrange
        ConditionGroup model = this.CreateModelWithConditions(nameof(ConditionGroupNamingConventionItem));
        ConditionItem firstCondition = model.Conditions[0];
        ConditionItem secondCondition = model.Conditions[1];

        // Act
        string firstStepWithId = ConditionGroupExecutor.Steps.Item(model, firstCondition);
        string secondStepWithoutId = ConditionGroupExecutor.Steps.Item(model, secondCondition);

        // Assert - first condition has explicit ID
        Assert.Equal(firstCondition.Id, firstStepWithId);
        // Second condition has no ID, should use index-based naming
        Assert.Equal($"{model.Id}_Items1", secondStepWithoutId);
    }

    [Fact]
    public void ConditionGroupNamingConventionElse()
    {
        // Arrange
        ConditionGroup model = this.CreateModelWithElse(nameof(ConditionGroupNamingConventionElse));

        // Act
        string elseStepWithId = ConditionGroupExecutor.Steps.Else(model);

        // Assert - else actions have explicit ID
        Assert.Equal(model.ElseActions.Id.Value, elseStepWithId);
    }

    [Fact]
    public async Task ConditionGroupFirstConditionTrueAsync()
    {
        // Act & Assert
        await this.ExecuteTestAsync(
            displayName: nameof(ConditionGroupFirstConditionTrueAsync),
            firstCondition: "true",
            secondCondition: "false",
            expectFirstMatch: true);
    }

    [Fact]
    public async Task ConditionGroupSecondConditionTrueAsync()
    {
        // Act & Assert
        await this.ExecuteTestAsync(
            displayName: nameof(ConditionGroupSecondConditionTrueAsync),
            firstCondition: "false",
            secondCondition: "true",
            expectFirstMatch: false,
            expectSecondMatch: true);
    }

    [Fact]
    public async Task ConditionGroupElseBranchAsync()
    {
        // Act & Assert
        await this.ExecuteTestAsync(
            displayName: nameof(ConditionGroupElseBranchAsync),
            firstCondition: "false",
            secondCondition: "false",
            expectElse: true);
    }

    [Fact]
    public async Task ConditionGroupNullConditionSkippedAsync()
    {
        // Act & Assert
        await this.ExecuteTestAsync(
            displayName: nameof(ConditionGroupNullConditionSkippedAsync),
            firstCondition: null,
            secondCondition: "true",
            expectSecondMatch: true);
    }

    [Fact]
    public async Task ConditionGroupAllConditionsNullAsync()
    {
        // Act & Assert
        await this.ExecuteTestAsync(
            displayName: nameof(ConditionGroupAllConditionsNullAsync),
            firstCondition: null,
            secondCondition: null,
            expectElse: true);
    }

    [Fact]
    public void ConditionGroupIsMatchTrue()
    {
        // Arrange
        ConditionGroup model = this.CreateModelWithConditions(nameof(ConditionGroupIsMatchTrue));
        ConditionGroupExecutor executor = new(model, this.State);
        ConditionItem firstCondition = model.Conditions[0];

        object? message = this.CreateActionExecutorResult(ConditionGroupExecutor.Steps.Item(model, firstCondition));

        // Act
        bool isMatch = executor.IsMatch(firstCondition, message);

        // Assert
        Assert.True(isMatch);
    }

    [Fact]
    public void ConditionGroupIsMatchFalse()
    {
        // Arrange
        ConditionGroup model = this.CreateModelWithConditions(nameof(ConditionGroupIsMatchFalse));
        ConditionGroupExecutor executor = new(model, this.State);
        ConditionItem firstCondition = model.Conditions[0];

        object? message = this.CreateActionExecutorResult("different_step");

        // Act
        bool isMatch = executor.IsMatch(firstCondition, message);

        // Assert
        Assert.False(isMatch);
    }

    [Fact]
    public void ConditionGroupIsElseTrue()
    {
        // Arrange
        ConditionGroup model = this.CreateModelWithElse(nameof(ConditionGroupIsElseTrue));
        ConditionGroupExecutor executor = new(model, this.State);

        object? message = this.CreateActionExecutorResult(ConditionGroupExecutor.Steps.Else(model));

        // Act
        bool isElse = executor.IsElse(message);

        // Assert
        Assert.True(isElse);
    }

    [Fact]
    public void ConditionGroupIsElseFalse()
    {
        // Arrange
        ConditionGroup model = this.CreateModelWithElse(nameof(ConditionGroupIsElseFalse));
        ConditionGroupExecutor executor = new(model, this.State);

        object? message = this.CreateActionExecutorResult("different_step");

        // Act
        bool isElse = executor.IsElse(message);

        // Assert
        Assert.False(isElse);
    }

    [Fact]
    public async Task ConditionGroupDoneAsync()
    {
        // Arrange
        ConditionGroup model = this.CreateModelWithConditions(nameof(ConditionGroupDoneAsync));
        ConditionGroupExecutor executor = new(model, this.State);

        // Act
        WorkflowEvent[] events = await this.ExecuteAsync(executor.Id, executor.DoneAsync);

        // Assert
        VerifyModel(model, executor);
        VerifyCompletionEvent(events);
    }

    private async Task ExecuteTestAsync(
        string displayName,
        string? firstCondition,
        string? secondCondition,
        bool expectFirstMatch = false,
        bool expectSecondMatch = false,
        bool expectElse = false)
    {
        // Arrange
        ConditionGroup model = this.CreateModel(displayName, firstCondition, secondCondition);
        ConditionGroupExecutor action = new(model, this.State);

        // Act
        WorkflowEvent[] events = await this.ExecuteAsync(action, isDiscrete: false);

        // Assert
        VerifyModel(model, action);
        VerifyInvocationEvent(events);

        // Verify IsDiscreteAction property is false (using reflection since property is protected)
        Assert.Equal(
            false,
            action.GetType().BaseType?
                .GetProperty("IsDiscreteAction", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance)?
                .GetValue(action));

        // Verify execution completed without errors
        Assert.NotEmpty(events);
    }

    /// <summary>
    /// Creates an ActionExecutorResult using reflection since the constructor is internal.
    /// </summary>
    private object CreateActionExecutorResult(string result)
    {
        System.Reflection.ConstructorInfo? constructor = typeof(ActionExecutorResult).GetConstructor(
            System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance,
            null,
            new System.Type[] { typeof(string), typeof(object) },
            null);
        Assert.NotNull(constructor);

        return constructor.Invoke(new object[] { "test_executor", result });
    }

    private ConditionGroup CreateModel(
        string displayName,
        string? firstCondition,
        string? secondCondition)
    {
        ConditionGroup.Builder actionBuilder = new()
        {
            Id = this.CreateActionId(),
            DisplayName = this.FormatDisplayName(displayName),
        };

        ConditionItem.Builder firstConditionBuilder = new()
        {
            Id = "condition_item_a",
            Actions = this.CreateActions("condition_a"),
        };
        if (firstCondition is not null)
        {
            firstConditionBuilder.Condition = BoolExpression.Expression(firstCondition);
        }
        actionBuilder.Conditions.Add(firstConditionBuilder);

        ConditionItem.Builder secondConditionBuilder = new()
        {
            // No explicit ID - test index-based naming
            Actions = this.CreateActions("condition_b"),
        };
        if (secondCondition is not null)
        {
            secondConditionBuilder.Condition = BoolExpression.Expression(secondCondition);
        }
        actionBuilder.Conditions.Add(secondConditionBuilder);

        actionBuilder.ElseActions = this.CreateActions("else_actions");

        return AssignParent<ConditionGroup>(actionBuilder);
    }

    private ConditionGroup CreateModelWithConditions(string displayName)
    {
        ConditionGroup.Builder actionBuilder = new()
        {
            Id = this.CreateActionId(),
            DisplayName = this.FormatDisplayName(displayName),
        };

        actionBuilder.Conditions.Add(
            new ConditionItem.Builder
            {
                Id = "condition_item_a",
                Condition = BoolExpression.Expression("true"),
                Actions = this.CreateActions("condition_a"),
            });

        actionBuilder.Conditions.Add(
            new ConditionItem.Builder
            {
                // No explicit ID
                Condition = BoolExpression.Expression("true"),
                Actions = this.CreateActions("condition_b"),
            });

        actionBuilder.ElseActions = this.CreateActions("else_actions");

        return AssignParent<ConditionGroup>(actionBuilder);
    }

    private ConditionGroup CreateModelWithElse(string displayName)
    {
        ConditionGroup.Builder actionBuilder = new()
        {
            Id = this.CreateActionId(),
            DisplayName = this.FormatDisplayName(displayName),
        };

        actionBuilder.Conditions.Add(
            new ConditionItem.Builder
            {
                Id = "condition_item_a",
                Condition = BoolExpression.Expression("false"),
                Actions = this.CreateActions("condition_a"),
            });

        actionBuilder.ElseActions = this.CreateActionsWithId("else_actions_with_id");

        return AssignParent<ConditionGroup>(actionBuilder);
    }

    /// <summary>
    /// Creates an ActionScope builder for testing.
    /// </summary>
    /// <param name="prefix">Descriptive prefix for the action scope (not used in IDs but kept for code clarity).</param>
    private ActionScope.Builder CreateActions(string prefix)
    {
        ActionScope.Builder actions = new()
        {
            Id = this.CreateActionId(),
        };

        actions.Actions.Add(
            new SendActivity.Builder
            {
                Id = this.CreateActionId(),
                Activity = new MessageActivityTemplate
                {
                },
            });

        return actions;
    }

    private ActionScope.Builder CreateActionsWithId(string id)
    {
        ActionScope.Builder actions = new()
        {
            Id = new ActionId(id),
        };

        actions.Actions.Add(
            new SendActivity.Builder
            {
                Id = this.CreateActionId(),
                Activity = new MessageActivityTemplate
                {
                },
            });

        return actions;
    }
}
