// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using AGUI.Client;
using AGUI.WorkflowApproval;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.IntegrationTests.Workflows;

public sealed class ApprovalWorkflowTests
{
    [Fact]
    public async Task ClientApprovesToolRequestAndWorkflowResumesAsync()
    {
        // Arrange
        Workflow workflow = ApprovalWorkflow.Create(new DeterministicExpenseReviewer());
        AIAgent workflowAgent = workflow.AsAIAgent(name: "ApprovalWorkflow");
        await using WorkflowTestHost host = await WorkflowTestHost.StartAsync(workflowAgent, persistSession: true);
        using AGUIChatClient chatClient = new(new(host.Client, ""));
        ChatOptions options = new();
        ExpenseReport report = new(
            "EXP-100",
            "Taylor",
            125.00m,
            "Developer conference registration",
            ReceiptAttached: true);

        // Act - the reviewer requests approval to submit the report.
        List<ChatResponseUpdate> firstTurn = await chatClient
            .GetStreamingResponseAsync(
                [new ChatMessage(ChatRole.User, JsonSerializer.Serialize(report))],
                options)
            .ToListAsync();

#pragma warning disable MEAI001 // Tool approval content is experimental.
        ToolApprovalRequestContent approvalRequest = firstTurn
            .SelectMany(static update => update.Contents)
            .OfType<ToolApprovalRequestContent>()
            .Single();
        FunctionCallContent toolCall = approvalRequest.ToolCall.Should()
            .BeOfType<FunctionCallContent>().Subject;
        toolCall.Name.Should().Be("SubmitExpense");

        ToolApprovalResponseContent approvalResponse = approvalRequest.CreateResponse(
            approved: true,
            reason: "Approved by integration test.");
        List<ChatMessage> approvalMessages =
        [
            new(ChatRole.Assistant, [approvalRequest]),
            new(ChatRole.Tool, [approvalResponse]),
        ];
        List<ChatResponseUpdate> secondTurn = await chatClient
            .GetStreamingResponseAsync(approvalMessages, options)
            .ToListAsync();
#pragma warning restore MEAI001

        // Assert
        secondTurn.Should().Contain(static update => update.Text == "Expense report EXP-100 was submitted.");
    }

    private sealed class DeterministicExpenseReviewer : AIAgent
    {
        public override string? Name => "ExpenseReviewer";

        protected override Task<AgentResponse> RunCoreAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            CancellationToken cancellationToken = default)
            => this.RunStreamingAsync(messages, session, options, cancellationToken).ToAgentResponseAsync(cancellationToken);

        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
#pragma warning disable MEAI001 // Tool approval content is experimental.
            ToolApprovalResponseContent? approvalResponse = messages
                .SelectMany(static message => message.Contents)
                .OfType<ToolApprovalResponseContent>()
                .LastOrDefault();

            if (approvalResponse is not null)
            {
                yield return CreateUpdate(approvalResponse.Approved
                    ? new TextContent("Expense report EXP-100 was submitted.")
                    : new TextContent("Expense report EXP-100 was rejected."));
                yield break;
            }

            FunctionCallContent toolCall = new(
                "submit-expense-call",
                "SubmitExpense",
                new Dictionary<string, object?> { ["reportId"] = "EXP-100" });
            yield return CreateUpdate(new ToolApprovalRequestContent("submit-expense-approval", toolCall));
#pragma warning restore MEAI001
            await Task.Yield();
        }

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
            => new(new ExpenseSession());

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
            AgentSession session,
            JsonSerializerOptions? jsonSerializerOptions = null,
            CancellationToken cancellationToken = default)
            => new(JsonSerializer.SerializeToElement(new Dictionary<string, string>()));

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
            JsonElement serializedState,
            JsonSerializerOptions? jsonSerializerOptions = null,
            CancellationToken cancellationToken = default)
            => new(new ExpenseSession());

        private static AgentResponseUpdate CreateUpdate(AIContent content)
            => new(ChatRole.Assistant, [content])
            {
                MessageId = "expense-review-message",
                ResponseId = "expense-review-response",
            };

        private sealed class ExpenseSession : AgentSession;
    }
}
