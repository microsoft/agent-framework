// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.CodeGen;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Bot.ObjectModel;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.CodeGen;

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
            messagesVariable: null);
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
    public void InputMessagesVariable()
    {
        // Act, Assert
        this.ExecuteTest(
            nameof(VariableConversation),
            StringExpression.Literal("asst_123abc"),
            StringExpression.Variable(PropertyPath.TopicVariable("TestConversation")),
            "MyMessages",
            messages: ValueExpression.Variable(PropertyPath.TopicVariable("TestConversation")));
    }

    [Fact]
    public void InputMessagesExpression()
    {
        // Act, Assert
        this.ExecuteTest(
            nameof(VariableConversation),
            StringExpression.Literal("asst_123abc"),
            StringExpression.Literal("conv_123abc"),
            "MyMessages",
            messages: ValueExpression.Expression("[UserMessage(System.LastMessageText)]"));
    }

    private void ExecuteTest(
        string displayName,
        StringExpression.Builder agentName,
        StringExpression.Builder conversation,
        string? messagesVariable = null,
        BoolExpression.Builder? autoSend = null,
        ValueExpression.Builder? messages = null)
    {
        // Arrange
        InvokeAzureAgent model =
            this.CreateModel(
                displayName,
                agentName,
                conversation,
                messagesVariable,
                autoSend,
                messages);

        // Act
        InvokeAzureAgentTemplate template = new(model);
        string workflowCode = template.TransformText();
        this.Output.WriteLine(workflowCode.Trim());

        // Assert
        AssertGeneratedCode<AgentExecutor>(template.Id, workflowCode);
        AssertAgentProvider(template.UseAgentProvider, workflowCode);
        AssertOptionalAssignment(model.Output?.Messages?.Path, workflowCode);
    }

    private InvokeAzureAgent CreateModel(
        string displayName,
        StringExpression.Builder agentName,
        StringExpression.Builder conversation,
        string? messagesVariable = null,
        BoolExpression.Builder? autoSend = null,
        ValueExpression.Builder? messages = null)
    {
        InitializablePropertyPath? outputMessages = null;
        if (messagesVariable is not null)
        {
            outputMessages = PropertyPath.Create(FormatVariablePath(messagesVariable));
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
                        Messages = messages,
                    },
                Output =
                    new AzureAgentOutput.Builder
                    {
                        AutoSend = autoSend,
                        Messages = outputMessages,
                    },
            };

        return actionBuilder.Build();
    }
}
