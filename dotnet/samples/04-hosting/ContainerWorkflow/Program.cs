// Copyright (c) Microsoft. All rights reserved.

// Host a deterministic expense-routing workflow in ASP.NET Core, locally or in a container.
using Microsoft.Agents.AI.Workflows;

WebApplicationBuilder builder = WebApplication.CreateBuilder(args);
WebApplication app = builder.Build();

app.MapGet("/health", () => Results.Ok());
app.MapPost("/expenses", async (ExpenseRequest expense, CancellationToken cancellationToken) =>
{
    if (string.IsNullOrWhiteSpace(expense.Id) || expense.Id.Length > 128 || expense.Amount <= 0)
    {
        return Results.BadRequest(new { error = "Supply an id of 1-128 characters and an amount greater than zero." });
    }

    // Each request owns its executors and workflow state, so concurrent requests remain isolated.
    NormalizeExpenseExecutor normalize = new();
    RouteExpenseExecutor route = new();
    Workflow workflow = new WorkflowBuilder(normalize).AddEdge(normalize, route).WithOutputFrom(route).Build();

    await using StreamingRun run = await InProcessExecution.RunStreamingAsync(workflow, expense, cancellationToken: cancellationToken);
    ExpenseDecision? decision = null;
    await foreach (WorkflowEvent evt in run.WatchStreamAsync(cancellationToken))
    {
        if (evt is WorkflowErrorEvent or ExecutorFailedEvent)
        {
            return Results.Problem("The expense workflow failed.");
        }

        if (evt is WorkflowOutputEvent { Data: ExpenseDecision output })
        {
            decision = output;
        }
    }

    // Disposing the run also stops execution when request cancellation ends stream consumption.
    return decision is null ? Results.Problem("The workflow produced no decision.") : Results.Ok(decision);
});

await app.RunAsync();

internal readonly record struct ExpenseRequest(string? Id, decimal Amount);

internal sealed record ExpenseDecision(string Id, decimal Amount, string Route);

internal sealed class NormalizeExpenseExecutor() : Executor<ExpenseRequest, ExpenseRequest>("NormalizeExpense")
{
    /// <inheritdoc/>
    public override ValueTask<ExpenseRequest> HandleAsync(ExpenseRequest message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        return ValueTask.FromResult(message with { Id = message.Id!.Trim() });
    }
}

internal sealed class RouteExpenseExecutor() : Executor<ExpenseRequest, ExpenseDecision>("RouteExpense")
{
    /// <inheritdoc/>
    public override ValueTask<ExpenseDecision> HandleAsync(ExpenseRequest message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        // ponytail: this sample routes expenses; it does not approve payments or call a business system.
        return ValueTask.FromResult(new ExpenseDecision(message.Id!, message.Amount,
            message.Amount > 100 ? "manager_review" : "standard_review"));
    }
}
