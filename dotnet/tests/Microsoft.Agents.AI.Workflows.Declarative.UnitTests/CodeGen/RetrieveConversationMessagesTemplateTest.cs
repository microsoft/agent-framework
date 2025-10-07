// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.CodeGen;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Bot.ObjectModel;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.CodeGen;

public class RetrieveConversationMessagesTemplateTest(ITestOutputHelper output) : WorkflowActionTemplateTest(output)
{
    [Fact]
    public void DefaultQuery()
    {
        // Act, Assert
        this.ExecuteTest(
            nameof(DefaultQuery),
            "TestVariable",
            StringExpression.Variable(PropertyPath.TopicVariable("TestConversation")));
    }

    [Fact]
    public void LimitCountQuery()
    {
        // Act, Assert
        this.ExecuteTest(
            nameof(DefaultQuery),
            "TestVariable",
            StringExpression.Literal("#cid_3"),
            limit: IntExpression.Literal(94));
    }

    [Fact]
    public void AfterMessageQuery()
    {
        // Act, Assert
        this.ExecuteTest(
            nameof(DefaultQuery),
            "TestVariable",
            StringExpression.Literal("#cid_3"),
            after: StringExpression.Literal("#mid_43"));
    }

    [Fact]
    public void BeforeMessageQuery()
    {
        // Act, Assert
        this.ExecuteTest(
            nameof(DefaultQuery),
            "TestVariable",
            StringExpression.Literal("#cid_3"),
            before: StringExpression.Literal("#mid_43"));
    }

    [Fact]
    public void NewestFirstQuery()
    {
        // Act, Assert
        this.ExecuteTest(
            nameof(DefaultQuery),
            "TestVariable",
            StringExpression.Literal("#cid_3"),
            sortOrder: EnumExpression<AgentMessageSortOrderWrapper>.Literal(AgentMessageSortOrderWrapper.Get(AgentMessageSortOrder.NewestFirst)));
    }

    private void ExecuteTest(
        string displayName,
        string variableName,
        StringExpression conversation,
        IntExpression? limit = null,
        StringExpression? after = null,
        StringExpression? before = null,
        EnumExpression<AgentMessageSortOrderWrapper>? sortOrder = null)
    {
        // Arrange
        RetrieveConversationMessages model =
            this.CreateModel(
                displayName,
                FormatVariablePath(variableName),
                conversation,
                limit,
                after,
                before,
                sortOrder);

        // Act
        RetrieveConversationMessagesTemplate template = new(model);
        string workflowCode = template.TransformText();
        this.Output.WriteLine(workflowCode.Trim());

        // Assert
        AssertGeneratedCode<ActionExecutor>(template.Id, workflowCode);
        AssertAgentProvider(template.UseAgentProvider, workflowCode);
        AssertGeneratedAssignment(model.Messages?.Path, workflowCode);
    }

    private RetrieveConversationMessages CreateModel(
        string displayName,
        string variableName,
        StringExpression conversationExpression,
        IntExpression? limitExpression,
        StringExpression? afterExpression,
        StringExpression? beforeExpression,
        EnumExpression<AgentMessageSortOrderWrapper>? sortExpression)
    {
        RetrieveConversationMessages.Builder actionBuilder =
            new()
            {
                Id = this.CreateActionId("retrieve_messages"),
                DisplayName = this.FormatDisplayName(displayName),
                Messages = PropertyPath.Create(variableName),
                ConversationId = conversationExpression,
            };

        if (limitExpression is not null)
        {
            actionBuilder.Limit = limitExpression;
        }

        if (afterExpression is not null)
        {
            actionBuilder.MessageAfter = afterExpression;
        }

        if (beforeExpression is not null)
        {
            actionBuilder.MessageBefore = beforeExpression;
        }

        if (sortExpression is not null)
        {
            actionBuilder.SortOrder = sortExpression;
        }

        return actionBuilder.Build();
    }
}
