// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;

namespace Harness.Shared.Console.Commands;

/// <summary>
/// Handles the <c>/todos</c> command to display the current todo list.
/// </summary>
internal sealed class TodoCommandHandler : CommandHandler
{
    private readonly TodoProvider? _todoProvider;

    /// <summary>
    /// Initializes a new instance of the <see cref="TodoCommandHandler"/> class.
    /// </summary>
    /// <param name="todoProvider">The todo provider, or <see langword="null"/> if not available.</param>
    public TodoCommandHandler(TodoProvider? todoProvider)
    {
        this._todoProvider = todoProvider;
    }

    /// <inheritdoc/>
    public override string? GetHelpText() => this._todoProvider is not null ? "/todos (show todo list)" : null;

    /// <inheritdoc/>
    public override async ValueTask<bool> TryHandleAsync(string input, AgentSession session, HarnessUXContainer ux)
    {
        if (!input.Equals("/todos", StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        if (this._todoProvider is null)
        {
            await ux.WriteInfoLineAsync("TodoProvider is not available.").ConfigureAwait(false);
            return true;
        }

        var todos = await this._todoProvider.GetAllTodosAsync(session).ConfigureAwait(false);
        if (todos.Count == 0)
        {
            await ux.WriteInfoLineAsync("No todos yet.").ConfigureAwait(false);
            return true;
        }

        await ux.WriteInfoLineAsync("── Todo List ──").ConfigureAwait(false);
        foreach (var item in todos)
        {
            string status = item.IsComplete ? "✓" : "○";
            ConsoleColor color = item.IsComplete ? ConsoleColor.DarkGray : ConsoleColor.White;
            string description = string.IsNullOrWhiteSpace(item.Description)
                ? string.Empty
                : $" — {item.Description}";
            await ux.WriteInfoLineAsync($"[{status}] #{item.Id} {item.Title}{description}", color).ConfigureAwait(false);
        }

        return true;
    }
}
