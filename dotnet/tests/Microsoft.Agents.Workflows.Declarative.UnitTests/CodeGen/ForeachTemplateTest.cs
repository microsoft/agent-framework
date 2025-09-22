// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.CodeGen;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.Kit;
using Microsoft.Agents.Workflows.Declarative.ObjectModel;
using Microsoft.Bot.ObjectModel;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.CodeGen;

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
        this.AssertGeneratedCode<ActionExecutor>(template.Id, workflowCode);
        this.AssertGeneratedMethod(nameof(ForeachExecutor.TakeNextAsync), workflowCode);
        this.AssertGeneratedMethod(nameof(ForeachExecutor.ResetAsync), workflowCode);
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
                Value = InitializablePropertyPath.Create(valueName),
                Index = indexName is null ? null : InitializablePropertyPath.Create(indexName, false),
            };

        return actionBuilder.Build();
    }
}
