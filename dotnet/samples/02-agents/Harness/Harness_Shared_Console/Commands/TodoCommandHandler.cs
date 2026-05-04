// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;

namespace Harness.Shared.Console.Commands;

/// <summary>
/// Handles the <c>/todos</c> command to display the current todo list.
/// </summary>
internal sealed class TodoCommandHandler : ICommandHandler
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
    public string? GetHelpText() => this._todoProvider is not null ? "/todos (show todo list)" : null;

    /// <inheritdoc/>
    public bool TryHandle(string input, AgentSession session)
    {
        if (!input.Equals("/todos", StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        if (this._todoProvider is null)
        {
            System.Console.WriteLine("TodoProvider is not available.");
            return true;
        }

        var todos = this._todoProvider.GetAllTodos(session);
        if (todos.Count == 0)
        {
            System.Console.WriteLine("\n  No todos yet.\n");
            return true;
        }

        System.Console.WriteLine();
        System.Console.WriteLine("  ── Todo List ──");
        foreach (var item in todos)
        {
            string status = item.IsComplete ? "✓" : "○";
            System.Console.ForegroundColor = item.IsComplete ? ConsoleColor.DarkGray : ConsoleColor.White;
            System.Console.Write($"  [{status}] #{item.Id} {item.Title}");
            if (!string.IsNullOrWhiteSpace(item.Description))
            {
                System.Console.Write($" — {item.Description}");
            }

            System.Console.WriteLine();
        }

        System.Console.ResetColor();
        System.Console.WriteLine();
        return true;
    }
}
