// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace AGUI.WorkflowApproval;

/// <summary>
/// Creates the approval workflow used by the sample and its integration test.
/// </summary>
public static class ApprovalWorkflow
{
    /// <summary>
    /// Creates a workflow that pauses for approval before submitting an expense.
    /// </summary>
    /// <returns>The approval workflow.</returns>
    public static Workflow Create()
    {
        ExpenseApprovalExecutor executor = new();
        return new WorkflowBuilder(executor)
            .AddExternalCall<ExpenseApprovalRequest, JsonElement>(executor, "ApprovalInput")
            .WithOutputFrom(executor)
            .Build();
    }
}

/// <summary>
/// The expense approval request presented to the client.
/// </summary>
/// <param name="ExpenseId">The expense identifier.</param>
/// <param name="Amount">The expense amount.</param>
public sealed record ExpenseApprovalRequest(string ExpenseId, decimal Amount);

[SendsMessage(typeof(ExpenseApprovalRequest))]
internal sealed partial class ExpenseApprovalExecutor()
    : ChatProtocolExecutor("ExpenseApproval", new ChatProtocolExecutorOptions { AutoSendTurnToken = false })
{
    protected override ValueTask TakeTurnAsync(
        List<ChatMessage> messages,
        IWorkflowContext context,
        bool? emitEvents,
        CancellationToken cancellationToken = default)
        => context.SendMessageAsync(new ExpenseApprovalRequest("EXP-100", 125.00m), cancellationToken);

    [MessageHandler]
    public async ValueTask HandleApprovalAsync(
        JsonElement response,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        bool approved = response.GetProperty("approved").GetBoolean();
        string result = approved ? "Expense approved and submitted." : "Expense rejected.";
        AgentResponseUpdate update = new(ChatRole.Assistant, result)
        {
            MessageId = "expense-result",
            ResponseId = "expense-response",
        };
        await context.AddEventAsync(new AgentResponseUpdateEvent(this.Id, update), cancellationToken).ConfigureAwait(false);
        await context.SendMessageAsync(new TurnToken(false), cancellationToken).ConfigureAwait(false);
    }
}
