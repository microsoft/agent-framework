// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;

namespace Harness.Shared.Console.Commands;

/// <summary>
/// Handles the <c>/mode</c> command to display or switch the current agent mode.
/// </summary>
internal sealed class ModeCommandHandler : ICommandHandler
{
    private readonly AgentModeProvider? _modeProvider;
    private readonly IReadOnlyDictionary<string, ConsoleColor>? _modeColors;

    /// <summary>
    /// Initializes a new instance of the <see cref="ModeCommandHandler"/> class.
    /// </summary>
    /// <param name="modeProvider">The mode provider, or <see langword="null"/> if not available.</param>
    /// <param name="modeColors">Optional mapping of mode names to console colors.</param>
    public ModeCommandHandler(AgentModeProvider? modeProvider, IReadOnlyDictionary<string, ConsoleColor>? modeColors = null)
    {
        this._modeProvider = modeProvider;
        this._modeColors = modeColors;
    }

    /// <inheritdoc/>
    public string? GetHelpText() => this._modeProvider is not null ? "/mode [plan|execute] (show or switch mode)" : null;

    /// <inheritdoc/>
    public bool TryHandle(string input, AgentSession session)
    {
        if (!input.StartsWith("/mode ", StringComparison.OrdinalIgnoreCase) && !input.Equals("/mode", StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        if (this._modeProvider is null)
        {
            System.Console.WriteLine("AgentModeProvider is not available.");
            return true;
        }

        string[] parts = input.Split(' ', 2, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        if (parts.Length < 2)
        {
            string current = this._modeProvider.GetMode(session);
            System.Console.WriteLine($"\n  Current mode: {current}\n");
            return true;
        }

        string newMode = parts[1];

        try
        {
            this._modeProvider.SetMode(session, newMode);
            System.Console.ForegroundColor = ConsoleWriter.GetModeColor(newMode, this._modeColors);
            System.Console.WriteLine($"\n  Switched to {newMode} mode.\n");
            System.Console.ResetColor();
        }
        catch (ArgumentException ex)
        {
            System.Console.ForegroundColor = ConsoleColor.Red;
            System.Console.WriteLine($"\n  {ex}\n");
            System.Console.ResetColor();
        }

        return true;
    }
}
