// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;

namespace Harness.Shared.Console.Commands;

/// <summary>
/// Handles the <c>/mode</c> command to display or switch the current agent mode.
/// </summary>
internal sealed class ModeCommandHandler : CommandHandler
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
    public override string? GetHelpText() => this._modeProvider is not null ? "/mode [plan|execute] (show or switch mode)" : null;

    /// <inheritdoc/>
    public override async ValueTask<bool> TryHandleAsync(string input, AgentSession session, HarnessUXContainer ux)
    {
        if (!input.StartsWith("/mode ", StringComparison.OrdinalIgnoreCase) && !input.Equals("/mode", StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        if (this._modeProvider is null)
        {
            await ux.WriteInfoLineAsync("AgentModeProvider is not available.").ConfigureAwait(false);
            return true;
        }

        string[] parts = input.Split(' ', 2, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        if (parts.Length < 2)
        {
            string current = this._modeProvider.GetMode(session);
            await ux.WriteInfoLineAsync($"Current mode: {current}").ConfigureAwait(false);
            return true;
        }

        string newMode = parts[1];

        try
        {
            this._modeProvider.SetMode(session, newMode);
            ux.CurrentMode = newMode;
            await ux.WriteInfoLineAsync($"Switched to {newMode} mode.", ModeColors.Get(newMode, this._modeColors)).ConfigureAwait(false);
        }
        catch (ArgumentException ex)
        {
            await ux.WriteInfoLineAsync(ex.Message, ConsoleColor.Red).ConfigureAwait(false);
        }

        return true;
    }
}
