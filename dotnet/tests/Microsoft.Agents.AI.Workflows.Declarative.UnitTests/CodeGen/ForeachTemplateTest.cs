// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.CodeGen;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;
using Microsoft.Bot.ObjectModel;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.CodeGen;

public class ForeachTemplateTest(ITestOutputHelper output) : WorkflowActionTemplateTest(output)
{
    [Fact]
    public void LoopNoIndex()
    {
        // Act, Assert
        this.ExecuteTest(
            nameof(LoopNoIndex),
            ValueExpression.Variable(PropertyPath.TopicVariable("MyItems")),
            "LoopValue");
    }

    [Fact]
    public void LoopWithIndex()
    {
        // Act, Assert
        this.ExecuteTest(
            nameof(LoopNoIndex),
            ValueExpression.Variable(PropertyPath.TopicVariable("MyItems")),
            "LoopValue",
            "IndexValue");
    }

    private void ExecuteTest(
        string displayName,
        ValueExpression items,
        string valueName,
        string? indexName = null)
    {
        // Arrange
        Foreach model =
            this.CreateModel(
                displayName,
                items,
                FormatVariablePath(valueName),
                FormatOptionalPath(indexName));

        // Act
        ForeachTemplate template = new(model);
        string workflowCode = template.TransformText();
        this.Output.WriteLine(workflowCode.Trim());

        // Assert
        AssertGeneratedCode<ActionExecutor>(template.Id, workflowCode);
        AssertAgentProvider(template.UseAgentProvider, workflowCode);
        AssertGeneratedMethod(nameof(ForeachExecutor.TakeNextAsync), workflowCode);
        AssertGeneratedMethod(nameof(ForeachExecutor.ResetAsync), workflowCode);
    }

    private Foreach CreateModel(
        string displayName,
        ValueExpression items,
        string valueName,
        string? indexName = null)
    {
        Foreach.Builder actionBuilder =
            new()
            {
                Id = this.CreateActionId("loop_action"),
                DisplayName = this.FormatDisplayName(displayName),
                Items = items,
                Value = PropertyPath.Create(valueName),
            };

        if (indexName is not null)
        {
            actionBuilder.Index = PropertyPath.Create(indexName);
        }

        return actionBuilder.Build();
    }
}
