// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.CodeGen;
using Microsoft.Agents.Workflows.Declarative.Kit;
using Microsoft.Bot.ObjectModel;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.CodeGen;

public class InvokeAzureAgentTemplateTest(ITestOutputHelper output) : WorkflowActionTemplateTest(output)
{
    [Fact]
    public void Basic()
    {
        // Act, Assert
        this.ExecuteTest(
            nameof(Basic),
            "TestVariable");
    }

    [Fact]
    public void WithMetadata()
    {
        // Act, Assert
        this.ExecuteTest(
            nameof(WithMetadata),
            "TestVariable");
    }

    private void ExecuteTest(
        string displayName,
        string variableName)
    {
        // Arrange
        InvokeAzureAgent model =
            this.CreateModel(
                displayName,
                FormatVariablePath(variableName));

        // Act
        InvokeAzureAgentTemplate template = new(model);
        string workflowCode = template.TransformText();
        this.Output.WriteLine(workflowCode.Trim());

        // Assert
        this.AssertGeneratedCode<ActionExecutor>(template.Id, workflowCode);
        //this.AssertGeneratedAssignment(model.ConversationId?.Path, workflowCode);
    }

    private InvokeAzureAgent CreateModel(
        string displayName,
        string variablePath)
    {
        InvokeAzureAgent.Builder actionBuilder =
            new()
            {
                Id = this.CreateActionId("create_conversation"),
                DisplayName = this.FormatDisplayName(displayName),
                //ConversationId = InitializablePropertyPath.Create(variablePath),
            };

        return actionBuilder.Build();
    }
}
