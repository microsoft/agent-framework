// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.CodeGen;
using Microsoft.Agents.Workflows.Declarative.Kit;
using Microsoft.Agents.Workflows.Declarative.ObjectModel;
using Microsoft.Bot.ObjectModel;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.CodeGen;

public class ConditionGroupTemplateTest(ITestOutputHelper output) : WorkflowActionTemplateTest(output)
{
    [Fact]
    public void NoElse()
    {
        // Act, Assert
        this.ExecuteTest(
            nameof(WithElse),
            hasElse: false);
    }

    [Fact]
    public void WithElse()
    {
        // Act, Assert
        this.ExecuteTest(
            nameof(WithElse),
            hasElse: true);
    }

    private void ExecuteTest(string displayName, bool hasElse = false)
    {
        // Arrange
        ConditionGroup model = this.CreateModel(displayName, hasElse);

        // Act
        ConditionGroupTemplate template = new(model);
        string workflowCode = template.TransformText();
        this.Output.WriteLine(workflowCode.Trim());

        // Assert
        this.AssertGeneratedCode<ActionExecutor>(template.Id, workflowCode);
        this.AssertGeneratedMethod(nameof(ConditionGroupExecutor.DoneAsync), workflowCode);
    }

    private ConditionGroup CreateModel(string displayName, bool hasElse = false)
    {
        ConditionGroup.Builder actionBuilder =
            new()
            {
                Id = this.CreateActionId("condition_group"),
                DisplayName = this.FormatDisplayName(displayName),
            };

        actionBuilder.Conditions.Add(
            new ConditionItem.Builder
            {
                Id = "condition_item_a",
                Condition = BoolExpression.Expression("2 > 3"),
                Actions = this.CreateActions("condition_a"),
            });

        actionBuilder.Conditions.Add(
            new ConditionItem.Builder
            {
                Id = "condition_item_b",
                Condition = BoolExpression.Expression("2 < 3"),
                Actions = this.CreateActions("condition_b"),
            });

        if (hasElse)
        {
            actionBuilder.ElseActions = this.CreateActions("condition_else");
        }

        return actionBuilder.Build();
    }

    private ActionScope.Builder CreateActions(string prefix, int count = 2)
    {
        ActionScope.Builder actions =
            new()
            {
                Id = this.CreateActionId("${prefix}_actions"),
            };
        for (int index = 1; index <= count; ++index)
        {
            actions.Actions.Add(
                new SendActivity.Builder
                {
                    Id = this.CreateActionId($"{prefix}_action_{index}"),
                    Activity = new MessageActivityTemplate
                    {
                        //Value = TemplateLine.Parse($"This is message #{index}"),
                    },
                });
        }

        return actions;
    }
}
