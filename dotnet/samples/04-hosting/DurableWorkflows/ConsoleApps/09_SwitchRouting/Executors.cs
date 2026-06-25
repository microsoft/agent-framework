// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace SwitchRouting;

internal sealed record Expense(string Id, decimal Amount);

internal sealed class ExpenseParser() : Executor<string, Expense>("ExpenseParser")
{
    public override async ValueTask<Expense> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        // The input is the expense amount (e.g., "50" or "4500"). A real workflow would
        // look the expense up from a store; here we just attach a generated id.
        decimal amount = decimal.TryParse(message, out decimal parsed) ? parsed : 0m;
        return new Expense($"EXP-{Guid.NewGuid().ToString()[..4]}", amount);
    }
}

internal sealed class AutoApprove() : Executor<Expense, string>("AutoApprove")
{
    public override async ValueTask<string> HandleAsync(Expense message, IWorkflowContext context, CancellationToken cancellationToken = default)
        => $"Expense {message.Id} for {message.Amount:C} was auto-approved.";
}

internal sealed class ManagerApproval() : Executor<Expense, string>("ManagerApproval")
{
    public override async ValueTask<string> HandleAsync(Expense message, IWorkflowContext context, CancellationToken cancellationToken = default)
        => $"Expense {message.Id} for {message.Amount:C} was routed to a manager for approval.";
}

internal sealed class DirectorApproval() : Executor<Expense, string>("DirectorApproval")
{
    public override async ValueTask<string> HandleAsync(Expense message, IWorkflowContext context, CancellationToken cancellationToken = default)
        => $"Expense {message.Id} for {message.Amount:C} was routed to a director for approval.";
}
