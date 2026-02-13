// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.ObjectModel;

/// <summary>
/// Tests for <see cref="InvokeFunctionToolExecutor"/>.
/// </summary>
public sealed class InvokeFunctionToolExecutorTest(ITestOutputHelper output) : WorkflowActionExecutorTest(output)
{
    [Fact]
    public async Task ExecutorCreatedWithValidModelAsync()
    {
        // Arrange
        // Initialize state to simulate workflow environment.
        this.State.InitializeSystem();
        InvokeFunctionTool model = this.CreateModel(
            displayName: nameof(ExecutorCreatedWithValidModelAsync),
            functionName: "test_function",
             requireApproval: true,
            conversationId: "TestConversationId");
        MockAgentProvider mockAgentProvider = new();
        InvokeFunctionToolExecutor action = new(model, mockAgentProvider.Object, this.State);

        // Act
        await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);
    }

    private InvokeFunctionTool CreateModel(
        string displayName,
        string functionName,
        bool requireApproval = false,
        string? conversationId = null)
    {
        InvokeFunctionTool.Builder builder = new()
        {
            Id = this.CreateActionId(),
            DisplayName = this.FormatDisplayName(displayName),
            FunctionName = new StringExpression.Builder(StringExpression.Literal(functionName)),
            RequireApproval = new BoolExpression.Builder(BoolExpression.Literal(requireApproval))
        };

        if (conversationId is not null)
        {
            builder.ConversationId = new StringExpression.Builder(StringExpression.Literal(conversationId));
        }

        return AssignParent<InvokeFunctionTool>(builder);
    }
}
