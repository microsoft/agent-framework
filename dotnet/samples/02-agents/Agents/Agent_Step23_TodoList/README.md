# Todo List

This sample demonstrates how to use the `TodoProvider` to let an agent plan and track multi-step
work using a todo list that persists across turns within a session.

The `TodoProvider` is an `AIContextProvider` that contributes todo-management tools and instructions
to the agent, and stores the todo list in the session state. The provider exposes the following
tools to the agent:

- `todos_add` — add one or more todo items (title + optional description).
- `todos_complete` — mark one or more items complete, with a reason.
- `todos_remove` — remove one or more items by ID.
- `todos_get_remaining` — retrieve the incomplete items.
- `todos_get_all` — retrieve all items (complete and incomplete).

## What it demonstrates

- Attaching a `TodoProvider` to an agent via `ChatClientAgentOptions.AIContextProviders`.
- The agent breaking a complex request into trackable todo items, marking items complete as
  progress is reported, and adjusting the list when the plan changes.
- Reading the todo list from application code with `TodoProvider.GetAllTodosAsync`.

This is a **scripted, non-interactive** walkthrough: it sends a fixed sequence of messages and,
after each turn, prints the agent's reply followed by the current todo list so you can watch the
state evolve.

## Prerequisites

- .NET 10 SDK or later
- Microsoft Foundry project endpoint and model configured
- Azure CLI installed and authenticated (run `az login`)
- User has the required role to invoke models in the Foundry project

## Running the sample

Set the required environment variables:

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT="https://your-project-endpoint"
$env:FOUNDRY_MODEL="gpt-5.4-mini"  # Optional, defaults to gpt-5.4-mini
```

Run the sample:

```powershell
dotnet run
```
