// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Concurrent;
using System.ComponentModel;

namespace AspNetAgentAuthorization.Service;

/// <summary>
/// Represents an expense awaiting approval.
/// </summary>
public sealed class Expense
{
    public int Id { get; init; }

    public string Description { get; init; } = string.Empty;

    public decimal Amount { get; init; }

    public string Submitter { get; init; } = string.Empty;

    public string Status { get; set; } = "Pending";

    public string? ApprovedBy { get; set; }
}

/// <summary>
/// Manages expense approvals. Pre-seeded with demo data so there are
/// expenses to review immediately. Uses <see cref="IUserContext"/> to
/// identify the caller and enforce scope-based permissions.
/// </summary>
public sealed class ExpenseService
{
    /// <summary>Maximum amount (EUR) that can be approved.</summary>
    private const decimal ApprovalLimit = 1000m;

    private static readonly ConcurrentDictionary<int, Expense> s_expenses = new(
        new Dictionary<int, Expense>
        {
            [1] = new() { Id = 1, Description = "Conference travel — Berlin", Amount = 850m, Submitter = "Alice" },
            [2] = new() { Id = 2, Description = "Team dinner — Q4 celebration", Amount = 320m, Submitter = "Bob" },
            [3] = new() { Id = 3, Description = "Cloud infrastructure — annual renewal", Amount = 4500m, Submitter = "Carol" },
            [4] = new() { Id = 4, Description = "Office supplies — ergonomic keyboards", Amount = 675m, Submitter = "Dave" },
            [5] = new() { Id = 5, Description = "Client gift baskets — holiday season", Amount = 980m, Submitter = "Eve" },
        });

    private readonly IUserContext _userContext;

    public ExpenseService(IUserContext userContext)
    {
        this._userContext = userContext;
    }

    /// <summary>
    /// Lists all pending expenses awaiting approval.
    /// </summary>
    [Description("Lists all pending expenses awaiting approval. Requires the expenses.view scope.")]
    public string ListPendingExpenses()
    {
        if (!this._userContext.Scopes.Contains("expenses.view"))
        {
            return "Access denied. You do not have the expenses.view scope.";
        }

        var pending = s_expenses.Values
            .Where(e => e.Status == "Pending")
            .OrderBy(e => e.Id)
            .ToList();

        if (pending.Count == 0)
        {
            return "No pending expenses.";
        }

        return string.Join("\n", pending.Select(e =>
            $"#{e.Id}: {e.Description} — €{e.Amount:N2} (submitted by {e.Submitter})"));
    }

    /// <summary>
    /// Approves a pending expense by its ID.
    /// </summary>
    [Description("Approves a pending expense by its ID. Requires the expenses.approve scope.")]
    public string ApproveExpense([Description("The ID of the expense to approve")] int expenseId)
    {
        if (!this._userContext.Scopes.Contains("expenses.approve"))
        {
            return "Access denied. You do not have the expenses.approve scope.";
        }

        if (!s_expenses.TryGetValue(expenseId, out var expense))
        {
            return $"Expense #{expenseId} not found.";
        }

        if (expense.Status != "Pending")
        {
            return $"Expense #{expenseId} has already been approved.";
        }

        if (expense.Amount > ApprovalLimit)
        {
            return $"Cannot approve expense #{expenseId} (€{expense.Amount:N2}). " +
                   $"Amount exceeds the €{ApprovalLimit:N2} approval limit.";
        }

        expense.Status = "Approved";
        expense.ApprovedBy = this._userContext.DisplayName;

        return $"Expense #{expenseId} (\"{expense.Description}\", €{expense.Amount:N2}) has been approved.";
    }
}
