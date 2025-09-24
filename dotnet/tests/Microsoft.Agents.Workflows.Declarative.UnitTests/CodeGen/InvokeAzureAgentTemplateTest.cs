// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.CodeGen;
using Microsoft.Agents.Workflows.Declarative.Kit;
using Microsoft.Bot.ObjectModel;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.CodeGen;

public class InvokeAzureAgentTemplateTest(ITestOutputHelper output) : WorkflowActionTemplateTest(output)
{
    [Fact]
    public void LiteralConversation()
    {
        // Act, Assert
        this.ExecuteTest(
            nameof(LiteralConversation),
            StringExpression.Literal("asst_123abc"),
            StringExpression.Literal("conv_123abc"),
            "MyMessages");
    }

    [Fact]
    public void VariableConversation()
    {
        // Act, Assert
        this.ExecuteTest(
            nameof(VariableConversation),
            StringExpression.Variable(PropertyPath.GlobalVariable("TestAgent")),
            StringExpression.Variable(PropertyPath.TopicVariable("TestConversation")),
            "MyMessages",
            BoolExpression.Literal(true));
    }

    [Fact]
    public void ExpressionAutosend()
    {
        // Act, Assert
        this.ExecuteTest(
            nameof(VariableConversation),
            StringExpression.Literal("asst_123abc"),
            StringExpression.Variable(PropertyPath.TopicVariable("TestConversation")),
            "MyMessages",
            BoolExpression.Expression("1 < 2"));
    }

    [Fact]
    public void AdditionalInstructions()
    {
        // Act, Assert
        this.ExecuteTest(
            nameof(VariableConversation),
            StringExpression.Literal("asst_123abc"),
            StringExpression.Variable(PropertyPath.TopicVariable("TestConversation")),
            "MyMessages",
            additionalInstructions: "Test instructions...");
    }

    private void ExecuteTest(
        string displayName,
        StringExpression.Builder agentName,
        StringExpression.Builder conversation,
        string? messagesVariable = null,
        BoolExpression.Builder? autoSend = null,
        string? additionalInstructions = null)
    {
        // Arrange
        InvokeAzureAgent model =
            this.CreateModel(
                displayName,
                agentName,
                conversation,
                messagesVariable,
                autoSend,
                additionalInstructions is null ? null : (TemplateLine.Builder)TemplateLine.Parse(additionalInstructions));

        // Act
        InvokeAzureAgentTemplate template = new(model);
        string workflowCode = template.TransformText();
        this.Output.WriteLine(workflowCode.Trim());

        // Assert
        this.AssertGeneratedCode<ActionExecutor>(template.Id, workflowCode);
        this.AssertAgentProvider(template.UseAgentProvider, workflowCode);
        this.AssertOptionalAssignment(model.Output?.Messages?.Path, workflowCode);
    }

    private InvokeAzureAgent CreateModel(
        string displayName,
        StringExpression.Builder agentName,
        StringExpression.Builder conversation,
        string? messagesVariable = null,
        BoolExpression.Builder? autoSend = null,
        TemplateLine.Builder? additionalInstructions = null)
    {
        InitializablePropertyPath? messages = null;
        if (messagesVariable is not null)
        {
            messages = InitializablePropertyPath.Create(FormatVariablePath(messagesVariable));
        }
        InvokeAzureAgent.Builder actionBuilder =
            new()
            {
                Id = this.CreateActionId("invoke_agent"),
                DisplayName = this.FormatDisplayName(displayName),
                ConversationId = conversation,
                Agent =
                    new AzureAgentUsage.Builder
                    {
                        Name = agentName,
                    },
                Input =
                    new AzureAgentInput.Builder
                    {
                        AdditionalInstructions = additionalInstructions,
                    },
                Output =
                    new AzureAgentOutput.Builder
                    {
                        AutoSend = autoSend,
                        Messages = messages,
                    },
            };

        return actionBuilder.Build();
    }
}
