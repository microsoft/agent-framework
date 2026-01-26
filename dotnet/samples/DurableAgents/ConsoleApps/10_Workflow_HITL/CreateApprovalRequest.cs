// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace SingleAgent;

public record ApprovalRequest(string ExpenseId, decimal Amount, string EmployeeName);
public record ApprovalResponse(bool Approved, string? Comments);

internal sealed class CreateApprovalRequest() : Executor<string, ApprovalRequest>("RetrieveRequest")
{
    public override async ValueTask<ApprovalRequest> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        // Get request details from db.
        return new ApprovalRequest(message, 1500.00m, "Jerry");
    }
}

internal sealed class ExpenseReimburse() : Executor<ApprovalResponse, string>("Reimburse")
{
    public override async ValueTask<string> HandleAsync(ApprovalResponse message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        // Simulate payment processing.
        await Task.Delay(1000, cancellationToken);
        return $"Expense reimbursed at {DateTime.Now.ToUniversalTime()}";
    }
}
