# Switch Routing Workflow Sample

This sample demonstrates how to build a workflow with **multi-way routing** using `AddSwitch`. A switch evaluates a set of ordered cases against the output of an executor and routes execution to the **first matching** branch — or to a **default** branch when no case matches.

> **Related sample:** [`03_ConditionalEdges`](../03_ConditionalEdges/README.md) solves a similar branching problem with a different API — `AddEdge(..., condition:)` for per-edge boolean conditions. See [`AddSwitch` vs. conditional edges](#addswitch-vs-conditional-edges) below for when to use which.

## Key Concepts Demonstrated

- Building workflows with **multi-way routing** using `AddSwitch` and `AddCase` / `WithDefault`
- Ordered, first-match-wins case evaluation
- Falling back to a default branch when no case matches
- Using `ConfigureDurableWorkflows` to register workflows with dependency injection

## Overview

The sample implements an expense approval workflow that routes each expense to a different approval path based on its amount:

```
ExpenseParser --[amount < 100]---> AutoApprove
              |--[amount < 1000]--> ManagerApproval
              +--[default]--------> DirectorApproval
```

| Executor | Description |
|----------|-------------|
| ExpenseParser | Parses the entered amount into an `Expense` |
| AutoApprove | Auto-approves small expenses (`< 100`) |
| ManagerApproval | Routes mid-range expenses (`< 1000`) to a manager |
| DirectorApproval | Default branch for everything else (`>= 1000`) |

## How `AddSwitch` Works

`AddSwitch` configures a switch on the output of a source executor. Cases are evaluated **in order**, and the **first** matching case wins; `WithDefault` handles anything that matches no case:

```csharp
builder.AddSwitch(expenseParser, switchBuilder =>
    switchBuilder
        .AddCase<Expense>(expense => expense!.Amount < 100m, autoApprove)
        .AddCase<Expense>(expense => expense!.Amount < 1000m, managerApproval)
        .WithDefault(directorApproval));
```

Each case predicate receives the output of the source executor and returns a boolean.

### `AddSwitch` vs. conditional edges

The [`03_ConditionalEdges`](../03_ConditionalEdges/README.md) sample uses `AddEdge(..., condition:)`, where each edge carries its own **independent** boolean condition (an edge is traversed whenever its condition is true). `AddSwitch` instead models **mutually exclusive, first-match-wins** routing with a single default — a better fit when exactly one of several branches should run.

## Environment Setup

See the [README.md](../../README.md) file in the parent directory for information on configuring the environment, including how to install and run the Durable Task Scheduler.

## Running the Sample

```bash
cd dotnet/samples/04-hosting/DurableWorkflows/ConsoleApps/09_SwitchRouting
dotnet run --framework net10.0
```

### Sample Output

```text
Enter an expense amount (or 'exit'):
Tip: try 50, 450, and 5000 to see each branch.

> 50
Starting workflow for expense amount '50'...
Run ID: abc123...
Waiting for workflow to complete...
Workflow completed. Expense EXP-1a2b for $50.00 was auto-approved.

> 450
Starting workflow for expense amount '450'...
Run ID: def456...
Waiting for workflow to complete...
Workflow completed. Expense EXP-3c4d for $450.00 was routed to a manager for approval.

> 5000
Starting workflow for expense amount '5000'...
Run ID: ghi789...
Waiting for workflow to complete...
Workflow completed. Expense EXP-5e6f for $5,000.00 was routed to a director for approval.
```
