// Copyright (c) Microsoft. All rights reserved.

using Harness.ConsoleReactiveComponents;
using Harness.ConsoleReactiveFramework;

namespace Harness.Shared.Console.Components;

/// <summary>
/// Props for <see cref="AgentModeAndHelp"/>.
/// </summary>
public record AgentModeAndHelpProps : ConsoleReactiveProps
{
    /// <summary>Gets or sets the current mode name (e.g. "plan", "execute"), or <see langword="null"/> if no mode is active.</summary>
    public string? Mode { get; set; }

    /// <summary>Gets or sets the foreground color for the mode label.</summary>
    public ConsoleColor? ModeColor { get; set; }

    /// <summary>Gets or sets the help text to display (e.g. available commands and exit info).</summary>
    public string? HelpText { get; set; }
}

/// <summary>
/// A component that renders a single fixed line below the bottom rule showing
/// the current agent mode (in the mode colour) and available commands (in dark grey).
/// </summary>
public class AgentModeAndHelp : ConsoleReactiveComponent<AgentModeAndHelpProps, ConsoleReactiveState>
{
    /// <summary>
    /// Calculates the height of the component.
    /// </summary>
    /// <param name="props">The component props.</param>
    /// <returns>1 if there is content to display; otherwise 0.</returns>
    public static int CalculateHeight(AgentModeAndHelpProps props) =>
        (props.Mode is not null || !string.IsNullOrEmpty(props.HelpText)) ? 1 : 0;

    /// <inheritdoc />
    public override void RenderCore(AgentModeAndHelpProps props, ConsoleReactiveState state)
    {
        if (props.Mode is null && string.IsNullOrEmpty(props.HelpText))
        {
            return;
        }

        System.Console.Write(AnsiEscapes.SaveCursor);
        System.Console.Write(AnsiEscapes.MoveAndEraseLine(this.Y));

        bool hasMode = props.Mode is not null;

        if (hasMode)
        {
            if (props.ModeColor.HasValue)
            {
                System.Console.Write(AnsiEscapes.SetForegroundColor(props.ModeColor.Value));
            }

            System.Console.Write($" [{props.Mode}]");
            System.Console.Write(AnsiEscapes.ResetAttributes);
        }

        if (!string.IsNullOrEmpty(props.HelpText))
        {
            string prefix = hasMode ? "  " : " ";
            System.Console.Write(AnsiEscapes.SetForegroundColor(ConsoleColor.DarkGray));
            System.Console.Write($"{prefix}{props.HelpText}");
            System.Console.Write(AnsiEscapes.ResetAttributes);
        }

        System.Console.Write(AnsiEscapes.RestoreCursor);
    }
}
