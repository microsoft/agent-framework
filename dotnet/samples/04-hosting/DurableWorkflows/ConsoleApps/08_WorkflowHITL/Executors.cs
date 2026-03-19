// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace WorkflowHITL;

/// <summary>
/// Represents an expense approval request.
/// </summary>
/// <param name="ExpenseId">The unique identifier of the expense.</param>
/// <param name="Amount">The amount of the expense.</param>
/// <param name="EmployeeName">The name of the employee submitting the expense.</param>
public record ApprovalRequest(string ExpenseId, decimal Amount, string EmployeeName);

/// <summary>
/// Represents the response to an approval request.
/// </summary>
/// <param name="Approved">Whether the expense was approved.</param>
/// <param name="Comments">Optional comments from the approver.</param>
public record ApprovalResponse(bool Approved, string? Comments);

/// <summary>
/// Retrieves expense details and creates an approval request.
/// </summary>
internal sealed class CreateApprovalRequest() : Executor<string, ApprovalRequest>("RetrieveRequest")
{
    /// <inheritdoc/>
    public override ValueTask<ApprovalRequest> HandleAsync(
        string message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        // In a real scenario, this would look up expense details from a database
        return new ValueTask<ApprovalRequest>(new ApprovalRequest(message, 1500.00m, "Jerry"));
    }
}

/// <summary>
/// Prepares the approval request for finance review after manager approval.
/// </summary>
internal sealed class PrepareFinanceReview() : Executor<ApprovalResponse, ApprovalRequest>("PrepareFinanceReview")
{
    /// <inheritdoc/>
    public override ValueTask<ApprovalRequest> HandleAsync(
        ApprovalResponse message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        if (!message.Approved)
        {
            throw new InvalidOperationException("Cannot proceed to finance review — manager denied the expense.");
        }

        // In a real scenario, this would retrieve the original expense details
        return new ValueTask<ApprovalRequest>(new ApprovalRequest("EXP-2025-001", 1500.00m, "Jerry"));
    }
}

/// <summary>
/// Processes the expense reimbursement based on the parallel approval responses from budget and compliance.
/// </summary>
internal sealed class ExpenseReimburse() : Executor<ApprovalResponse[], string>("Reimburse")
{
    /// <inheritdoc/>
    public override async ValueTask<string> HandleAsync(
        ApprovalResponse[] message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        // Check that all parallel approvals passed
        ApprovalResponse? denied = Array.Find(message, r => !r.Approved);
        if (denied is not null)
        {
            return $"Expense reimbursement denied. Comments: {denied.Comments}";
        }

        // Simulate payment processing
        await Task.Delay(1000, cancellationToken);
        return $"Expense reimbursed at {DateTime.UtcNow:O}";
    }
}
