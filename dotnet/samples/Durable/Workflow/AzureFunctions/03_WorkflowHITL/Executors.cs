// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace WorkflowHITLFunctions;

/// <summary>Expense approval request passed to the RequestPort.</summary>
public record ApprovalRequest(string ExpenseId, decimal Amount, string EmployeeName);

/// <summary>Approval response received from the RequestPort.</summary>
public record ApprovalResponse(bool Approved, string? Comments);

/// <summary>Looks up expense details and creates an approval request.</summary>
internal sealed class CreateApprovalRequest() : Executor<string, ApprovalRequest>("RetrieveRequest")
{
    public override ValueTask<ApprovalRequest> HandleAsync(
        string message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        // In a real scenario, this would look up expense details from a database
        return new ValueTask<ApprovalRequest>(new ApprovalRequest(message, 1500.00m, "Jerry"));
    }
}

/// <summary>Processes the expense reimbursement based on the approval decision.</summary>
internal sealed class ExpenseReimburse() : Executor<ApprovalResponse, string>("Reimburse")
{
    public override async ValueTask<string> HandleAsync(
        ApprovalResponse message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        if (!message.Approved)
        {
            return $"Expense reimbursement denied. Comments: {message.Comments}";
        }

        // Simulate payment processing
        await Task.Delay(1000, cancellationToken);
        return $"Expense reimbursed at {DateTime.UtcNow:O}";
    }
}
