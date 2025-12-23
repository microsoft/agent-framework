// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx.Types;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.ObjectModel;

/// <summary>
/// Tests for <see cref="CreateConversationExecutor "/>.
/// </summary>
public sealed class CreateConversationExecutorTest(ITestOutputHelper output) : WorkflowActionExecutorTest(output)
{
    [Fact]
    public async Task CreateNewConversationAsync()
    {
        // Arrange, Act, Assert
        await this.ExecuteTestAsync(nameof(CreateNewConversationAsync),
            "TestConversationId",
            executionIteration: 1);
    }

    [Fact]
    public async Task CreateMultipleConversationsAsync()
    {
        // Arrange, Act, Assert
        await this.ExecuteTestAsync(nameof(CreateMultipleConversationsAsync),
            "TestConversationId",
            executionIteration: 4);
    }

    private async Task ExecuteTestAsync(
        string displayName,
        string variableName,
        int executionIteration)
    {
        // Arrange
        // Initialize state to simulate workflow environment.
        this.State.InitializeSystem();
        CreateConversation model = this.CreateModel(
            this.FormatDisplayName(displayName),
            FormatVariablePath(variableName));
        MockAgentProvider mockAgentProvider = new();
        CreateConversationExecutor action = new(model, mockAgentProvider.Object, this.State);

        // Act
        int expectedIterationCount = executionIteration;
        while (executionIteration-- > 0)
        {
            await this.ExecuteAsync(action);
        }

        // Assert
        VerifyModel(model, action);
        Assert.Equal(expected: expectedIterationCount, actual: mockAgentProvider.ExistingConversationIds.Count);
        this.VerifyState("TestConversationId", FormulaValue.New(mockAgentProvider.ExistingConversationIds.Last()));
    }

    private CreateConversation CreateModel(string displayName, string conversationIdVariable)
    {
        CreateConversation.Builder actionBuilder =
            new()
            {
                Id = this.CreateActionId(),
                DisplayName = this.FormatDisplayName(displayName),
                ConversationId = PropertyPath.Create(conversationIdVariable)
            };

        return AssignParent<CreateConversation>(actionBuilder);
    }
}
