// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Agents.AI.Workflows.Declarative.CodeGen;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Bot.ObjectModel;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.CodeGen;

public class CreateConversationTemplateTest(ITestOutputHelper output) : WorkflowActionTemplateTest(output)
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
        Dictionary<string, string> metadata =
            new()
            {
                ["key1"] = "value1",
                ["key2"] = "value2",
            };

        // Act, Assert
        this.ExecuteTest(
            nameof(WithMetadata),
            "TestVariable",
            ObjectExpression<RecordDataValue>.Literal(metadata.ToRecordValue()));
    }

    private void ExecuteTest(
        string displayName,
        string variableName,
        ObjectExpression<RecordDataValue>? metadata = null)
    {
        // Arrange
        CreateConversation model =
            this.CreateModel(
                displayName,
                FormatVariablePath(variableName),
                metadata);

        // Act
        CreateConversationTemplate template = new(model);
        string workflowCode = template.TransformText();
        this.Output.WriteLine(workflowCode.Trim());

        // Assert
        AssertGeneratedCode<ActionExecutor>(template.Id, workflowCode);
        AssertAgentProvider(template.UseAgentProvider, workflowCode);
        AssertGeneratedAssignment(model.ConversationId?.Path, workflowCode);
    }

    private CreateConversation CreateModel(
        string displayName,
        string variablePath,
        ObjectExpression<RecordDataValue>? metadata = null)
    {
        CreateConversation.Builder actionBuilder =
            new()
            {
                Id = this.CreateActionId("create_conversation"),
                DisplayName = this.FormatDisplayName(displayName),
                ConversationId = PropertyPath.Create(variablePath),
            };

        if (metadata is not null)
        {
            actionBuilder.Metadata = metadata;
        }

        return actionBuilder.Build();
    }
}
