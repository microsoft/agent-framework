// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;

namespace AGUI.WorkflowApproval;

/// <summary>
/// Creates the approval workflow used by the sample and its integration test.
/// </summary>
public static class ApprovalWorkflow
{
    /// <summary>
    /// Creates a workflow containing one expense-review agent.
    /// </summary>
    /// <param name="expenseReviewer">The agent that checks and submits expense reports.</param>
    /// <returns>The expense approval workflow.</returns>
    public static Workflow Create(AIAgent expenseReviewer)
        => new SequentialWorkflowBuilder(expenseReviewer).Build();
}

/// <summary>
/// An expense report submitted to the workflow.
/// </summary>
/// <param name="Id">The report identifier.</param>
/// <param name="Employee">The submitting employee.</param>
/// <param name="Amount">The total expense amount.</param>
/// <param name="BusinessPurpose">The business purpose.</param>
/// <param name="ReceiptAttached">Whether a receipt is attached.</param>
public sealed record ExpenseReport(
    string Id,
    string Employee,
    decimal Amount,
    string BusinessPurpose,
    bool ReceiptAttached);
